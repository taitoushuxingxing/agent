"""Conditional logic for graph routing."""

from __future__ import annotations

from typing import Any


class VehicleConditionalLogic:
    def __init__(self, max_tool_calls: int = 2, max_debate_rounds: int = 1, max_safety_discuss_rounds: int = 1) -> None:
        self.max_tool_calls = max_tool_calls
        self.max_debate_rounds = max_debate_rounds
        self.max_safety_discuss_rounds = max_safety_discuss_rounds

    def should_continue_vin_context(self, state: dict[str, Any]) -> str:
        return self._analyst_next(state, "vin_context", "VIN Context")

    def should_continue_symptom(self, state: dict[str, Any]) -> str:
        return self._analyst_next(state, "symptom", "Symptom")

    def should_continue_dtc(self, state: dict[str, Any]) -> str:
        return self._analyst_next(state, "dtc", "Diagnostic Code")

    def should_continue_telemetry(self, state: dict[str, Any]) -> str:
        return self._analyst_next(state, "telemetry", "Telemetry")

    def should_continue_knowledge(self, state: dict[str, Any]) -> str:
        return self._analyst_next(state, "knowledge", "Knowledge")

    def _analyst_next(self, state: dict[str, Any], analyst_key: str, node_title: str) -> str:
        report_key = {
            "vin_context": "vehicle_profile_report",
            "symptom": "symptom_report",
            "dtc": "dtc_report",
            "telemetry": "telemetry_report",
            "knowledge": "knowledge_report",
        }[analyst_key]
        count_key = f"{analyst_key}_tool_call_count"
        if len(state.get(report_key, "")) > 20:
            return f"Msg Clear {node_title}"
        if state.get(count_key, 0) >= self.max_tool_calls:
            return f"Msg Clear {node_title}"
        return f"Msg Clear {node_title}"

    def should_continue_debate(self, state: dict[str, Any]) -> str:
        count = state.get("diagnostic_debate_state", {}).get("count", 0)
        if count >= 2 * self.max_debate_rounds:
            return "Diagnostic Planner"
        speaker = state.get("diagnostic_debate_state", {}).get("current_response", "")
        return "Counterfactual Researcher" if speaker == "Hypothesis Researcher" else "Hypothesis Researcher"

    def should_continue_safety(self, state: dict[str, Any]) -> str:
        count = state.get("safety_review_state", {}).get("count", 0)
        if count >= self.max_safety_discuss_rounds:
            return "Safety Judge"
        return "Repair Advisor"
