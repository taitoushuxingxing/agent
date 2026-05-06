"""Small local DTC dictionary for MVP behavior."""

from __future__ import annotations

from typing import Any


DTC_DICTIONARY = {
    "P0300": {
        "description": "Random/Multiple Cylinder Misfire Detected",
        "common_causes": ["spark plugs", "ignition coils", "vacuum leak", "fuel delivery issue"],
        "severity": "medium",
    },
    "P0301": {
        "description": "Cylinder 1 Misfire Detected",
        "common_causes": ["cylinder 1 ignition coil", "spark plug", "injector", "compression issue"],
        "severity": "medium",
    },
    "P0171": {
        "description": "System Too Lean Bank 1",
        "common_causes": ["vacuum leak", "MAF sensor", "fuel pressure", "exhaust leak"],
        "severity": "medium",
    },
    "P0420": {
        "description": "Catalyst System Efficiency Below Threshold",
        "common_causes": ["catalytic converter", "oxygen sensor", "exhaust leak", "misfire damage"],
        "severity": "low",
    },
    "P0128": {
        "description": "Coolant Thermostat Temperature Below Regulating Temperature",
        "common_causes": ["thermostat stuck open", "coolant temperature sensor", "low coolant"],
        "severity": "low",
    },
}


def lookup_dtc_code(code: str, vehicle: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = code.upper().strip()
    info = DTC_DICTIONARY.get(normalized)
    if not info:
        return {
            "code": normalized,
            "description": "Unknown DTC",
            "common_causes": [],
            "severity": "unknown",
        }
    return {"code": normalized, **info}


def search_dtc_combinations(codes: list[str]) -> list[dict[str, Any]]:
    normalized = {code.upper().strip() for code in codes}
    patterns: list[dict[str, Any]] = []
    if {"P0301", "P0171"}.issubset(normalized):
        patterns.append(
            {
                "pattern": "misfire_with_lean_condition",
                "interpretation": "Cylinder misfire together with lean condition can indicate intake leak, fuel delivery issue, or ignition fault aggravated by mixture imbalance.",
                "priority": "high",
            }
        )
    if {"P0300", "P0420"}.issubset(normalized):
        patterns.append(
            {
                "pattern": "misfire_with_catalyst_efficiency",
                "interpretation": "Repeated misfires can overheat and damage the catalytic converter.",
                "priority": "high",
            }
        )
    return patterns

