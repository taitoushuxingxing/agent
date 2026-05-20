"""Diagnostic code analyst.

The DTC agent is an objective evidence collector. It uses the subjective
agent's inspection directions to prioritize code lookup, but it does not make
the final cross-validation judgment. That arbitration belongs to Summary.
"""

from __future__ import annotations

import json
from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


def create_diagnostic_code_analyst(llm=None, toolkit=None):
    tools = [toolkit.lookup_dtc_code, toolkit.search_dtc_combinations] if toolkit is not None else []

    def diagnostic_code_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        submitted = state.get("dtc_codes") or []
        historical = [item.get("code") for item in state.get("dtc_history", []) if item.get("code")]
        symptom_report = _loads(state.get("symptom_report"), {})
        focus = _extract_upstream_focus(symptom_report)
        codes = _prioritize_codes(sorted(set(submitted + historical)), focus)
        has_tool_results = bool((state.get("analyst_tool_results") or {}).get("dtc"))

        if codes and not has_tool_results and not state.get("dtc_report"):
            llm_message = invoke_llm_tool_decision(
                llm,
                tools,
                "Diagnostic Code Analyst",
                state,
                {"dtc_codes": codes, "vehicle": state.get("vehicle") or {}, "upstream_focus": focus},
            )
            if llm_message and getattr(llm_message, "tool_calls", None):
                return {
                    "messages": [llm_message],
                    "dtc_codes": codes,
                    "current_node": "Diagnostic Code Analyst",
                    "pending_tool_owner": "dtc",
                }

            calls = [{"name": "lookup_dtc_code", "args": {"code": code}} for code in codes[:3]]
            if codes:
                calls.append({"name": "search_dtc_combinations", "args": {"codes": codes}})
            return {
                "messages": [make_tool_call_message(calls, "Diagnostic Code Analyst")],
                "dtc_codes": codes,
                "current_node": "Diagnostic Code Analyst",
                "pending_tool_owner": "dtc",
            }

        tool_results = (state.get("analyst_tool_results") or {}).get("dtc", [])
        lookups = [item.get("result") for item in tool_results if item.get("ok") and item.get("tool") == "lookup_dtc_code"]
        combinations = [
            item.get("result")
            for item in tool_results
            if item.get("ok") and item.get("tool") == "search_dtc_combinations"
        ]
        report = {
            "analyst": "Diagnostic Code Analyst",
            "role": "objective_evidence_collector",
            "conclusion": "has_dtc_evidence" if codes else "no_dtc_evidence",
            "reason": f"读取到 {', '.join(codes)}" if codes else "未提供或发现故障码",
            "upstream_focus": focus,
            "codes": codes,
            "lookups": lookups,
            "combinations": combinations[0] if combinations else [],
            "active_history": state.get("dtc_history") or [],
            "freeze_frame": state.get("freeze_frame") or {},
            "data_stream_notes": [],
            "handoff_note": "本报告只陈述 DTC/冻结帧/数据流事实，不执行最终交叉验证。",
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "dtc"],
        }
        updates = conclusion_updates(state, "Diagnostic Code Analyst", "dtc_report", report)
        updates["dtc_codes"] = codes
        return updates

    return diagnostic_code_analyst_node


def _extract_upstream_focus(symptom_report: dict[str, Any]) -> dict[str, Any]:
    suspected = symptom_report.get("suspected_fault_points") or []
    directions = symptom_report.get("inspection_directions") or []
    systems = []
    dtc_focus = []
    for item in suspected:
        if isinstance(item, dict) and item.get("system"):
            systems.append(item["system"])
    for item in directions:
        if isinstance(item, dict):
            dtc_focus.extend(item.get("suggested_dtc_focus") or [])
    return {
        "suspected_systems": _dedupe(systems),
        "suggested_dtc_focus": _dedupe([str(item) for item in dtc_focus]),
        "suspected_fault_points": suspected,
    }


def _prioritize_codes(codes: list[str], focus: dict[str, Any]) -> list[str]:
    focus_text = json.dumps(focus, ensure_ascii=False).lower()

    def score(code: str) -> tuple[int, str]:
        normalized = code.upper()
        value = 0
        if normalized.startswith("P03") and any(key in focus_text for key in ("misfire", "点火", "engine_ignition")):
            value -= 20
        if normalized in focus_text:
            value -= 10
        if normalized.startswith("P0"):
            value -= 1
        return (value, normalized)

    return sorted(_dedupe([code.upper() for code in codes]), key=score)


def _loads(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
