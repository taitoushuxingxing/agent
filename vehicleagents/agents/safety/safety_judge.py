"""Safety judge and final diagnosis builder."""

from __future__ import annotations

import json
from typing import Any


def create_safety_judge(llm=None, memory=None):
    def safety_judge_node(state: dict[str, Any]) -> dict[str, Any]:
        plan = _loads(state.get("diagnostic_plan"), {})
        repair = _loads(state.get("repair_advice"), {})
        hypotheses = plan.get("ranked_hypotheses", [])
        confidence = plan.get("confidence", 0.0)
        safety_level = "medium" if repair.get("drivability") == "limited" else "low"
        final = {
            "diagnosis_id": state.get("diagnosis_id"),
            "vin": state.get("vin"),
            "vehicle": state.get("vehicle") or {},
            "summary": _summary(hypotheses),
            "safety_level": safety_level,
            "drivability": repair.get("drivability", "unknown"),
            "confidence_score": confidence,
            "ranked_hypotheses": hypotheses,
            "inspection_plan": plan.get("next_tests", []),
            "repair_advice": repair,
            "telemetry_findings": _loads(state.get("telemetry_report"), {}).get("rule_findings", {}).get("findings", []),
            "reports": {
                "vehicle_profile_report": state.get("vehicle_profile_report", ""),
                "symptom_report": state.get("symptom_report", ""),
                "dtc_report": state.get("dtc_report", ""),
                "telemetry_report": state.get("telemetry_report", ""),
                "knowledge_report": state.get("knowledge_report", ""),
                "diagnostic_plan": state.get("diagnostic_plan", ""),
                "safety_review": state.get("safety_review_state", {}).get("safety_history", ""),
            },
        }
        safety = dict(state.get("safety_review_state") or {})
        safety["judge_decision"] = json.dumps(final, ensure_ascii=False)
        return {
            "safety_review_state": safety,
            "final_diagnosis": json.dumps(final, ensure_ascii=False, indent=2),
            "structured_result": final,
        }

    return safety_judge_node


def _loads(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _summary(hypotheses: list[dict[str, Any]]) -> str:
    if not hypotheses:
        return "No clear fault hypothesis yet; collect DTC and telemetry data first."
    top = hypotheses[0]
    return f"Most likely fault: {top.get('fault', 'unknown')}."

