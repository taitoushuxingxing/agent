import asyncio
import json
import time

from langchain_core.messages import AIMessage
import pytest

from app.core.llm_config import load_llm_config
from app.core.llm_client import create_llm_pair
from app.repositories.vehicle_diagnosis_repository import VehicleDiagnosisRepository
from app.schemas.vehicle_diagnosis import DiagnosisParameters
from app.services.vehicle_diagnosis_service import VehicleDiagnosisService
from app.queues.task_queue import InMemoryTaskQueue
from vehicleagents.dataflows import interface
from vehicleagents.dataflows.providers.mongo_client import get_data_provider_mode, get_database
from vehicleagents.graph import VehicleDiagnosisGraph


class FakePlannerLLM:
    def invoke(self, prompt: str) -> str:
        return json.dumps(
            {
                "summary": "LLM synthesized ignition fault.",
                "ranked_hypotheses": [
                    {
                        "rank": 1,
                        "fault": "LLM synthesized ignition fault",
                        "probability": 0.71,
                        "evidence_for": ["P0301"],
                        "evidence_against": [],
                    }
                ],
                "inspection_plan": ["Run coil swap test."],
                "confidence_score": 0.71,
            }
        )


class FakeToolCallingLLM:
    def bind_tools(self, tools):
        return self

    def invoke(self, prompt: str):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "lookup_dtc_code",
                    "args": {"code": "P0301"},
                    "id": "fake-tool-call",
                }
            ],
        )


def test_graph_smoke():
    graph = VehicleDiagnosisGraph()
    _, result = graph.diagnose(
        {
            "vin": "LFV3A23C0J3000001",
            "symptoms": [{"name": "rough idle", "severity": "medium"}],
            "dtc_codes": ["P0301", "P0171"],
        }
    )
    assert result["vin"] == "LFV3A23C0J3000001"
    assert result["ranked_hypotheses"]


def test_graph_respects_selected_analysts():
    graph = VehicleDiagnosisGraph(selected_analysts=["dtc"])
    state, result = graph.diagnose(
        {
            "vin": "LFV3A23C0J3000001",
            "dtc_codes": ["P0301"],
        }
    )

    assert state["dtc_report"]
    assert state["vehicle_profile_report"] == ""
    assert result["ranked_hypotheses"][0]["fault"] == "Cylinder 1 ignition system fault"


def test_graph_records_tool_flow_and_cleans_messages():
    graph = VehicleDiagnosisGraph(selected_analysts=["dtc"])
    state, _ = graph.diagnose({"dtc_codes": ["P0301"]})

    assert state["dtc_tool_call_count"] == 2
    assert any(item["node"] == "tools_dtc" for item in state["graph_trace"])
    assert state["analyst_conclusions"]["Diagnostic Code Analyst"].startswith("has_dtc_evidence")
    assert [message.content for message in state["messages"]] == [
        f"[Diagnostic Code Analyst: {state['analyst_conclusions']['Diagnostic Code Analyst']}]"
    ]


def test_graph_continues_when_tool_fails(monkeypatch):
    def fail_lookup(*args, **kwargs):
        raise RuntimeError("dtc backend unavailable")

    monkeypatch.setattr(interface, "lookup_dtc_code", fail_lookup)

    graph = VehicleDiagnosisGraph(selected_analysts=["dtc"])
    state, result = graph.diagnose({"dtc_codes": ["P0301"]})

    assert state["tool_errors"]
    assert state["dtc_report"]
    assert result["ranked_hypotheses"]


