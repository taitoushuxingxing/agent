"""Subjective symptom analyst.

This node only translates the user's complaint into structured symptom
features, suspected fault points, and downstream inspection directions. It does
not query the repair knowledge base; RAG remains a separate downstream agent.
"""

from __future__ import annotations

import json
from typing import Any

from ..utils.agent_utils import conclusion_updates


def create_symptom_analyst(llm=None, toolkit=None):
    def symptom_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
        report = _try_llm_symptom_report(llm, state) if llm is not None else None
        report = report or _deterministic_symptom_report(state)
        return conclusion_updates(state, "Symptom Analyst", "symptom_report", report)

    return symptom_analyst_node


def _try_llm_symptom_report(llm: Any, state: dict[str, Any]) -> dict[str, Any] | None:
    prompt = {
        "role": "subjective_symptom_agent",
        "instruction": (
            "You are the subjective complaint agent in a vehicle diagnosis workflow. "
            "Do semantic normalization only, then propose suspected fault points and "
            "inspection directions for downstream DTC/RAG agents. Do not perform final "
            "diagnosis and do not call databases or RAG. Return strict JSON with keys: "
            "analyst, conclusion, reason, semantic_standardization, suspected_fault_points, "
            "inspection_directions, search_strategy."
        ),
        "vehicle": state.get("vehicle") or {},
        "vin": state.get("vin") or "",
        "user_question": state.get("user_question") or "",
        "symptoms": state.get("symptoms") or [],
    }
    try:
        response = llm.invoke(json.dumps(prompt, ensure_ascii=False, default=str))
        result = json.loads(_message_content(response))
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    result.setdefault("analyst", "Symptom Analyst")
    result.setdefault("conclusion", "has_subjective_clues")
    result.setdefault("reason", "LLM normalized the user complaint into inspection clues.")
    result.setdefault("semantic_standardization", {})
    result.setdefault("suspected_fault_points", [])
    result.setdefault("inspection_directions", [])
    result.setdefault("search_strategy", {})
    return result


def _deterministic_symptom_report(state: dict[str, Any]) -> dict[str, Any]:
    symptoms = state.get("symptoms") or []
    user_question = state.get("user_question") or ""
    text = _build_complaint_text(symptoms, user_question)
    lowered = text.lower()

    standard_symptoms = [_symptom_name(item) for item in symptoms if _symptom_name(item)]
    standard_symptoms.extend(_keyword_symptoms(text))
    standard_symptoms = _dedupe(standard_symptoms)

    trigger_conditions = _extract_conditions(text)
    affected_systems = _infer_systems(text, standard_symptoms)
    severity = _max_severity(symptoms)
    suspected_fault_points = _suspected_fault_points(lowered, affected_systems)
    inspection_directions = _inspection_directions(suspected_fault_points)
    needs_clarification = not text.strip()

    return {
        "analyst": "Symptom Analyst",
        "role": "subjective_hypothesis_provider",
        "conclusion": "needs_clarification" if needs_clarification else "has_subjective_clues",
        "reason": "未提供明确故障现象" if needs_clarification else "已完成主诉语义标准化并给出待验证假设",
        "original_description": user_question,
        "semantic_standardization": {
            "standard_symptoms": standard_symptoms,
            "trigger_conditions": trigger_conditions,
            "affected_systems": affected_systems,
            "severity": severity,
            "frequency": _extract_frequency(text),
        },
        "suspected_fault_points": suspected_fault_points,
        "inspection_directions": inspection_directions,
        "search_strategy": {
            "should_search_web": _should_search_web(text),
            "search_queries": _search_queries(state, standard_symptoms, affected_systems),
            "source_policy": "优先权威维修资料、召回/通病信息；过滤纯主观论坛吐槽",
        },
        "handoff_note": "该报告只提供主观线索和排查方向，最终交叉验证由 Summary Agent 完成。",
    }


def _build_complaint_text(symptoms: list[dict[str, Any]], user_question: str) -> str:
    names = " ".join(_symptom_name(item) for item in symptoms if _symptom_name(item))
    return f"{user_question} {names}".strip()


def _symptom_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("description") or "").strip()


def _keyword_symptoms(text: str) -> list[str]:
    mapping = [
        (("抖", "rough idle", "shake", "vibration"), "异常抖动"),
        (("冷车", "cold start"), "冷车启动异常"),
        (("没劲", "无力", "power loss", "加速慢"), "动力不足"),
        (("顿挫", "jerk", "hesitation"), "加速/换挡顿挫"),
        (("异响", "咯噔", "metal", "noise"), "异响"),
        (("刹车", "brake"), "制动异常"),
        (("方向盘", "转向", "steering"), "转向异常"),
        (("油耗", "fuel consumption"), "油耗异常"),
    ]
    return [label for keys, label in mapping if any(key in text.lower() for key in keys)]


def _extract_conditions(text: str) -> list[str]:
    mapping = [
        (("冷车", "cold start"), "冷车启动"),
        (("热车", "warm"), "热车后"),
        (("加速", "急加速", "accelerat"), "加速时"),
        (("起步", "start off"), "起步时"),
        (("转弯", "turn"), "转弯时"),
        (("减速带", "坑", "颠簸", "bump"), "颠簸路面"),
        (("刹车", "brak"), "制动时"),
    ]
    lowered = text.lower()
    return [label for keys, label in mapping if any(key in lowered for key in keys)] or ["未明确"]


