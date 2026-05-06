"""Diagnostic code analyst."""

from __future__ import annotations

import json
from typing import Any

from ...dataflows import interface


def create_diagnostic_code_analyst(llm=None, toolkit=None):
    def diagnostic_code_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        submitted = state.get("dtc_codes") or []
        historical = [item.get("code") for item in state.get("dtc_history", []) if item.get("code")]
        codes = sorted(set(submitted + historical))
        lookups = [interface.lookup_dtc_code(code, state.get("vehicle") or {}) for code in codes]
        combinations = interface.search_dtc_combinations(codes)
        report = {
            "codes": codes,
            "lookups": lookups,
            "combinations": combinations,
            "active_history": state.get("dtc_history") or [],
        }
        return {
            "dtc_codes": codes,
            "dtc_report": json.dumps(report, ensure_ascii=False, indent=2),
            "dtc_tool_call_count": state.get("dtc_tool_call_count", 0) + 1,
        }

    return diagnostic_code_analyst_node

