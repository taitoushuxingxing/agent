"""VIN context analyst."""

from __future__ import annotations

import json
from typing import Any

from ...dataflows import interface


def create_vin_context_analyst(llm=None, toolkit=None):
    def vin_context_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        vin = state.get("vin") or state.get("vehicle", {}).get("vin") or ""
        vehicle = dict(state.get("vehicle") or {})
        profile = interface.get_vehicle_profile_by_vin(vin) if vin else {}
        if profile:
            vehicle.update(profile)

        dtc_history = state.get("dtc_history") or (interface.get_dtc_history_by_vin(vin) if vin else [])
        maintenance_history = state.get("maintenance_history") or (interface.get_maintenance_history_by_vin(vin) if vin else [])
        report = {
            "vin": vin,
            "vehicle": vehicle,
            "dtc_history_count": len(dtc_history),
            "maintenance_history_count": len(maintenance_history),
            "data_gaps": [] if vin else ["vin_missing"],
        }
        return {
            "vehicle": vehicle,
            "dtc_history": dtc_history,
            "maintenance_history": maintenance_history,
            "vehicle_profile_report": json.dumps(report, ensure_ascii=False, indent=2),
            "vin_context_tool_call_count": state.get("vin_context_tool_call_count", 0) + 1,
        }

    return vin_context_analyst_node

