"""Mock similar repair case provider."""

from __future__ import annotations

from typing import Any

from .mongo_client import get_database, safe_find_many


def retrieve_repair_cases(query: dict[str, Any]) -> list[dict[str, Any]]:
    codes = set(query.get("dtc_codes") or [])
    db = get_database()
    if db is not None and codes:
        cases = safe_find_many(
            db.repair_cases,
            {"dtc_codes": {"$in": sorted(codes)}},
            _sort=[("confidence", -1)],
            _limit=5,
        )
        if cases:
            return cases
    if "P0301" in codes:
        return [
            {
                "case_id": "mock_case_p0301_001",
                "summary": "Rough idle and P0301 resolved after swapping cylinder 1 ignition coil.",
                "confirmed_root_cause": "cylinder 1 ignition coil failure",
                "repair": ["replace ignition coil", "inspect spark plug"],
                "confidence": 0.62,
            }
        ]
    return []
