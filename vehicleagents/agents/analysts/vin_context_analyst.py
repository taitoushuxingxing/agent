"""VIN context analyst."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


def create_vin_context_analyst(llm=None, toolkit=None):
    tools = [
        toolkit.get_vehicle_profile_by_vin,
        toolkit.get_dtc_history_by_vin,
        toolkit.get_maintenance_history_by_vin,
    ] if toolkit is not None else []

    def vin_context_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        vin = state.get("vin") or state.get("vehicle", {}).get("vin") or ""
        vehicle = dict(state.get("vehicle") or {})
        has_tool_results = bool((state.get("analyst_tool_results") or {}).get("vin_context"))
        if vin and not has_tool_results and not state.get("vehicle_profile_report"):
            llm_message = invoke_llm_tool_decision(
                llm,
                tools,
                "VIN Context Analyst",
                state,
                {"vin": vin, "vehicle": vehicle, "dtc_history": state.get("dtc_history") or []},
            )
            if llm_message and getattr(llm_message, "tool_calls", None):
                return {"messages": [llm_message], "current_node": "VIN Context Analyst", "pending_tool_owner": "vin_context"}
            return {
                "messages": [
                    make_tool_call_message(
                        [
                            {"name": "get_vehicle_profile_by_vin", "args": {"vin": vin}},
                            {"name": "get_dtc_history_by_vin", "args": {"vin": vin}},
                            {"name": "get_maintenance_history_by_vin", "args": {"vin": vin}},
                        ],
                        "VIN Context Analyst",
                    )
                ],
                "current_node": "VIN Context Analyst",
                "pending_tool_owner": "vin_context",
            }

        dtc_history = state.get("dtc_history") or []
        maintenance_history = state.get("maintenance_history") or []
        report = {
            "analyst": "VIN Context Analyst",
            "role": "historical_record_collector",
            "conclusion": "has_history_findings" if dtc_history else "no_history_findings",
            "reason": "存在历史故障码" if dtc_history else ("VIN 缺失，车辆档案不可用" if not vin else "车辆档案未显示历史故障"),
            "vin": vin,
            "vehicle": vehicle,
            "dtc_history_count": len(dtc_history),
            "maintenance_history_count": len(maintenance_history),
            "dtc_history": dtc_history,
            "maintenance_history": maintenance_history,
            "data_gaps": [] if vin else ["vin_missing"],
            "handoff_note": "本报告只提供 VIN 车辆档案、历史故障和维修记录事实。",
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "vin_context"],
        }
        updates = conclusion_updates(state, "VIN Context Analyst", "vehicle_profile_report", report)
        updates.update({"vehicle": vehicle, "dtc_history": dtc_history, "maintenance_history": maintenance_history})
        return updates

    return vin_context_analyst_node
