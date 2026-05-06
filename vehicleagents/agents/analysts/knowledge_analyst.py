"""Knowledge analyst."""

from __future__ import annotations

import json
from typing import Any

from ...dataflows import interface


def create_knowledge_analyst(llm=None, toolkit=None):
    def knowledge_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        query = {
            "vehicle": state.get("vehicle") or {},
            "symptoms": state.get("symptoms") or [],
            "dtc_codes": state.get("dtc_codes") or [],
            "telemetry_report": state.get("telemetry_report") or "",
        }
        cases = interface.retrieve_repair_cases(query)
        report = {
            "similar_cases": cases,
            "case_count": len(cases),
            "knowledge_sources": ["local_dtc", "local_cases"],
        }
        return {
            "knowledge_report": json.dumps(report, ensure_ascii=False, indent=2),
            "knowledge_tool_call_count": state.get("knowledge_tool_call_count", 0) + 1,
        }

    return knowledge_analyst_node

