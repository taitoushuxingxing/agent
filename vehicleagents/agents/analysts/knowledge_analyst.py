"""Knowledge/RAG analyst."""

from __future__ import annotations

import json
from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


def create_knowledge_analyst(llm=None, toolkit=None):
    tools = [toolkit.retrieve_repair_cases] if toolkit is not None else []

    def knowledge_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        query = _build_rag_query(state)
        has_tool_results = bool((state.get("analyst_tool_results") or {}).get("knowledge"))
        if not has_tool_results and not state.get("knowledge_report"):
            llm_message = invoke_llm_tool_decision(
                llm,
                tools,
                "Knowledge Analyst",
                state,
                query,
            )
            if llm_message and getattr(llm_message, "tool_calls", None):
                return {"messages": [llm_message], "current_node": "Knowledge Analyst", "pending_tool_owner": "knowledge"}
            return {
                "messages": [
                    make_tool_call_message(
                        [{"name": "retrieve_repair_cases", "args": {"query": query}}],
                        "Knowledge Analyst",
                    )
                ],
                "current_node": "Knowledge Analyst",
                "pending_tool_owner": "knowledge",
            }

        cases = [
            item.get("result")
            for item in (state.get("analyst_tool_results") or {}).get("knowledge", [])
            if item.get("ok") and item.get("tool") == "retrieve_repair_cases"
        ]
        case_count = sum(len(item) for item in cases if isinstance(item, list))
        report = {
            "analyst": "Knowledge Analyst",
            "role": "rag_reference_retriever",
            "conclusion": "has_references" if case_count else "no_references",
            "reason": f"检索到 {case_count} 条维修手册/案例参考" if case_count else "知识库未命中相似资料",
            "query": query,
            "repair_references": cases,
            "case_count": case_count,
            "knowledge_sources": ["vehicle_manuals", "repair_cases"],
            "handoff_note": "本报告只提供维修知识参考，不执行最终判断。",
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "knowledge"],
        }
        return conclusion_updates(state, "Knowledge Analyst", "knowledge_report", report)

    return knowledge_analyst_node


def _build_rag_query(state: dict[str, Any]) -> dict[str, Any]:
    symptom_report = _loads(state.get("symptom_report"), {})
    dtc_report = _loads(state.get("dtc_report"), {})
    return {
        "vehicle": state.get("vehicle") or {},
        "symptoms": state.get("symptoms") or [],
        "semantic_standardization": symptom_report.get("semantic_standardization") or {},
        "suspected_fault_points": symptom_report.get("suspected_fault_points") or [],
        "inspection_directions": symptom_report.get("inspection_directions") or [],
        "dtc_codes": dtc_report.get("codes") or state.get("dtc_codes") or [],
        "dtc_lookups": dtc_report.get("lookups") or [],
        "freeze_frame": dtc_report.get("freeze_frame") or state.get("freeze_frame") or {},
        "retrieval_goal": (
            "查找该车型在上述主观现象和 DTC/数据流条件下的维修手册步骤、"
            "技术公告、召回通病和已确认维修案例。"
        ),
    }


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
