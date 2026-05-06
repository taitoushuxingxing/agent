"""Mock vehicle event provider."""

from __future__ import annotations

from typing import Any

from .mongo_client import get_database, safe_find_many


def get_event_logs_by_vin(vin: str, time_range: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not vin:
        return []
    db = get_database()
    if db is not None:
        items = safe_find_many(db.vin_event_logs, {"vin": vin}, _sort=[("occurred_at", -1)])
        if items:
            return items
    return [
        {
            "vin": vin,
            "event_id": "mock_evt_001",
            "event_name": "rough_idle_detected",
            "event_type": "vehicle_state",
            "severity": "medium",
            "source": "mock_event_database",
            "payload": {"duration_sec": 25, "rpm_variance": 180},
            "tags": ["idle", "engine"],
        }
    ]
