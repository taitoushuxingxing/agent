"""Final summary agent for the simplified diagnosis graph."""

from __future__ import annotations

import json
from typing import Any

from .utils.agent_utils import append_trace


def create_summary_agent(llm=None):
    def summary_agent_node(state: dict[str, Any]) -> dict[str, Any]:
        llm_result = _try_llm_summary(llm, state) if llm is not None else None
        result = llm_result or _deterministic_summary(state)
        result.setdefault("diagnosis_id", state.get("diagnosis_id"))
        result.setdefault("vin", state.get("vin"))
        result.setdefault("vehicle", state.get("vehicle") or {})
        result.setdefault("analyst_conclusions", state.get("analyst_conclusions", {}))
        result.setdefault("tool_errors", state.get("tool_errors", []))
        result.setdefault("diagnostic_trace", state.get("graph_trace", []))
        result.setdefault(
            "reports",
            {
                "vehicle_profile_report": state.get("vehicle_profile_report", ""),
                "symptom_report": state.get("symptom_report", ""),
                "dtc_report": state.get("dtc_report", ""),
                "knowledge_report": state.get("knowledge_report", ""),
                "experience_report": state.get("experience_report", ""),
            },
        )
        updates = append_trace(state, "Summary Agent", "completed", result.get("summary", ""))
        result["diagnostic_trace"] = updates["graph_trace"]
        updates.update(
            {
                "final_diagnosis": json.dumps(result, ensure_ascii=False, indent=2),
                "structured_result": result,
            }
        )
        return updates

    return summary_agent_node


def _deterministic_summary(state: dict[str, Any]) -> dict[str, Any]:
    codes = state.get("dtc_codes") or []
    symptoms = state.get("symptoms") or []
    experience = _loads(state.get("experience_report"), {})
    hypotheses: list[dict[str, Any]] = []

    if "P0301" in codes:
        hypotheses.append(
            {
                "rank": 1,
                "fault": "Cylinder 1 ignition system fault",
                "probability": 0.58 if experience.get("similar_cases") else 0.5,
                "evidence_for": ["P0301", *_symptom_names(symptoms)],
                "evidence_against": ["ignition, injector, intake leak, and compression still need confirmation"],
            }
        )
    if "P0171" in codes:
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "fault": "Lean mixture related fault",
                "probability": 0.36,
                "evidence_for": ["P0171"],
                "evidence_against": ["fuel trim and intake leak data not confirmed"],
            }
        )
    if not hypotheses:
        hypotheses.append(
            {
                "rank": 1,
                "fault": "Undetermined fault",
                "probability": 0.2,
                "evidence_for": _symptom_names(symptoms) or ["user description"],
                "evidence_against": ["missing DTC or confirmed reference evidence"],
            }
        )

    confidence = max(item.get("probability", 0.0) for item in hypotheses)
    return {
        "summary": f"Most likely fault: {hypotheses[0]['fault']}.",
        "confidence_score": confidence,
        "ranked_hypotheses": hypotheses,
        "inspection_plan": [
            "Verify active and pending DTCs.",
            "Confirm the customer complaint under the reported working condition.",
            "Inspect the top-ranked fault area before replacing parts.",
        ],
        "knowledge_sources": _loads(state.get("knowledge_report"), {}).get("knowledge_sources", []),
        "similar_experience_cases": experience.get("similar_cases", []),
    }


def _try_llm_summary(llm: Any, state: dict[str, Any]) -> dict[str, Any] | None:
    prompt = {
        "role": "summary_agent",
        "instruction": (
            "Return strict JSON with keys summary, confidence_score, ranked_hypotheses, "
            "inspection_plan. Use only the provided analyst reports."
        ),
        "reports": {
            "vehicle_profile_report": state.get("vehicle_profile_report", ""),
            "symptom_report": state.get("symptom_report", ""),
            "dtc_report": state.get("dtc_report", ""),
            "knowledge_report": state.get("knowledge_report", ""),
            "experience_report": state.get("experience_report", ""),
        },
    }
    try:
        response = llm.invoke(json.dumps(prompt, ensure_ascii=False))
        result = json.loads(_message_content(response))
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    if "ranked_hypotheses" not in result or "summary" not in result:
        return None
    result.setdefault("confidence_score", 0.0)
    result.setdefault("inspection_plan", [])
    return result


def _loads(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _message_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    if hasattr(response, "content"):
        return response.content
    return str(response)


def _symptom_names(symptoms: list[dict[str, Any]]) -> list[str]:
    return [item.get("name", "") for item in symptoms if item.get("name")]
