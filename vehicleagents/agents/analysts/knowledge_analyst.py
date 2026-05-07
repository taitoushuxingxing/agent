"""Knowledge analyst."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


def create_knowledge_analyst(llm=None, toolkit=None):
    tools = [toolkit.retrieve_repair_cases] if toolkit is not None else []

    def knowledge_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        query = {
            "vehicle": state.get("vehicle") or {},
            "symptoms": state.get("symptoms") or [],
            "dtc_codes": state.get("dtc_codes") or [],
            "telemetry_report": state.get("telemetry_report") or "",
        }
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
        report = {
            "analyst": "Knowledge Analyst",
            "conclusion": "有问题" if cases else "无问题",
            "reason": f"检索到 {sum(len(item) for item in cases if isinstance(item, list))} 个相似案例" if cases else "知识库未命中相似案例",
            "similar_cases": cases,
            "case_count": sum(len(item) for item in cases if isinstance(item, list)),
            "knowledge_sources": ["local_dtc", "local_cases"],
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "knowledge"],
        }
        return conclusion_updates(state, "Knowledge Analyst", "knowledge_report", report)

    return knowledge_analyst_node
