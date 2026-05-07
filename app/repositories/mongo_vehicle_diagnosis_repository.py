"""MongoDB persistence for diagnosis tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from app.models.vehicle_diagnosis import DiagnosisTask


class MongoVehicleDiagnosisRepository:
    def __init__(self, mongo_uri: str, database: str) -> None:
        self.mongo_uri = mongo_uri
        self.database_name = database
        self._client: Any = None
        self._collection: Any = None

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def create_task(self, task: DiagnosisTask) -> None:
        await asyncio.to_thread(self._create_task_sync, task)

    async def save_task(self, task: DiagnosisTask) -> None:
        await asyncio.to_thread(self._save_task_sync, task)

    async def get_task(self, task_id: str) -> DiagnosisTask | None:
        return await asyncio.to_thread(self._get_task_sync, task_id)

    async def list_tasks_by_status(self, statuses: list[str]) -> list[DiagnosisTask]:
        return await asyncio.to_thread(self._list_tasks_by_status_sync, statuses)

    def _initialize_sync(self) -> None:
        from pymongo import ASCENDING, MongoClient

        if self._client is None:
            self._client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self._client.admin.command("ping")
            database = self._client[self.database_name]
            self._collection = database.vehicle_diagnosis_tasks
            self._collection.create_index([("task_id", ASCENDING)], unique=True)
            self._collection.create_index([("status", ASCENDING)])
            self._collection.create_index([("created_at", ASCENDING)])

    def _create_task_sync(self, task: DiagnosisTask) -> None:
        self._collection.insert_one(_task_to_document(task))

    def _save_task_sync(self, task: DiagnosisTask) -> None:
        self._collection.update_one(
            {"task_id": task.task_id},
            {"$set": _task_to_document(task)},
            upsert=True,
        )

    def _get_task_sync(self, task_id: str) -> DiagnosisTask | None:
        document = self._collection.find_one({"task_id": task_id})
        return _document_to_task(document) if document else None

    def _list_tasks_by_status_sync(self, statuses: list[str]) -> list[DiagnosisTask]:
        documents = self._collection.find({"status": {"$in": statuses}}).sort("created_at", 1)
        return [_document_to_task(document) for document in documents]


def _task_to_document(task: DiagnosisTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "request": task.request,
        "status": task.status,
        "progress": task.progress,
        "current_step": task.current_step,
        "queue_position": task.queue_position,
        "result": task.result,
        "state": _json_safe(task.state),
        "outcome": task.outcome,
        "error_message": task.error_message,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
    }


def _document_to_task(document: dict[str, Any]) -> DiagnosisTask:
    return DiagnosisTask(
        task_id=document["task_id"],
        request=document.get("request") or {},
        status=document.get("status", "submitted"),
        progress=document.get("progress", 0),
        current_step=document.get("current_step", "submitted"),
        queue_position=document.get("queue_position"),
        result=document.get("result"),
        state=document.get("state"),
        outcome=document.get("outcome"),
        error_message=document.get("error_message"),
        created_at=document.get("created_at"),
        updated_at=document.get("updated_at"),
        started_at=document.get("started_at"),
        completed_at=document.get("completed_at"),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "type") and hasattr(value, "content"):
        data = {"type": getattr(value, "type", value.__class__.__name__), "content": value.content}
        tool_calls = getattr(value, "tool_calls", None)
        if tool_calls:
            data["tool_calls"] = _json_safe(tool_calls)
        tool_call_id = getattr(value, "tool_call_id", None)
        if tool_call_id:
            data["tool_call_id"] = tool_call_id
        message_id = getattr(value, "id", None)
        if message_id:
            data["id"] = message_id
        return data
    return str(value)