def _extract_frequency(text: str) -> str:
    lowered = text.lower()
    if any(key in lowered for key in ("一直", "持续", "always", "constant")):
        return "持续"
    if any(key in lowered for key in ("偶尔", "有时", "intermittent", "sometimes")):
        return "偶发"
    return "未明确"


def _infer_systems(text: str, standard_symptoms: list[str]) -> list[str]:
    lowered = text.lower()
    joined = " ".join(standard_symptoms)
    candidates: list[str] = []
    if any(key in lowered or key in joined for key in ("发动机", "抖", "没劲", "冷车", "rough idle", "power")):
        candidates.append("engine")
    if any(key in lowered or key in joined for key in ("顿挫", "变速箱", "换挡", "transmission")):
        candidates.append("transmission")
    if any(key in lowered or key in joined for key in ("底盘", "悬挂", "减速带", "咯噔", "异响")):
        candidates.append("chassis_suspension")
    if any(key in lowered or key in joined for key in ("刹车", "brake")):
        candidates.append("brake")
    if any(key in lowered or key in joined for key in ("方向盘", "转向", "steering")):
        candidates.append("steering")
    return _dedupe(candidates) or ["unknown"]


def _max_severity(symptoms: list[dict[str, Any]]) -> str:
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    if not symptoms:
        return "unknown"
    return max(
        (str(item.get("severity", "unknown")) for item in symptoms),
        key=lambda level: severity_order.get(level, 0),
    )


def _suspected_fault_points(text: str, systems: list[str]) -> list[dict[str, Any]]:
    if "engine" in systems:
        if "冷" in text or "cold" in text or "抖" in text or "rough idle" in text:
            return [
                {
                    "fault_point": "火花塞/点火线圈",
                    "system": "engine_ignition",
                    "priority": "high",
                    "reason": "冷车抖动或怠速不稳常见于缺火相关问题",
                },
                {
                    "fault_point": "节气门/喷油嘴积碳",
                    "system": "engine_air_fuel",
                    "priority": "medium",
                    "reason": "冷启动燃烧不充分时常见",
                },
                {
                    "fault_point": "进气泄漏或燃油修正异常",
                    "system": "engine_air_fuel",
                    "priority": "medium",
                    "reason": "可导致混合气异常和动力不足",
                },
            ]
        return [
            {
                "fault_point": "点火/燃油/进气系统",
                "system": "engine",
                "priority": "medium",
                "reason": "主诉指向发动机输出或燃烧稳定性异常",
            }
        ]
    if "transmission" in systems:
        return [
            {
                "fault_point": "变速箱换挡控制或油压调节",
                "system": "transmission",
                "priority": "medium",
                "reason": "顿挫/动力中断可能与换挡控制有关",
            }
        ]
    if "chassis_suspension" in systems:
        return [
            {
                "fault_point": "平衡杆球头/下摆臂胶套/减震器顶胶",
                "system": "chassis_suspension",
                "priority": "medium",
                "reason": "颠簸或过减速带异响常见于悬挂连接件松旷",
            }
        ]
    if "brake" in systems:
        return [
            {
                "fault_point": "刹车片/刹车盘磨损或异物",
                "system": "brake",
                "priority": "medium",
                "reason": "制动异响首先关注摩擦副和磨损状态",
            }
        ]
    return []


def _inspection_directions(suspected_fault_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    directions = []
    for item in suspected_fault_points:
        system = item.get("system", "")
        if system.startswith("engine"):
            directions.append(
                {
                    "target": item.get("fault_point"),
                    "suggested_dtc_focus": ["P0300-P0306", "P0171", "P0172"],
                    "data_stream_focus": ["misfire_count", "short_term_fuel_trim", "long_term_fuel_trim"],
                }
            )
        elif system == "transmission":
            directions.append(
                {
                    "target": item.get("fault_point"),
                    "suggested_dtc_focus": ["TCU shift solenoid and pressure control codes"],
                    "data_stream_focus": ["gear_commanded", "gear_actual", "line_pressure"],
                }
            )
        else:
            directions.append(
                {
                    "target": item.get("fault_point"),
                    "suggested_dtc_focus": [system or "related control module"],
                    "data_stream_focus": [],
                }
            )
    return directions


def _should_search_web(text: str) -> bool:
    lowered = text.lower()
    return any(key in lowered for key in ("通病", "召回", "新车", "刚上市", "recall", "common issue"))


def _search_queries(state: dict[str, Any], symptoms: list[str], systems: list[str]) -> list[str]:
    vehicle = state.get("vehicle") or {}
    vehicle_name = " ".join(
        str(vehicle.get(key, "")).strip()
        for key in ("year", "make", "model", "engine")
        if vehicle.get(key)
    ).strip()
    symptom_text = " ".join(symptoms[:3]) or state.get("user_question", "")
    system_text = " ".join(systems)
    base = " ".join(part for part in (vehicle_name, symptom_text, system_text) if part)
    if not base:
        return []
    return [
        f"{base} 常见故障原因",
        f"{base} 维修案例",
        f"{base} 召回 通病",
    ]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _message_content(response: Any) -> str:
    if isinstance(response, str):
        return response
    if hasattr(response, "content"):
        return response.content
    return str(response)
