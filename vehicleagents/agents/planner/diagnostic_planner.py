"""Diagnostic planner."""

from __future__ import annotations

import json
from typing import Any

from ..utils.agent_utils import append_trace


def create_diagnostic_planner(llm=None, memory=None):
    def diagnostic_planner_node(state: dict[str, Any]) -> dict[str, Any]:
        memory_matches = _get_memory_matches(memory, state)
        plan = _try_llm_plan(llm, state, memory_matches) if llm is not None else None
        if plan is None:
            plan = _deterministic_plan(state, memory_matches)
        plan.setdefault("planner_source", "llm" if llm is not None else "rules")
        plan["similar_memory_cases"] = memory_matches

        debate = dict(state.get("diagnostic_debate_state") or {})
        debate["planner_decision"] = json.dumps(plan, ensure_ascii=False)
        updates = append_trace(state, "Diagnostic Planner", "completed", plan.get("planner_source", ""))
        updates.update({
            "diagnostic_debate_state": debate,
            "diagnostic_plan": json.dumps(plan, ensure_ascii=False, indent=2),
        })
        return updates

    return diagnostic_planner_node


def _deterministic_plan(state: dict[str, Any], memory_matches: list[dict[str, Any]]) -> dict[str, Any]:
    codes = state.get("dtc_codes") or []
    hypotheses: list[dict[str, Any]] = []
    if "P0301" in codes:
        probability = 0.48 if memory_matches else 0.42
        hypotheses.append(
            {
                "rank": 1,
                "fault": "Cylinder 1 ignition system fault",
                "probability": probability,
                "evidence_for": ["P0301", "rough idle symptom", "misfire telemetry if present"],
                "evidence_against": ["spark plug, injector, and compression not yet inspected"],
            }
        )
    if "P0171" in codes:
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "fault": "Lean mixture from intake leak or fuel delivery issue",
                "probability": 0.32,
                "evidence_for": ["P0171", "high fuel trim if present"],
                "evidence_against": ["MAF and fuel pressure not yet verified"],
            }
        )
    if not hypotheses:
        hypotheses.append(
            {
                "rank": 1,
                "fault": "Undetermined fault",
                "probability": 0.2,
                "evidence_for": ["symptom report available"],
                "evidence_against": ["missing DTC or telemetry evidence"],
            }
        )
    return {
        "planner_source": "rules",
        "ranked_hypotheses": hypotheses,
        "next_tests": [
            "Scan active and pending DTCs.",
            "Inspect ignition coil and spark plug for affected cylinder.",
            "Check intake leaks and fuel trim behavior.",
            "Review event logs around symptom onset.",
        ],
        "stop_conditions": ["MIL flashing", "severe vibration", "overheating", "fuel smell"],
        "confidence": max(item["probability"] for item in hypotheses),
    }


def _try_llm_plan(llm: Any, state: dict[str, Any], memory_matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    prompt = {
        "role": "diagnostic_planner",
        "instruction": (
            "Return strict JSON with keys ranked_hypotheses, next_tests, "
            "stop_conditions, confidence. Rank fault hypotheses using the evidence."
        ),
        "vehicle": state.get("vehicle") or {},
        "symptoms": state.get("symptoms") or [],
        "dtc_codes": state.get("dtc_codes") or [],
        "reports": {
            "vehicle_profile_report": state.get("vehicle_profile_report", ""),
            "symptom_report": state.get("symptom_report", ""),
            "dtc_report": state.get("dtc_report", ""),
            "telemetry_report": state.get("telemetry_report", ""),
            "knowledge_report": state.get("knowledge_report", ""),
            "debate_history": state.get("diagnostic_debate_state", {}).get("history", ""),
        },
        "similar_memory_cases": memory_matches,
    }
    try:
        response = llm.invoke(json.dumps(prompt, ensure_ascii=False))
        content = _message_content(response)
        plan = json.loads(content)
    except Exception:
        return None
    if not isinstance(plan, dict):
        return None
    if "ranked_hypotheses" not in plan or "next_tests" not in plan:
        return None
    plan["planner_source"] = "llm"
    plan.setdefault("stop_conditions", [])
    plan.setdefault("confidence", 0.0)
    return plan


def _get_memory_matches(memory: Any, state: dict[str, Any]) -> list[dict[str, Any]]:
    if memory is None or not hasattr(memory, "get_memories"):
        return []
    situation = json.dumps(
        {
            "vehicle": state.get("vehicle") or {},
            "symptoms": state.get("symptoms") or [],
            "dtc_codes": state.get("dtc_codes") or [],
            "telemetry_report": state.get("telemetry_report", ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    try:
        return memory.get_memories(situation, n_matches=3)
    except Exception:
        return []


def _message_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    if hasattr(response, "content"):
        return response.content
    return str(response)
