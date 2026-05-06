"""Safety analyst."""

from __future__ import annotations

from typing import Any


def create_safety_analyst(llm=None):
    def safety_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        codes = set(state.get("dtc_codes") or [])
        level = "medium" if codes.intersection({"P0300", "P0301"}) else "low"
        response = f"Safety level: {level}. Stop driving if MIL flashes, vibration worsens, fuel smell appears, or overheating occurs."
        safety = dict(state.get("safety_review_state") or {})
        safety["safety_history"] = response
        safety["latest_speaker"] = "Safety Analyst"
        safety["count"] = safety.get("count", 0) + 1
        return {"safety_review_state": safety}

    return safety_analyst_node

