"""Repair advisor."""

from __future__ import annotations

import json
from typing import Any


def create_repair_advisor(llm=None, memory=None):
    def repair_advisor_node(state: dict[str, Any]) -> dict[str, Any]:
        advice = {
            "drivability": "limited",
            "recommended_actions": [
                "Avoid high-load driving until misfire is verified.",
                "Perform low-cost inspection before replacing parts.",
                "If MIL flashes, stop driving and arrange service.",
            ],
            "estimated_cost": {"currency": "CNY", "low": 200, "high": 1500},
        }
        return {"repair_advice": json.dumps(advice, ensure_ascii=False, indent=2)}

    return repair_advisor_node

