"""Result processing helpers."""

from __future__ import annotations

from typing import Any


class VehicleSignalProcessor:
    def process_result(self, state: dict[str, Any]) -> dict[str, Any]:
        return state.get("structured_result") or {
            "diagnosis_id": state.get("diagnosis_id"),
            "summary": state.get("final_diagnosis", ""),
        }

