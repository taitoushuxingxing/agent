"""Experience analyst backed by confirmed diagnosis memory."""

from __future__ import annotations

import json
from typing import Any

from ..utils.agent_utils import conclusion_updates


def create_experience_analyst(memory=None):
    def experience_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        query = {
            "vehicle": state.get("vehicle") or {},
            "symptoms": state.get("symptoms") or [],
            "dtc_codes": state.get("dtc_codes") or [],
        }
        matches = _get_memory_matches(memory, query)
        report = {
            "analyst": "Experience Analyst",
            "conclusion": "has_similar_cases" if matches else "no_similar_cases",
            "reason": f"found {len(matches)} confirmed similar case(s)" if matches else "no confirmed similar case found",
            "query": query,
            "similar_cases": matches,
        }
        return conclusion_updates(state, "Experience Analyst", "experience_report", report)

    return experience_analyst_node


def _get_memory_matches(memory: Any, query: dict[str, Any]) -> list[dict[str, Any]]:
    if memory is None or not hasattr(memory, "get_memories"):
        return []
    try:
        return memory.get_memories(json.dumps(query, ensure_ascii=False, sort_keys=True), n_matches=3)
    except Exception:
        return []
