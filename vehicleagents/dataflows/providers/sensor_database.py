"""Mock telemetry provider."""

from __future__ import annotations

from typing import Any

from .mongo_client import get_database, safe_find_many, safe_find_one


def get_sensor_snapshot_by_vin(vin: str, time_range: dict[str, Any] | None = None) -> dict[str, Any]:
    if not vin:
        return {}
    db = get_database()
    if db is not None:
        snapshot = safe_find_one(db.vin_sensor_snapshots, {"vin": vin}, sort=[("captured_at", -1)])
        if snapshot:
            snapshot.setdefault("source", "mongo_sensor_snapshots")
            return snapshot
    return {
        "vin": vin,
        "snapshot_id": "mock_snapshot",
        "source": "mock_sensor_database",
        "quality": "good",
        "signals": {
            "rpm": {"value": 760, "unit": "rpm", "quality": "good"},
            "battery_voltage": {"value": 12.4, "unit": "V", "quality": "good"},
            "coolant_temp_c": {"value": 92, "unit": "C", "quality": "good"},
            "stft_b1": {"value": 18.5, "unit": "%", "quality": "good"},
            "ltft_b1": {"value": 12.1, "unit": "%", "quality": "good"},
            "misfire_count_cyl_1": {"value": 43, "unit": "count", "quality": "good"},
        },
    }


def get_sensor_timeseries_by_vin(
    vin: str,
    signals: list[str],
    time_range: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not vin:
        return {}
    db = get_database()
    if db is not None:
        rows = safe_find_many(db.vin_sensor_timeseries, {"vin": vin, "signal": {"$in": signals}}, _sort=[("signal", 1)])
        if rows:
            return {row["signal"]: row.get("points", []) for row in rows}
    return {
        signal: [
            {"ts": "2026-05-06T09:30:00+08:00", "value": 1, "unit": "", "quality": "mock"},
            {"ts": "2026-05-06T09:31:00+08:00", "value": 2, "unit": "", "quality": "mock"},
        ]
        for signal in signals
    }
