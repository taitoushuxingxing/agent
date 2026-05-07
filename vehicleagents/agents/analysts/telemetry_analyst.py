"""Telemetry analyst."""

from __future__ import annotations

from typing import Any

from ..utils.agent_utils import conclusion_updates, invoke_llm_tool_decision, make_tool_call_message


DEFAULT_SIGNALS = [
    "rpm",
    "battery_voltage",
    "coolant_temp_c",
    "stft_b1",
    "ltft_b1",
    "misfire_count_cyl_1",
]


def create_telemetry_analyst(llm=None, toolkit=None):
    tools = [
        toolkit.get_sensor_snapshot_by_vin,
        toolkit.get_sensor_timeseries_by_vin,
        toolkit.get_event_logs_by_vin,
        toolkit.analyze_telemetry_rules,
    ] if toolkit is not None else []

    def telemetry_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        vin = state.get("vin") or state.get("vehicle", {}).get("vin") or ""
        snapshot = state.get("sensor_snapshot") or {}
        timeseries = state.get("sensor_timeseries") or {}
        events = state.get("event_logs") or []
        has_tool_results = bool((state.get("analyst_tool_results") or {}).get("telemetry"))
        if not has_tool_results and not state.get("telemetry_report") and (vin or snapshot or events):
            llm_message = invoke_llm_tool_decision(
                llm,
                tools,
                "Telemetry Analyst",
                state,
                {"vin": vin, "sensor_snapshot": snapshot, "event_logs": events},
            )
            if llm_message and getattr(llm_message, "tool_calls", None):
                return {"messages": [llm_message], "current_node": "Telemetry Analyst", "pending_tool_owner": "telemetry"}
            calls = []
            if (snapshot or events) and len(calls) < 2:
                calls.append({"name": "analyze_telemetry_rules", "args": {"sensor_snapshot": snapshot, "event_logs": events}})
            if vin and not snapshot and len(calls) < 2:
                calls.append({"name": "get_sensor_snapshot_by_vin", "args": {"vin": vin}})
            if vin and not timeseries and len(calls) < 2:
                calls.append({"name": "get_sensor_timeseries_by_vin", "args": {"vin": vin, "signals": DEFAULT_SIGNALS}})
            if vin and not events and len(calls) < 2:
                calls.append({"name": "get_event_logs_by_vin", "args": {"vin": vin}})
            if calls:
                return {
                    "messages": [make_tool_call_message(calls, "Telemetry Analyst")],
                    "current_node": "Telemetry Analyst",
                    "pending_tool_owner": "telemetry",
                }

        telemetry_results = (state.get("analyst_tool_results") or {}).get("telemetry", [])
        rule_findings = {}
        for item in telemetry_results:
            if item.get("ok") and item.get("tool") == "analyze_telemetry_rules":
                rule_findings = item.get("result") or {}
        report = {
            "analyst": "Telemetry Analyst",
            "conclusion": "有问题" if rule_findings.get("findings") else "无问题",
            "reason": f"发现 {len(rule_findings.get('findings', []))} 个遥测异常" if rule_findings.get("findings") else "遥测规则未发现明确异常",
            "snapshot_available": bool(snapshot),
            "timeseries_signals": list(timeseries.keys()),
            "event_count": len(events),
            "rule_findings": rule_findings,
            "tool_errors": [item for item in state.get("tool_errors", []) if item.get("analyst") == "telemetry"],
        }
        updates = conclusion_updates(state, "Telemetry Analyst", "telemetry_report", report)
        updates.update({"sensor_snapshot": snapshot, "sensor_timeseries": timeseries, "event_logs": events})
        return updates

    return telemetry_analyst_node
