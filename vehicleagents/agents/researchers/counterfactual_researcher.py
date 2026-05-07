"""Counterfactual researcher."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import append_trace


def create_counterfactual_researcher(llm=None, memory=None):
    def counterfactual_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
        response = (
            "- Do not replace parts based on one DTC alone.\n"
            "- Confirm ignition, fuel, air leak, and compression evidence before final repair.\n"
            "- Check whether telemetry and event timing match the reported symptom."
        )
        debate = dict(state.get("diagnostic_debate_state") or {})
        debate["counterfactual_history"] = response
        debate["history"] = (debate.get("history") or "") + "\nCounterfactual Researcher:\n" + response
        debate["current_response"] = "Counterfactual Researcher"
        debate["count"] = debate.get("count", 0) + 1
        updates = append_trace(state, "Counterfactual Researcher", "completed")
        updates["diagnostic_debate_state"] = debate
        return updates

    return counterfactual_researcher_node
