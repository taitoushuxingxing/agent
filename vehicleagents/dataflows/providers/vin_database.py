"""Mock VIN database provider.

Replace this file with a real database adapter when connection details are ready.
"""

from __future__ import annotations

from typing import Any

from .mongo_client import get_database, safe_find_many, safe_find_one


def get_vehicle_profile_by_vin(vin: str) -> dict[str, Any]:
    if not vin:
        return {}
    db = get_database()
    if db is not None:
        profile = safe_find_one(db.vehicle_profiles, {"vin": vin})
        if profile:
            profile.setdefault("metadata", {})["source"] = "mongo_vehicle_profiles"
            return profile
    return {
        "vin": vin,
        "make": "MockBrand",
        "model": "MockModel",
        "model_year": 2020,
        "engine_code": "ICE-1.5T",
        "engine": {"type": "ice", "displacement_l": 1.5, "fuel_type": "gasoline"},
        "transmission": {"type": "at", "gears": 6},
        "powertrain_type": "ice",
        "region": "CN",
        "mileage_km": 86000,
        "metadata": {"source": "mock_vin_database"},
    }


def get_dtc_history_by_vin(vin: str, time_range: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not vin:
        return []
    db = get_database()
    if db is not None:
        items = safe_find_many(db.vin_dtc_history, {"vin": vin}, _sort=[("detected_at", -1)])
        if items:
            return items
    return [
        {
            "vin": vin,
            "code": "P0301",
            "status": "active",
            "ecu": "ECM",
            "description": "Cylinder 1 Misfire Detected",
            "severity": "medium",
            "occurrence_count": 3,
        }
    ]


def get_maintenance_history_by_vin(vin: str) -> list[dict[str, Any]]:
    if not vin:
        return []
    db = get_database()
    if db is not None:
        items = safe_find_many(db.vin_maintenance_history, {"vin": vin}, _sort=[("service_date", -1)])
        if items:
            return items
    return [
        {
            "vin": vin,
            "service_date": "2026-04-01",
            "mileage_km": 84500,
            "service_type": "maintenance",
            "items": ["spark_plug_inspection", "throttle_body_cleaning"],
            "notes": "Mock maintenance record.",
        }
    ]
