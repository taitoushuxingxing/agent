"""Reflection hook for future memory updates."""

from __future__ import annotations

from typing import Any


class VehicleReflector:
    def reflect_outcome(self, state: dict[str, Any], outcome: dict[str, Any], memory: Any) -> None:
        if not memory:
            return
        memory.add_case(
            situation=str(state.get("structured_result") or state),
            recommendation=str(outcome),
            metadata={"vin": state.get("vin"), "diagnosis_id": state.get("diagnosis_id")},
        )