def test_graph_retries_transient_tool_failure(monkeypatch):
    original_lookup = interface.lookup_dtc_code
    calls = {"count": 0}

    def flaky_lookup(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary dtc backend error")
        return original_lookup(*args, **kwargs)

    monkeypatch.setattr(interface, "lookup_dtc_code", flaky_lookup)

    graph = VehicleDiagnosisGraph(
        selected_analysts=["dtc"],
        config={"tool_max_retries": 1},
    )
    state, _ = graph.diagnose({"dtc_codes": ["P0301"]})

    assert calls["count"] == 2
    assert not state["tool_errors"]


def test_graph_uses_llm_tool_call_decision():
    graph = VehicleDiagnosisGraph(selected_analysts=["dtc"], quick_llm=FakeToolCallingLLM())
    state, _ = graph.diagnose({"dtc_codes": ["P0301"]})

    assert state["dtc_tool_call_count"] == 1
    assert state["analyst_tool_results"]["dtc"][0]["tool"] == "lookup_dtc_code"
    assert state["analyst_conclusions"]["Diagnostic Code Analyst"].startswith("has_dtc_evidence")


def test_graph_respects_per_analyst_tool_limit():
    graph = VehicleDiagnosisGraph(
        selected_analysts=["dtc"],
        config={"analyst_max_tool_calls": {"dtc": 1}},
    )
    state, _ = graph.diagnose({"dtc_codes": ["P0301"]})

    assert state["dtc_tool_call_count"] == 1
    assert state["tool_errors"][0]["error"] == "max_tool_calls exceeded for dtc"


def test_graph_uses_llm_summary_when_available():
    graph = VehicleDiagnosisGraph(selected_analysts=["dtc"], deep_llm=FakePlannerLLM())
    _, result = graph.diagnose({"dtc_codes": ["P0301"]})

    assert result["ranked_hypotheses"][0]["fault"] == "LLM synthesized ignition fault"
    assert result["confidence_score"] == 0.71


def test_diagnosis_parameters_validate_supported_analysts():
    with pytest.raises(ValueError):
        DiagnosisParameters(selected_analysts=["unknown"])


def test_llm_config_can_be_overridden_by_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_LLM_ENABLED", "true")
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_LLM_QUICK_PROVIDER", "deepseek")
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_LLM_QUICK_MODEL", "deepseek-chat")
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_LLM_QUICK_API_KEY_ENV", "DEEPSEEK_API_KEY")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    config = load_llm_config(tmp_path / "missing.json")

    assert config.enabled is True
    assert config.quick.provider == "deepseek"
    assert config.quick.model == "deepseek-chat"
    assert config.quick.api_key == "test-key"


def test_llm_client_pair_created_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_LLM_ENABLED", "true")
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_LLM_QUICK_API_KEY_ENV", "OPENAI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = load_llm_config(tmp_path / "missing.json")

    quick_llm, deep_llm = create_llm_pair(config)

    assert quick_llm is not None
    assert deep_llm is not None


def test_data_provider_mock_mode_skips_mongo(monkeypatch):
    monkeypatch.setenv("VEHICLE_DIAGNOSIS_DATA_PROVIDER", "mock")
    get_database.cache_clear()

    assert get_data_provider_mode() == "mock"
    assert get_database() is None


def test_service_executes_depth_config_and_stores_outcome(tmp_path):
    async def run_case():
        repository = VehicleDiagnosisRepository(tmp_path / "diagnosis.sqlite3")
        service = VehicleDiagnosisService(repository=repository, task_queue=InMemoryTaskQueue())
        created = await service.create_task(
            {
                "vin": "LFV3A23C0J3000001",
                "dtc_codes": ["P0301"],
                "parameters": {
                    "selected_analysts": ["dtc"],
                    "diagnosis_depth": "standard",
                },
            }
        )
        task_id = created["task_id"]
        await service.execute_task(task_id)
        status = await service.get_status(task_id)
        result = await service.get_result(task_id)
        outcome = await service.record_outcome(
            task_id,
            {
                "confirmed_root_cause": "cylinder 1 ignition coil failure",
                "repairs_performed": ["replace ignition coil"],
                "resolved": True,
            },
        )

        assert status["status"] == "completed"
        assert result["ranked_hypotheses"]
        assert outcome["stored"] is True
        assert service.memory.get_memories("rough idle")

    asyncio.run(run_case())


def test_service_graph_cache_prunes_by_size_and_can_clear(tmp_path):
    service = VehicleDiagnosisService(
        repository=VehicleDiagnosisRepository(tmp_path / "diagnosis.sqlite3"),
        task_queue=InMemoryTaskQueue(),
    )
    service.graph_cache_max_size = 1

    first = service._get_graph({"parameters": {"selected_analysts": ["dtc"]}})
    second = service._get_graph({"parameters": {"selected_analysts": ["symptom"]}})

    assert first is not second
    assert len(service._graph_cache) == 1
    service.clear_graph_cache()
    assert len(service._graph_cache) == 0


def test_service_persists_completed_task_across_instances(tmp_path):
    async def run_case():
        db_path = tmp_path / "diagnosis.sqlite3"
        service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(db_path),
            task_queue=InMemoryTaskQueue(),
        )
        created = await service.create_task(
            {
                "vin": "LFV3A23C0J3000001",
                "dtc_codes": ["P0301"],
                "parameters": {"selected_analysts": ["dtc"]},
            }
        )
        task_id = created["task_id"]
        await service.execute_task(task_id)

        restarted_service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(db_path),
            task_queue=InMemoryTaskQueue(),
        )
        status = await restarted_service.get_status(task_id)
        result = await restarted_service.get_result(task_id)

        assert status["status"] == "completed"
        assert status["current_node"] == "Summary Agent"
        assert status["graph_trace"]
        assert result["vin"] == "LFV3A23C0J3000001"
        assert result["ranked_hypotheses"][0]["fault"] == "Cylinder 1 ignition system fault"

    asyncio.run(run_case())


