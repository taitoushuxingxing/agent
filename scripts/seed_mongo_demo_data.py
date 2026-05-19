"""Seed MongoDB with demo vehicle diagnosis data."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure


VIN = "LFV3A23C0J3000001"


def main() -> None:
    mongo_uri = os.getenv("VEHICLE_DIAGNOSIS_MONGO_URI", "mongodb://127.0.0.1:27017")
    database_name = os.getenv("VEHICLE_DIAGNOSIS_MONGO_DATABASE", "vehicle_diagnosis")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[database_name]

    _ensure_indexes(db)
    _seed_vehicle_profile(db)
    _seed_dtc_history(db)
    _seed_maintenance_history(db)
    _seed_repair_cases(db)

    print(f"Seeded MongoDB database '{database_name}' with demo VIN {VIN}.")


def _ensure_indexes(db) -> None:
    db.vehicle_profiles.create_index([("vin", ASCENDING)], unique=True)
    db.vin_dtc_history.create_index([("vin", ASCENDING), ("code", ASCENDING)])
    db.vin_maintenance_history.create_index([("vin", ASCENDING), ("service_date", ASCENDING)])
    db.repair_cases.create_index([("case_id", ASCENDING)], unique=True)
    db.repair_cases.create_index([("dtc_codes", ASCENDING)])


def _seed_vehicle_profile(db) -> None:
    db.vehicle_profiles.update_one(
        {"vin": VIN},
        {
            "$set": {
                "vin": VIN,
                "make": "Volkswagen",
                "model": "Sagitar",
                "model_year": 2020,
                "engine_code": "EA211-1.4T",
                "engine": {"type": "ice", "displacement_l": 1.4, "fuel_type": "gasoline"},
                "transmission": {"type": "dct", "gears": 7},
                "powertrain_type": "ice",
                "region": "CN",
                "mileage_km": 86240,
                "metadata": {"source": "seed_demo_data", "seeded_at": _now()},
            }
        },
        upsert=True,
    )


def _seed_dtc_history(db) -> None:
    records = [
        {
            "vin": VIN,
            "code": "P0301",
            "status": "active",
            "ecu": "ECM",
            "description": "Cylinder 1 Misfire Detected",
            "severity": "medium",
            "occurrence_count": 5,
            "detected_at": "2026-05-06T09:28:00+08:00",
        },
        {
            "vin": VIN,
            "code": "P0171",
            "status": "pending",
            "ecu": "ECM",
            "description": "System Too Lean Bank 1",
            "severity": "medium",
            "occurrence_count": 2,
            "detected_at": "2026-05-06T09:29:00+08:00",
        },
    ]
    for record in records:
        db.vin_dtc_history.update_one(
            {"vin": record["vin"], "code": record["code"]},
            {"$set": record},
            upsert=True,
        )


def _seed_maintenance_history(db) -> None:
    record = {
        "vin": VIN,
        "service_date": "2026-04-01",
        "mileage_km": 84500,
        "service_type": "maintenance",
        "items": ["spark_plug_inspection", "throttle_body_cleaning", "air_filter_replacement"],
        "notes": "Customer reported slight idle vibration; no part replacement at that visit.",
    }
    db.vin_maintenance_history.update_one(
        {"vin": VIN, "service_date": record["service_date"]},
        {"$set": record},
        upsert=True,
    )


def _seed_repair_cases(db) -> None:
    cases = [
        {
            "case_id": "case_p0301_ignition_coil_001",
            "dtc_codes": ["P0301"],
            "symptoms": ["rough idle", "engine vibration"],
            "summary": "Rough idle and P0301 resolved after replacing cylinder 1 ignition coil.",
            "confirmed_root_cause": "cylinder 1 ignition coil failure",
            "repair": ["replace cylinder 1 ignition coil", "clear DTC", "road test"],
            "confidence": 0.78,
        },
        {
            "case_id": "case_p0301_p0171_intake_leak_001",
            "dtc_codes": ["P0301", "P0171"],
            "symptoms": ["rough idle", "lean fuel trim"],
            "summary": "P0301 with P0171 traced to intake hose leak near cylinder 1 runner.",
            "confirmed_root_cause": "intake air leak",
            "repair": ["replace cracked intake hose", "verify fuel trim normalization"],
            "confidence": 0.7,
        },
    ]
    for case in cases:
        db.repair_cases.update_one(
            {"case_id": case["case_id"]},
            {"$set": case},
            upsert=True,
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    try:
        main()
    except OperationFailure as exc:
        if exc.code == 13:
            raise SystemExit(
                "MongoDB requires authentication. Set VEHICLE_DIAGNOSIS_MONGO_URI "
                "to an authenticated URI, for example "
                "mongodb://user:password@127.0.0.1:27017/vehicle_diagnosis?authSource=admin"
            ) from exc
        raise
