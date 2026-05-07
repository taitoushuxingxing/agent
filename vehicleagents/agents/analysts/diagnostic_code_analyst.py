"""Diagnostic code analyst."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


def create_diagnostic_code_analyst(llm=None, toolkit=None):
    tools = [toolkit.lookup_dtc_code, toolkit.search_dtc_combinations] if toolkit is not None else []

    def diagnostic_code_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        submitted = state.get("dtc_codes") or []
        historical = [item.get("code") for item in state.get("dtc_history", []) if item.get("code")]
        codes = sorted(set(submitted + historical))
        has_tool_results = bool((state.get("analyst_tool_results") or {}).get("dtc"))
        if codes and not has_tool_results and not state.get("dtc_report"):
            llm_message = invoke_llm_tool_decision(
                llm,
                tools,
                "Diagnostic Code Analyst",
                state,
                {"dtc_codes": codes, "vehicle": state.get("vehicle") or {}},
            )
            if llm_message and getattr(llm_message, "tool_calls", None):
                return {"messages": [llm_message], "dtc_codes": codes, "current_node": "Diagnostic Code Analyst", "pending_tool_owner": "dtc"}
            calls = [{"name": "lookup_dtc_code", "args": {"code": code}} for code in codes[:2]]
            if len(calls) < 2:
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
            "conclusion": "有问题" if codes else "无问题",
            "reason": f"检测到 {', '.join(codes)}" if codes else "未提供或发现故障码",
            "codes": codes,
            "lookups": lookups,
            "combinations": combinations[0] if combinations else [],
            "active_history": state.get("dtc_history") or [],
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "dtc"],
        }
        updates = conclusion_updates(state, "Diagnostic Code Analyst", "dtc_report", report)
        updates["dtc_codes"] = codes
        return updates

    return diagnostic_code_analyst_node