def test_service_queue_worker_executes_task(tmp_path):
    async def run_case():
        service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(tmp_path / "diagnosis.sqlite3"),
            task_queue=InMemoryTaskQueue(),
        )
        await service.start_workers()
        try:
            created = await service.submit_task(
                {
                    "vin": "LFV3A23C0J3000001",
                    "dtc_codes": ["P0301"],
                    "parameters": {"selected_analysts": ["dtc"]},
                }
            )
            task_id = created["task_id"]
            await service.queue.join()
            status = await service.get_status(task_id)
            result = await service.get_result(task_id)

            assert created["status"] == "queued"
            assert status["status"] == "completed"
            assert result["ranked_hypotheses"]
        finally:
            await service.stop_workers()

    asyncio.run(run_case())


def test_service_updates_status_while_graph_is_running(monkeypatch, tmp_path):
    original_lookup = interface.lookup_dtc_code

    def slow_lookup(*args, **kwargs):
        time.sleep(0.25)
        return original_lookup(*args, **kwargs)

    monkeypatch.setattr(interface, "lookup_dtc_code", slow_lookup)

    async def run_case():
        service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(tmp_path / "diagnosis.sqlite3"),
            task_queue=InMemoryTaskQueue(),
        )
        created = await service.create_task(
            {
                "dtc_codes": ["P0301"],
                "parameters": {"selected_analysts": ["dtc"]},
            }
        )
        task_id = created["task_id"]
        running = asyncio.create_task(service.execute_task(task_id))
        observed = False
        for _ in range(50):
            await asyncio.sleep(0.02)
            status = await service.get_status(task_id)
            if status and status["status"] == "running" and status["current_node"] != "VehicleDiagnosisGraph":
                observed = True
                break
        await running

        assert observed

    asyncio.run(run_case())


def test_service_can_cancel_running_task_during_graph_stream(monkeypatch, tmp_path):
    original_lookup = interface.lookup_dtc_code

    def slow_lookup(*args, **kwargs):
        time.sleep(0.25)
        return original_lookup(*args, **kwargs)

    monkeypatch.setattr(interface, "lookup_dtc_code", slow_lookup)

    async def run_case():
        service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(tmp_path / "diagnosis.sqlite3"),
            task_queue=InMemoryTaskQueue(),
        )
        created = await service.create_task(
            {
                "dtc_codes": ["P0301"],
                "parameters": {"selected_analysts": ["dtc"]},
            }
        )
        task_id = created["task_id"]
        running = asyncio.create_task(service.execute_task(task_id))
        for _ in range(50):
            await asyncio.sleep(0.02)
            status = await service.get_status(task_id)
            if status and status["status"] == "running" and status["current_node"] != "VehicleDiagnosisGraph":
                break
        cancel_result = await service.cancel_task(task_id)
        await running
        status = await service.get_status(task_id)

        assert cancel_result["status"] == "cancel_requested"
        assert status["status"] == "cancelled"

    asyncio.run(run_case())


def test_service_can_cancel_queued_task(tmp_path):
    async def run_case():
        service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(tmp_path / "diagnosis.sqlite3"),
            task_queue=InMemoryTaskQueue(),
        )
        created = await service.submit_task(
            {
                "vin": "LFV3A23C0J3000001",
                "dtc_codes": ["P0301"],
                "parameters": {"selected_analysts": ["dtc"]},
            }
        )
        result = await service.cancel_task(created["task_id"])
        status = await service.get_status(created["task_id"])

        assert result["cancelled"] is True
        assert status["status"] == "cancelled"

    asyncio.run(run_case())


def test_memory_persists_feedback_across_service_instances(tmp_path):
    async def run_case():
        db_path = tmp_path / "diagnosis.sqlite3"
        service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(db_path),
            task_queue=InMemoryTaskQueue(),
        )
        created = await service.create_task(
            {
                "vin": "LFV3A23C0J3000001",
                "symptoms": [{"name": "rough idle", "severity": "medium"}],
                "dtc_codes": ["P0301"],
                "parameters": {"selected_analysts": ["dtc"]},
            }
        )
        task_id = created["task_id"]
        await service.execute_task(task_id)
        await service.record_outcome(
            task_id,
            {
                "confirmed_root_cause": "cylinder 1 ignition coil failure",
                "repairs_performed": ["replace ignition coil"],
                "resolved": True,
            },
        )

        restarted_service = VehicleDiagnosisService(
            repository=VehicleDiagnosisRepository(db_path),
            task_queue=InMemoryTaskQueue(),
        )
        memories = restarted_service.memory.get_memories("rough idle P0301 ignition coil", n_matches=1)

        assert memories
        assert "ignition coil failure" in memories[0]["recommendation"]

    asyncio.run(run_case())
