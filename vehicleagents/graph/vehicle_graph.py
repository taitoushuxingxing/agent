"""Main vehicle diagnosis graph facade."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from vehicleagents.agents.utils.agent_states import build_initial_state
from vehicleagents.agents.utils.memory import VehicleDiagnosisMemory
from vehicleagents.default_config import DEFAULT_VEHICLE_CONFIG
from vehicleagents.graph.conditional_logic import VehicleConditionalLogic
from vehicleagents.graph.setup import VehicleGraphSetup
from vehicleagents.graph.signal_processing import VehicleSignalProcessor

DEFAULT_ANALYSTS = ["vin_context", "symptom", "dtc", "knowledge", "experience"]


class VehicleDiagnosisGraph:
    """Orchestrates the vehicle fault diagnosis workflow."""

    def __init__(
        self,
        selected_analysts: list[str] | None = None,
        config: dict[str, Any] | None = None,
        quick_llm: Any = None,
        deep_llm: Any = None,
        memory: VehicleDiagnosisMemory | None = None,
    ) -> None:
        self.config = DEFAULT_VEHICLE_CONFIG.copy()
        if config:
            self.config.update(config)
        self.selected_analysts = (
            selected_analysts
            if selected_analysts is not None
            else self.config.get("selected_analysts", DEFAULT_ANALYSTS)
        )
        self.quick_llm = quick_llm
        self.deep_llm = deep_llm
        self.memory = memory or VehicleDiagnosisMemory()
        self.conditional_logic = VehicleConditionalLogic(
            max_tool_calls=self.config.get("analyst_max_tool_calls", self.config.get("max_tool_calls", 2)),
        )
        self.signal_processor = VehicleSignalProcessor()
        self.graph = VehicleGraphSetup(
            quick_llm=self.quick_llm,
            deep_llm=self.deep_llm,
            conditional_logic=self.conditional_logic,
            memory=self.memory,
            config=self.config,
        ).setup_graph(self.selected_analysts)

    def diagnose(
        self,
        payload: dict[str, Any],
        progress_callback: Any | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        diagnosis_id = payload.get("diagnosis_id") or str(uuid4())
        case_date = payload.get("case_date") or datetime.now(timezone.utc).isoformat()
        state = build_initial_state(payload, diagnosis_id=diagnosis_id, case_date=case_date)
        if progress_callback is None:
            final_state = self.graph.invoke(state)
        else:
            final_state = state
            for snapshot in self.graph.stream(state, stream_mode="values"):
                final_state = snapshot
                progress_callback(snapshot)
        result = self.signal_processor.process_result(final_state)
        return final_state, result
