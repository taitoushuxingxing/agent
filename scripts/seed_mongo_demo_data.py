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
    _seed_sensor_snapshot(db)
    _seed_sensor_timeseries(db)
    _seed_event_logs(db)
    _seed_repair_cases(db)

    print(f"Seeded MongoDB database '{database_name}' with demo VIN {VIN}.")


def _ensure_indexes(db) -> None:
    db.vehicle_profiles.create_index([("vin", ASCENDING)], unique=True)
    db.vin_dtc_history.create_index([("vin", ASCENDING), ("code", ASCENDING)])
    db.vin_maintenance_history.create_index([("vin", ASCENDING), ("service_date", ASCENDING)])
    db.vin_sensor_snapshots.create_index([("vin", ASCENDING), ("captured_at", ASCENDING)])
    db.vin_sensor_timeseries.create_index([("vin", ASCENDING), ("signal", ASCENDING)], unique=True)
    db.vin_event_logs.create_index([("vin", ASCENDING), ("event_id", ASCENDING)], unique=True)
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


def _seed_sensor_snapshot(db) -> None:
    snapshot = {
        "vin": VIN,
        "snapshot_id": "seed_snapshot_rough_idle_001",
        "captured_at": "2026-05-06T09:31:00+08:00",
        "source": "seed_sensor_snapshot",
        "quality": "good",
        "signals": {
            "rpm": {"value": 742, "unit": "rpm", "quality": "good"},
            "battery_voltage": {"value": 12.3, "unit": "V", "quality": "good"},
            "coolant_temp_c": {"value": 91, "unit": "C", "quality": "good"},
            "stft_b1": {"value": 19.4, "unit": "%", "quality": "good"},
            "ltft_b1": {"value": 13.2, "unit": "%", "quality": "good"},
            "misfire_count_cyl_1": {"value": 57, "unit": "count", "quality": "good"},
        },
    }
    db.vin_sensor_snapshots.update_one(
        {"vin": VIN, "snapshot_id": snapshot["snapshot_id"]},
        {"$set": snapshot},
        upsert=True,
    )


def _seed_sensor_timeseries(db) -> None:
    series = {
        "rpm": [760, 735, 710, 780, 725],
        "stft_b1": [16.8, 18.2, 19.4, 21.0, 18.9],
        "ltft_b1": [11.6, 12.4, 13.2, 13.1, 12.9],
        "misfire_count_cyl_1": [8, 15, 27, 43, 57],
        "battery_voltage": [12.4, 12.3, 12.3, 12.2, 12.3],
        "coolant_temp_c": [88, 89, 90, 91, 91],
    }
    for signal, values in series.items():
        points = [
            {
                "ts": f"2026-05-06T09:3{index}:00+08:00",
                "value": value,
                "unit": _unit_for_signal(signal),
                "quality": "good",
            }
            for index, value in enumerate(values)
        ]
        db.vin_sensor_timeseries.update_one(
            {"vin": VIN, "signal": signal},
            {"$set": {"vin": VIN, "signal": signal, "points": points}},
            upsert=True,
        )


def _seed_event_logs(db) -> None:
    event = {
        "vin": VIN,
        "event_id": "seed_evt_rough_idle_001",
        "event_name": "rough_idle_detected",
        "event_type": "vehicle_state",
        "severity": "medium",
        "occurred_at": "2026-05-06T09:30:20+08:00",
        "source": "seed_event_log",
        "payload": {"duration_sec": 31, "rpm_variance": 210},
        "tags": ["idle", "engine", "misfire"],
    }
    db.vin_event_logs.update_one(
        {"vin": VIN, "event_id": event["event_id"]},
        {"$set": event},
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


def _unit_for_signal(signal: str) -> str:
    return {
        "rpm": "rpm",
        "stft_b1": "%",
        "ltft_b1": "%",
        "misfire_count_cyl_1": "count",
        "battery_voltage": "V",
        "coolant_temp_c": "C",
    }.get(signal, "")


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
