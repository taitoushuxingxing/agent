"""Symptom analyst."""

from __future__ import annotations

import json
from typing import Any


def create_symptom_analyst(llm=None, toolkit=None):
    def symptom_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        symptoms = state.get("symptoms") or []
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        max_severity = "unknown"
        if symptoms:
            max_severity = max(
                (item.get("severity", "unknown") for item in symptoms),
                key=lambda level: severity_order.get(level, 0),
            )
        report = {
            "symptom_count": len(symptoms),
            "max_severity": max_severity,
            "symptoms": symptoms,
            "primary_complaint": symptoms[0].get("name") if symptoms else state.get("user_question", ""),
        }
        return {
            "symptom_report": json.dumps(report, ensure_ascii=False, indent=2),
            "symptom_tool_call_count": state.get("symptom_tool_call_count", 0) + 1,
        }

    return symptom_analyst_node

