"""Telemetry analyst."""

from __future__ import annotations

import json
from typing import Any

from ...dataflows import interface
from ..utils.agent_utils import VehicleToolkit


DEFAULT_SIGNALS = [
    "rpm",
    "battery_voltage",
    "coolant_temp_c",
    "stft_b1",
    "ltft_b1",
    "misfire_count_cyl_1",
]


def create_telemetry_analyst(llm=None, toolkit=None):
    def telemetry_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        vin = state.get("vin") or state.get("vehicle", {}).get("vin") or ""
        snapshot = state.get("sensor_snapshot") or (interface.get_sensor_snapshot_by_vin(vin) if vin else {})
        timeseries = state.get("sensor_timeseries") or (interface.get_sensor_timeseries_by_vin(vin, DEFAULT_SIGNALS) if vin else {})
        events = state.get("event_logs") or (interface.get_event_logs_by_vin(vin) if vin else [])
        rules_raw = VehicleToolkit.analyze_telemetry_rules.invoke(
            {"sensor_snapshot": snapshot, "event_logs": events}
        )
        report = {
            "snapshot_available": bool(snapshot),
            "timeseries_signals": list(timeseries.keys()),
            "event_count": len(events),
            "rule_findings": json.loads(rules_raw),
        }
        return {
            "sensor_snapshot": snapshot,
            "sensor_timeseries": timeseries,
            "event_logs": events,
            "telemetry_report": json.dumps(report, ensure_ascii=False, indent=2),
            "telemetry_tool_call_count": state.get("telemetry_tool_call_count", 0) + 1,
        }

    return telemetry_analyst_node

