"""Helpers for compact vehicle context strings."""

from typing import Any


def format_vehicle_context(state: dict[str, Any]) -> str:
    vehicle = state.get("vehicle") or {}
    vin = state.get("vin") or vehicle.get("vin") or "unknown"
    make = vehicle.get("make") or vehicle.get("brand") or "unknown"
    model = vehicle.get("model") or "unknown"
    year = vehicle.get("model_year") or vehicle.get("year") or "unknown"
    mileage = vehicle.get("mileage_km") or vehicle.get("mileage") or "unknown"
    engine = vehicle.get("engine_code") or vehicle.get("engine", {}).get("type") or "unknown"
    return (
        f"VIN: {vin}\n"
        f"Vehicle: {year} {make} {model}\n"
        f"Mileage: {mileage} km\n"
        f"Engine: {engine}\n"
        f"Powertrain: {vehicle.get('powertrain_type', 'unknown')}"
    )

