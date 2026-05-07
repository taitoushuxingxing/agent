"""Symptom analyst."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


def create_symptom_analyst(llm=None, toolkit=None):
    tools = [toolkit.retrieve_repair_cases] if toolkit is not None else []

    def symptom_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        symptoms = state.get("symptoms") or []
        has_tool_results = bool((state.get("analyst_tool_results") or {}).get("symptom"))
        if symptoms and not has_tool_results and not state.get("symptom_report"):
            query = {
                "symptoms": symptoms,
                "dtc_codes": state.get("dtc_codes") or [],
                "vehicle": state.get("vehicle") or {},
            }
            llm_message = invoke_llm_tool_decision(
                llm,
                tools,
                "Symptom Analyst",
                state,
                {"symptoms": symptoms, "user_question": state.get("user_question", "")},
            )
            if llm_message and getattr(llm_message, "tool_calls", None):
                return {"messages": [llm_message], "current_node": "Symptom Analyst", "pending_tool_owner": "symptom"}
            return {
                "messages": [
                    make_tool_call_message(
                        [{"name": "retrieve_repair_cases", "args": {"query": query}}],
                        "Symptom Analyst",
                    )
                ],
                "current_node": "Symptom Analyst",
                "pending_tool_owner": "symptom",
            }

        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        max_severity = "unknown"
        if symptoms:
            max_severity = max(
                (item.get("severity", "unknown") for item in symptoms),
                key=lambda level: severity_order.get(level, 0),
            )
        similar_cases = [
            item.get("result")
            for item in (state.get("analyst_tool_results") or {}).get("symptom", [])
            if item.get("ok") and item.get("tool") == "retrieve_repair_cases"
        ]
        report = {
            "analyst": "Symptom Analyst",
            "conclusion": "有问题" if symptoms else "无问题",
            "reason": f"用户报告 {len(symptoms)} 个症状，最高严重度 {max_severity}" if symptoms else "未提供明确故障现象",
            "symptom_count": len(symptoms),
            "max_severity": max_severity,
            "symptoms": symptoms,
            "primary_complaint": symptoms[0].get("name") if symptoms else state.get("user_question", ""),
            "similar_cases": similar_cases,
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "symptom"],
        }
        return conclusion_updates(state, "Symptom Analyst", "symptom_report", report)

    return symptom_analyst_node
