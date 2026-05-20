"""Final summary/debate agent for the diagnosis graph."""

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
    symptom_report = _loads(state.get("symptom_report"), {})
    dtc_report = _loads(state.get("dtc_report"), {})
    knowledge_report = _loads(state.get("knowledge_report"), {})
    experience = _loads(state.get("experience_report"), {})

    hypotheses = _dtc_hypotheses(codes, symptoms)
    if not hypotheses:
        hypotheses = _symptom_hypotheses(symptom_report)
    if not hypotheses:
        hypotheses = [
            {
                "rank": 1,
                "fault": "Undetermined fault",
                "probability": 0.2,
                "evidence_for": _symptom_names(symptoms) or ["user description"],
                "evidence_against": ["missing DTC or confirmed reference evidence"],
            }
        ]

    _enrich_with_knowledge(hypotheses, knowledge_report, experience)
    confidence = max(item.get("probability", 0.0) for item in hypotheses)
    summary = f"Most likely fault: {hypotheses[0]['fault']}."
    return {
        "summary": summary,
        "final_conclusion": hypotheses[0]["fault"],
        "confidence_score": confidence,
        "confidence_level": _confidence_level(confidence),
        "ranked_hypotheses": hypotheses,
        "debate_notes": _debate_notes(symptom_report, dtc_report, knowledge_report),
        "reasoning_process": (
            "Summary compared subjective hypotheses, objective DTC evidence, and RAG references. "
            "DTC/RAG facts were weighted above subjective complaint wording when they conflicted."
        ),
        "inspection_plan": [
            "Confirm the customer complaint under the reported working condition.",
            "Verify active and pending DTCs plus freeze frame data.",
            "Use RAG manual/case references to inspect the top-ranked fault area before replacing parts.",
        ],
        "knowledge_sources": knowledge_report.get("knowledge_sources", []),
        "similar_experience_cases": experience.get("similar_cases", []),
    }


def _try_llm_summary(llm: Any, state: dict[str, Any]) -> dict[str, Any] | None:
    prompt = {
        "role": "summary_debate_agent",
        "instruction": (
            "You are the final chief diagnostic expert. Use only the provided reports. "
            "Do the cross-validation/debate here, not in upstream agents. Compare: "
            "1) subjective complaint hypotheses, 2) objective VIN/DTC/freeze-frame facts, "
            "3) RAG manual/case references. Prefer objective data and authoritative RAG "
            "when they conflict with subjective wording. Return strict JSON with keys "
            "summary, final_conclusion, confidence_score, confidence_level, "
            "ranked_hypotheses, debate_notes, reasoning_process, inspection_plan. "
            "The reasoning_process must be a concise evidence rationale, not hidden chain-of-thought."
        ),
        "case_file": {
            "vehicle_and_history": state.get("vehicle_profile_report", ""),
            "subjective_complaint_and_hypotheses": state.get("symptom_report", ""),
            "objective_dtc_data": state.get("dtc_report", ""),
            "rag_manual_and_cases": state.get("knowledge_report", ""),
            "confirmed_experience_memory": state.get("experience_report", ""),
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
    result.setdefault("final_conclusion", result.get("summary", ""))
    result.setdefault("confidence_score", 0.0)
    result.setdefault("confidence_level", _confidence_level(float(result.get("confidence_score") or 0.0)))
    result.setdefault("debate_notes", [])
    result.setdefault("reasoning_process", "")
    result.setdefault("inspection_plan", [])
    return result


def _dtc_hypotheses(codes: list[str], symptoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    symptom_evidence = _symptom_names(symptoms)
    if "P0301" in codes:
        hypotheses.append(
            {
                "rank": 1,
                "fault": "Cylinder 1 ignition system fault",
                "probability": 0.62,
                "evidence_for": ["P0301", *symptom_evidence],
                "evidence_against": ["ignition coil, spark plug, injector, intake leak, and compression still need confirmation"],
            }
        )
    if "P0300" in codes:
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "fault": "Random/multiple cylinder misfire",
                "probability": 0.52,
                "evidence_for": ["P0300", *symptom_evidence],
                "evidence_against": ["specific cylinder and root cause still need confirmation"],
            }
        )
    if "P0171" in codes:
        hypotheses.append(
            {
                "rank": len(hypotheses) + 1,
                "fault": "Lean mixture related fault",
                "probability": 0.38,
                "evidence_for": ["P0171"],
                "evidence_against": ["fuel trim and intake leak data not confirmed"],
            }
        )
    for index, item in enumerate(hypotheses, start=1):
        item["rank"] = index
    return hypotheses


def _symptom_hypotheses(symptom_report: dict[str, Any]) -> list[dict[str, Any]]:
    suspected = symptom_report.get("suspected_fault_points") or []
    hypotheses = []
    probability_by_priority = {"high": 0.45, "medium": 0.32, "low": 0.2}
    for index, item in enumerate(suspected[:3], start=1):
        if not isinstance(item, dict):
            continue
        priority = item.get("priority", "medium")
        hypotheses.append(
            {
                "rank": index,
                "fault": item.get("fault_point", "Subjective suspected fault"),
                "probability": probability_by_priority.get(priority, 0.25),
                "evidence_for": [item.get("reason", "subjective complaint hypothesis")],
                "evidence_against": ["no objective DTC/RAG confirmation yet"],
            }
        )
    return hypotheses


def _enrich_with_knowledge(
    hypotheses: list[dict[str, Any]],
    knowledge_report: dict[str, Any],
    experience: dict[str, Any],
) -> None:
    case_count = int(knowledge_report.get("case_count") or 0)
    experience_cases = experience.get("similar_cases") or []
    if not hypotheses:
        return
    if case_count:
        hypotheses[0]["probability"] = min(float(hypotheses[0].get("probability", 0.0)) + 0.08, 0.9)
        hypotheses[0].setdefault("evidence_for", []).append(f"RAG matched {case_count} repair reference(s)")
    if experience_cases:
        hypotheses[0]["probability"] = min(float(hypotheses[0].get("probability", 0.0)) + 0.05, 0.92)
        hypotheses[0].setdefault("evidence_for", []).append("confirmed experience memory has similar case(s)")


def _debate_notes(
    symptom_report: dict[str, Any],
    dtc_report: dict[str, Any],
    knowledge_report: dict[str, Any],
) -> list[str]:
    notes = [
        "主观描述 Agent 提供语义标准化和待验证故障假设。",
        "DTC Agent 只提交客观 DTC/冻结帧/数据流事实，不提前裁决。",
        "RAG Agent 只提交维修手册和案例参考。",
        "Summary Agent 在本节点统一执行主观、客观和知识库证据的交叉验证。",
    ]
    if not (dtc_report.get("codes") or []):
        notes.append("当前缺少 DTC 证据，结论需要保持为疑似并建议进一步路试/读取数据。")
    if not int(knowledge_report.get("case_count") or 0):
        notes.append("当前缺少 RAG 命中资料，维修建议应偏保守。")
    if symptom_report.get("conclusion") == "needs_clarification":
        notes.append("用户主诉信息不足，建议优先追问触发工况、频率和仪表故障灯状态。")
    return notes


def _confidence_level(score: float) -> str:
    if score >= 0.7:
        return "高"
    if score >= 0.4:
        return "中"
    return "低"


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
