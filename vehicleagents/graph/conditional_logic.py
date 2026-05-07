"""Conditional logic for graph routing."""

from __future__ import annotations

from typing import Any


class VehicleConditionalLogic:
    def __init__(
        self,
        max_tool_calls: int | dict[str, int] = 2,
        max_debate_rounds: int = 1,
        max_safety_discuss_rounds: int = 1,
    ) -> None:
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
        count_key = f"{analyst_key}_tool_call_count"
        max_tool_calls = self.max_tool_calls_for(analyst_key)
        if self._last_message_has_tool_calls(state) and state.get(count_key, 0) < max_tool_calls:
            return f"tools_{analyst_key}"
        if state.get(count_key, 0) >= max_tool_calls:
            return f"Msg Clear {node_title}"
        return f"Msg Clear {node_title}"

    def max_tool_calls_for(self, analyst_key: str) -> int:
        if isinstance(self.max_tool_calls, dict):
            return int(self.max_tool_calls.get(analyst_key, self.max_tool_calls.get("default", 2)))
        return int(self.max_tool_calls)

    def _last_message_has_tool_calls(self, state: dict[str, Any]) -> bool:
        messages = state.get("messages") or []
        if not messages:
            return False
        return bool(getattr(messages[-1], "tool_calls", None))

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
