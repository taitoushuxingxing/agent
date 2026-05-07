"""Hypothesis researcher."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import append_trace


def create_hypothesis_researcher(llm=None, memory=None):
    def hypothesis_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
        codes = state.get("dtc_codes") or []
        hypotheses = []
        if "P0301" in codes:
            hypotheses.append("Cylinder 1 ignition, spark plug, injector, or compression fault.")
        if "P0171" in codes:
            hypotheses.append("Lean condition from intake leak, MAF error, or fuel delivery problem.")
        if not hypotheses:
            hypotheses.append("Insufficient evidence; start from symptom-guided inspection.")
        response = "\n".join(f"- {item}" for item in hypotheses)
        debate = dict(state.get("diagnostic_debate_state") or {})
        debate["hypothesis_history"] = response
        debate["history"] = (debate.get("history") or "") + "\nHypothesis Researcher:\n" + response
        debate["current_response"] = "Hypothesis Researcher"
        debate["count"] = debate.get("count", 0) + 1
        updates = append_trace(state, "Hypothesis Researcher", "completed")
        updates["diagnostic_debate_state"] = debate
        return updates

    return hypothesis_researcher_node
