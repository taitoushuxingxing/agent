"""Vehicle diagnosis task service."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from vehicleagents.agents.utils.memory import MongoVehicleMemoryStore, SQLiteVehicleMemoryStore, VehicleDiagnosisMemory
from vehicleagents.graph import VehicleDiagnosisGraph

from ..core.config import get_settings
from ..core.llm_client import create_llm_pair
from ..core.llm_config import load_llm_config
from ..core.logging import get_logger
from ..models.vehicle_diagnosis import DiagnosisTask
from ..queues.task_queue import RedisTaskQueue, TaskQueue
from ..repositories.mongo_vehicle_diagnosis_repository import MongoVehicleDiagnosisRepository

logger = get_logger("vehicle_diagnosis.service")

DEPTH_DEFAULTS = {
    "quick": {"max_debate_rounds": 0, "max_safety_discuss_rounds": 1},
    "basic": {"max_debate_rounds": 1, "max_safety_discuss_rounds": 1},
    "standard": {"max_debate_rounds": 1, "max_safety_discuss_rounds": 1},
    "deep": {"max_debate_rounds": 2, "max_safety_discuss_rounds": 2},
    "comprehensive": {"max_debate_rounds": 3, "max_safety_discuss_rounds": 3},
}


@dataclass
class GraphCacheEntry:
    graph: VehicleDiagnosisGraph
    created_at: float
    last_used_at: float


class TaskCancelledDuringGraph(RuntimeError):
    """Raised inside the graph worker thread when a running task is cancelled."""


class VehicleDiagnosisService:
    def __init__(
        self,
        repository: Any | None = None,
        task_queue: TaskQueue | None = None,
        memory: VehicleDiagnosisMemory | None = None,
    ) -> None:
        settings = get_settings()
        self.tasks: dict[str, DiagnosisTask] = {}
        self._graph_cache: OrderedDict[str, GraphCacheEntry] = OrderedDict()
        self._graph_cache_lock = threading.RLock()
        self.graph_cache_max_size = max(settings.graph_cache_max_size, 0)
        self.graph_cache_ttl_seconds = max(settings.graph_cache_ttl_seconds, 0)
        self.repository = repository or MongoVehicleDiagnosisRepository(settings.mongo_uri, settings.mongo_database)
        self.memory = memory or self._build_memory(settings)
        self.queue = task_queue or RedisTaskQueue(settings.redis_url, settings.redis_queue_name, settings.queue_max_size)
        self.llm_config = load_llm_config(settings.llm_config_path)
        self.quick_llm, self.deep_llm = create_llm_pair(self.llm_config)
        self.worker_concurrency = max(settings.worker_concurrency, 1)
        self.task_timeout_seconds = max(settings.task_timeout_seconds, 1)
        self._workers: list[asyncio.Task[None]] = []
        self._initialized = False

    def _build_memory(self, settings: Any) -> VehicleDiagnosisMemory:
        db_path = getattr(self.repository, "db_path", None)
        if db_path is not None:
            return VehicleDiagnosisMemory(SQLiteVehicleMemoryStore(db_path))
        return VehicleDiagnosisMemory(MongoVehicleMemoryStore(settings.mongo_uri, settings.mongo_database))

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.repository.initialize()
        await self.queue.initialize()
        self._initialized = True

    async def start_workers(self) -> None:
        await self.initialize()
        if self._workers:
            return
        await self._requeue_interrupted_tasks()
        for index in range(self.worker_concurrency):
            worker = asyncio.create_task(self._worker_loop(index), name=f"vehicle-diagnosis-worker-{index}")
            self._workers.append(worker)
        logger.info("workers_started", extra={"_worker_concurrency": self.worker_concurrency})

    async def stop_workers(self) -> None:
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        await self.queue.close()
        logger.info("workers_stopped")

    async def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self.initialize()
        task_id = str(uuid4())
        task = DiagnosisTask(task_id=task_id, request=payload)
        self.tasks[task_id] = task
        await self.repository.create_task(task)
        return {"task_id": task_id, "status": task.status}

    async def submit_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await self.create_task(payload)
        await self.enqueue_task(result["task_id"])
        result["status"] = "queued"
        return result

    async def enqueue_task(self, task_id: str) -> None:
        await self.initialize()
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        if not task:
            raise ValueError(f"task not found: {task_id}")
        if task.status in {"queued", "running", "completed"}:
            return
        task.status = "queued"
        task.progress = 5
        task.current_step = "queued"
        task.queue_position = await self.queue.qsize() + 1
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self.tasks[task_id] = task
        await self.repository.save_task(task)
        await self.queue.put(task_id)
        logger.info("task_queued", extra={"_task_id": task_id, "_queue_position": task.queue_position})

    async def execute_task(self, task_id: str) -> None:
        await self.initialize()
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        if not task:
            return
        if task.status == "completed":
            logger.info("task_already_completed", extra={"_task_id": task_id})
            return
        if task.status in {"cancel_requested", "cancelled"}:
            await self._mark_cancelled(task)
            return
        now = datetime.now(timezone.utc).isoformat()
        task.status = "running"
        task.progress = 10
        task.current_step = "VehicleDiagnosisGraph"
        task.queue_position = None
        task.started_at = now
        task.updated_at = now
        self.tasks[task_id] = task
        await self.repository.save_task(task)
        logger.info("task_started", extra={"_task_id": task_id})
        try:
            graph = self._get_graph(task.request)
            loop = asyncio.get_running_loop()
            last_progress_signature: dict[str, Any] = {"value": None}

            def on_graph_progress(snapshot: dict[str, Any]) -> None:
                signature = (snapshot.get("current_node"), len(snapshot.get("graph_trace") or []))
                if signature == last_progress_signature["value"]:
                    return
                last_progress_signature["value"] = signature
                future = asyncio.run_coroutine_threadsafe(
                    self._save_progress_snapshot(task_id, snapshot),
                    loop,
                )
                try:
                    future.result(timeout=5)
                except Exception:
                    logger.exception("task_progress_update_failed", extra={"_task_id": task_id})
                cancel_future = asyncio.run_coroutine_threadsafe(self._is_cancel_requested(task_id), loop)
                try:
                    if cancel_future.result(timeout=5):
                        raise TaskCancelledDuringGraph()
                except TaskCancelledDuringGraph:
                    raise
                except Exception:
                    logger.exception("task_cancel_check_failed", extra={"_task_id": task_id})

            state, result = await asyncio.wait_for(
                asyncio.to_thread(graph.diagnose, task.request, on_graph_progress),
                timeout=self.task_timeout_seconds,
            )
            finished_at = datetime.now(timezone.utc).isoformat()
            latest_task = await self.repository.get_task(task_id)
            if latest_task and latest_task.status == "cancel_requested":
                await self._mark_cancelled(latest_task)
                return
            task.state = state
            task.result = result
            task.status = "completed"
            task.progress = 100
            task.current_step = "completed"
            task.completed_at = finished_at
            task.updated_at = finished_at
            task.error_message = None
            await self.repository.save_task(task)
            logger.info("task_completed", extra={"_task_id": task_id})
        except asyncio.TimeoutError:
            failed_at = datetime.now(timezone.utc).isoformat()
            task.status = "failed"
            task.progress = 100
            task.current_step = "timeout"
            task.error_message = f"task timed out after {self.task_timeout_seconds} seconds"
            task.completed_at = failed_at
            task.updated_at = failed_at
            await self.repository.save_task(task)
            logger.exception("task_timeout", extra={"_task_id": task_id})
        except TaskCancelledDuringGraph:
            latest_task = await self.repository.get_task(task_id)
            await self._mark_cancelled(latest_task or task)
        except Exception as exc:
            failed_at = datetime.now(timezone.utc).isoformat()
            task.status = "failed"
            task.progress = 100
            task.current_step = "failed"
            task.error_message = str(exc)
            task.completed_at = failed_at
            task.updated_at = failed_at
            await self.repository.save_task(task)
            logger.exception("task_failed", extra={"_task_id": task_id})

    async def cancel_task(self, task_id: str) -> dict[str, Any] | None:
        await self.initialize()
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        if not task:
            return None
        if task.status in {"completed", "failed", "cancelled"}:
            return {"task_id": task_id, "status": task.status, "cancelled": task.status == "cancelled"}
        if task.status in {"submitted", "queued"}:
            removed = await self.queue.remove(task_id)
            task.status = "cancelled"
            task.progress = 100
            task.current_step = "cancelled"
            task.queue_position = None
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.updated_at = task.completed_at
            self.tasks[task_id] = task
            await self.repository.save_task(task)
            logger.info("task_cancelled", extra={"_task_id": task_id, "_queue_removed": removed})
            return {"task_id": task_id, "status": task.status, "cancelled": True, "queue_removed": removed}
        if task.status == "running":
            task.status = "cancel_requested"
            task.current_step = "cancel_requested"
            task.updated_at = datetime.now(timezone.utc).isoformat()
            self.tasks[task_id] = task
            await self.repository.save_task(task)
            logger.info("task_cancel_requested", extra={"_task_id": task_id})
            return {"task_id": task_id, "status": task.status, "cancelled": False}
        return {"task_id": task_id, "status": task.status, "cancelled": False}

    async def get_status(self, task_id: str) -> dict[str, Any] | None:
        await self.initialize()
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        return task.to_status() if task else None

    async def get_result(self, task_id: str) -> dict[str, Any] | None:
        await self.initialize()
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        if not task:
            return None
        if task.status != "completed":
            return {"task_id": task_id, "status": task.status, "error_message": task.error_message}
        return task.result

    async def record_outcome(self, task_id: str, outcome: dict[str, Any]) -> dict[str, Any] | None:
        await self.initialize()
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        if not task:
            return None
        task.outcome = outcome
        task.updated_at = datetime.now(timezone.utc).isoformat()
        situation = {
            "vin": task.request.get("vin"),
            "vehicle": task.request.get("vehicle") or {},
            "symptoms": task.request.get("symptoms") or [],
            "dtc_codes": task.request.get("dtc_codes") or [],
            "telemetry_findings": (task.result or {}).get("telemetry_findings", []),
        }
        recommendation = {
            "confirmed_root_cause": outcome.get("confirmed_root_cause"),
            "repairs_performed": outcome.get("repairs_performed", []),
            "resolved": outcome.get("resolved"),
        }
        self.memory.add_case(
            situation=json.dumps(situation, ensure_ascii=False, sort_keys=True),
            recommendation=json.dumps(recommendation, ensure_ascii=False, sort_keys=True),
            metadata={"task_id": task_id, "stored_at": datetime.now(timezone.utc).isoformat()},
        )
        self.tasks[task_id] = task
        await self.repository.save_task(task)
        return {"task_id": task_id, "outcome": outcome, "stored": True}

    def _get_graph(self, payload: dict[str, Any]) -> VehicleDiagnosisGraph:
        config = self._build_graph_config(payload)
        selected_analysts = config.pop("selected_analysts")
        cache_key = json.dumps({"selected_analysts": selected_analysts, **config}, sort_keys=True)
        with self._graph_cache_lock:
            self._prune_graph_cache()
            now = time.monotonic()
            cached = self._graph_cache.get(cache_key)
            if cached is not None:
                cached.last_used_at = now
                self._graph_cache.move_to_end(cache_key)
                return cached.graph

            graph = VehicleDiagnosisGraph(
                selected_analysts=selected_analysts,
                config=config,
                quick_llm=self.quick_llm,
                deep_llm=self.deep_llm,
                memory=self.memory,
            )
            if self.graph_cache_max_size == 0:
                return graph
            self._graph_cache[cache_key] = GraphCacheEntry(graph=graph, created_at=now, last_used_at=now)
            self._prune_graph_cache()
            return graph

    def clear_graph_cache(self) -> None:
        with self._graph_cache_lock:
            self._graph_cache.clear()

    def _prune_graph_cache(self) -> None:
        if not self._graph_cache:
            return
        now = time.monotonic()
        if self.graph_cache_ttl_seconds:
            expired = [
                key
                for key, entry in self._graph_cache.items()
                if now - entry.last_used_at > self.graph_cache_ttl_seconds
            ]
            for key in expired:
                self._graph_cache.pop(key, None)
        if self.graph_cache_max_size == 0:
            self._graph_cache.clear()
            return
        while len(self._graph_cache) > self.graph_cache_max_size:
            self._graph_cache.popitem(last=False)

    async def _save_progress_snapshot(self, task_id: str, state: dict[str, Any]) -> None:
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        if not task or task.status != "running":
            return
        task.state = state
        task.current_step = state.get("current_node") or task.current_step
        task.progress = max(task.progress, self._progress_from_state(task.request, state))
        task.updated_at = datetime.now(timezone.utc).isoformat()
        self.tasks[task_id] = task
        await self.repository.save_task(task)

    async def _is_cancel_requested(self, task_id: str) -> bool:
        task = self.tasks.get(task_id) or await self.repository.get_task(task_id)
        return bool(task and task.status == "cancel_requested")

    def _progress_from_state(self, payload: dict[str, Any], state: dict[str, Any]) -> int:
        config = self._build_graph_config(payload)
        selected = config.get("selected_analysts") or []
        estimated_steps = max(
            8,
            len(selected) * 3
            + (config.get("max_debate_rounds", 1) * 2)
            + config.get("max_safety_discuss_rounds", 1)
            + 3,
        )
        trace_count = len(state.get("graph_trace") or [])
        if state.get("structured_result"):
            return 95
        return min(95, 10 + int((min(trace_count, estimated_steps) / estimated_steps) * 85))

    def _build_graph_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        parameters = payload.get("parameters") or {}
        depth = str(parameters.get("diagnosis_depth") or "standard").lower()
        config = dict(DEPTH_DEFAULTS.get(depth, DEPTH_DEFAULTS["standard"]))
        config["selected_analysts"] = parameters.get("selected_analysts") or [
            "vin_context",
            "symptom",
            "dtc",
            "telemetry",
            "knowledge",
        ]
        if parameters.get("max_debate_rounds") is not None:
            config["max_debate_rounds"] = parameters["max_debate_rounds"]
        if parameters.get("max_safety_discuss_rounds") is not None:
            config["max_safety_discuss_rounds"] = parameters["max_safety_discuss_rounds"]
        if parameters.get("max_tool_calls") is not None:
            config["max_tool_calls"] = parameters["max_tool_calls"]
        if parameters.get("analyst_max_tool_calls") is not None:
            config["analyst_max_tool_calls"] = parameters["analyst_max_tool_calls"]
        if parameters.get("tool_timeout_seconds") is not None:
            config["tool_timeout_seconds"] = parameters["tool_timeout_seconds"]
        if parameters.get("tool_max_retries") is not None:
            config["tool_max_retries"] = parameters["tool_max_retries"]
        return config

    async def _worker_loop(self, index: int) -> None:
        while True:
            task_id = await self.queue.get()
            try:
                logger.info("worker_picked_task", extra={"_worker_index": index, "_task_id": task_id})
                await self.execute_task(task_id)
            finally:
                self.queue.task_done()

    async def _requeue_interrupted_tasks(self) -> None:
        pending = await self.repository.list_tasks_by_status(["submitted", "queued", "running"])
        for task in pending:
            task.status = "submitted"
            task.current_step = "recovered"
            task.queue_position = None
            task.updated_at = datetime.now(timezone.utc).isoformat()
            self.tasks[task.task_id] = task
            await self.repository.save_task(task)
            await self.enqueue_task(task.task_id)
        if pending:
            logger.info("tasks_requeued", extra={"_task_count": len(pending)})

    async def _mark_cancelled(self, task: DiagnosisTask) -> None:
        now = datetime.now(timezone.utc).isoformat()
        task.status = "cancelled"
        task.progress = 100
        task.current_step = "cancelled"
        task.queue_position = None
        task.completed_at = now
        task.updated_at = now
        self.tasks[task.task_id] = task
        await self.repository.save_task(task)
        logger.info("task_cancelled", extra={"_task_id": task.task_id})


_service: VehicleDiagnosisService | None = None


def get_vehicle_diagnosis_service() -> VehicleDiagnosisService:
    global _service
    if _service is None:
        _service = VehicleDiagnosisService()
    return _service
