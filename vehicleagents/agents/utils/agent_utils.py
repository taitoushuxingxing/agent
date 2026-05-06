"""Shared toolkit and utility nodes."""

from __future__ import annotations

import json
from typing import Annotated, Any

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.tools import tool

from ...dataflows import interface
from ...default_config import DEFAULT_VEHICLE_CONFIG


def create_msg_delete():
    def delete_messages(state: dict[str, Any]) -> dict[str, Any]:
        messages = state.get("messages", [])
        removals = [RemoveMessage(id=m.id) for m in messages if hasattr(m, "id")]
        return {"messages": removals + [HumanMessage(content="Continue")]}

    return delete_messages


class VehicleToolkit:
    _config = DEFAULT_VEHICLE_CONFIG.copy()

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        if config:
            self._config.update(config)

    @staticmethod
    @tool
    def get_vehicle_profile_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch vehicle profile by VIN."""
        return json.dumps(interface.get_vehicle_profile_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_dtc_history_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch historical DTC records by VIN."""
        return json.dumps(interface.get_dtc_history_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_sensor_snapshot_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch latest sensor snapshot by VIN."""
        return json.dumps(interface.get_sensor_snapshot_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def get_sensor_timeseries_by_vin(
        vin: Annotated[str, "Vehicle identification number"],
        signals: Annotated[list[str], "Signal names to fetch"],
    ) -> str:
        """Fetch sensor timeseries by VIN and signal list."""
        return json.dumps(interface.get_sensor_timeseries_by_vin(vin, signals), ensure_ascii=False)

    @staticmethod
    @tool
    def get_event_logs_by_vin(vin: Annotated[str, "Vehicle identification number"]) -> str:
        """Fetch vehicle event logs by VIN."""
        return json.dumps(interface.get_event_logs_by_vin(vin), ensure_ascii=False)

    @staticmethod
    @tool
    def lookup_dtc_code(code: Annotated[str, "DTC code, e.g. P0301"]) -> str:
        """Look up a DTC code in the local dictionary."""
        return json.dumps(interface.lookup_dtc_code(code), ensure_ascii=False)

    @staticmethod
    @tool
    def search_dtc_combinations(codes: Annotated[list[str], "DTC code list"]) -> str:
        """Search known diagnostic patterns for DTC combinations."""
        return json.dumps(interface.search_dtc_combinations(codes), ensure_ascii=False)

    @staticmethod
    @tool
    def retrieve_repair_cases(query: Annotated[dict[str, Any], "Case retrieval query"]) -> str:
        """Retrieve similar repair cases."""
        return json.dumps(interface.retrieve_repair_cases(query), ensure_ascii=False)

    @staticmethod
    @tool
    def analyze_telemetry_rules(
        sensor_snapshot: Annotated[dict[str, Any], "Sensor snapshot"],
        event_logs: Annotated[list[dict[str, Any]], "Event logs"],
    ) -> str:
        """Run deterministic telemetry checks for common fault signals."""
        findings: list[dict[str, Any]] = []
        signals = sensor_snapshot.get("signals", sensor_snapshot)

        def value(name: str) -> Any:
            item = signals.get(name)
            if isinstance(item, dict):
                return item.get("value")
            return item

        stft = value("stft_b1")
        ltft = value("ltft_b1")
        misfire_cyl_1 = value("misfire_count_cyl_1")
        battery_voltage = value("battery_voltage")

        if isinstance(stft, (int, float)) and stft > 15:
            findings.append({"signal": "stft_b1", "finding": "short term fuel trim is high", "severity": "medium"})
        if isinstance(ltft, (int, float)) and ltft > 10:
            findings.append({"signal": "ltft_b1", "finding": "long term fuel trim is high", "severity": "medium"})
        if isinstance(misfire_cyl_1, (int, float)) and misfire_cyl_1 > 0:
            findings.append({"signal": "misfire_count_cyl_1", "finding": "cylinder 1 misfire count is non-zero", "severity": "medium"})
        if isinstance(battery_voltage, (int, float)) and battery_voltage < 12.0:
            findings.append({"signal": "battery_voltage", "finding": "battery voltage is low", "severity": "medium"})
        for event in event_logs:
            if event.get("event_name") == "rough_idle_detected":
                findings.append({"event": "rough_idle_detected", "finding": "rough idle event correlates with symptom", "severity": event.get("severity", "medium")})
        return json.dumps({"findings": findings}, ensure_ascii=False)

