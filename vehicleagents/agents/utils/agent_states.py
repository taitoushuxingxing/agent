"""LangGraph state definitions for vehicle diagnosis."""

from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph import MessagesState


class DiagnosticDebateState(TypedDict):
    hypothesis_history: Annotated[str, "Hypothesis researcher history"]
    counterfactual_history: Annotated[str, "Counterfactual researcher history"]
    history: Annotated[str, "Combined diagnostic debate history"]
    current_response: Annotated[str, "Latest debate response"]
    planner_decision: Annotated[str, "Planner decision"]
    count: Annotated[int, "Debate turn count"]


class SafetyReviewState(TypedDict):
    safety_history: Annotated[str, "Safety analysis history"]
    repair_history: Annotated[str, "Repair advice review history"]
    judge_decision: Annotated[str, "Final safety decision"]
    latest_speaker: Annotated[str, "Latest speaker"]
    count: Annotated[int, "Safety review turn count"]


class VehicleDiagnosisState(MessagesState):
    diagnosis_id: Annotated[str, "Diagnosis id"]
    case_date: Annotated[str, "Case date"]
    vin: Annotated[str, "Vehicle identification number"]
    vehicle: Annotated[dict[str, Any], "Vehicle profile"]
    symptoms: Annotated[list[dict[str, Any]], "User reported symptoms"]
    dtc_codes: Annotated[list[str], "Submitted DTC codes"]
    dtc_history: Annotated[list[dict[str, Any]], "DTC history from VIN database"]
    sensor_snapshot: Annotated[dict[str, Any], "Sensor snapshot"]
    sensor_timeseries: Annotated[dict[str, Any], "Sensor timeseries"]
    event_logs: Annotated[list[dict[str, Any]], "Vehicle event logs"]
    freeze_frame: Annotated[dict[str, Any], "Freeze frame data"]
    maintenance_history: Annotated[list[dict[str, Any]], "Maintenance history"]
    user_question: Annotated[str, "User question"]

    vehicle_profile_report: Annotated[str, "VIN context report"]
    symptom_report: Annotated[str, "Symptom report"]
    dtc_report: Annotated[str, "DTC report"]
    telemetry_report: Annotated[str, "Telemetry report"]
    knowledge_report: Annotated[str, "Knowledge report"]

    vin_context_tool_call_count: Annotated[int, "VIN context tool calls"]
    symptom_tool_call_count: Annotated[int, "Symptom tool calls"]
    dtc_tool_call_count: Annotated[int, "DTC tool calls"]
    telemetry_tool_call_count: Annotated[int, "Telemetry tool calls"]
    knowledge_tool_call_count: Annotated[int, "Knowledge tool calls"]

    diagnostic_debate_state: Annotated[DiagnosticDebateState, "Diagnostic debate"]
    diagnostic_plan: Annotated[str, "Diagnostic plan"]
    repair_advice: Annotated[str, "Repair advice"]
    safety_review_state: Annotated[SafetyReviewState, "Safety review"]
    final_diagnosis: Annotated[str, "Final diagnosis"]
    structured_result: Annotated[dict[str, Any], "Machine readable result"]


def build_initial_state(payload: dict[str, Any], diagnosis_id: str, case_date: str) -> dict[str, Any]:
    """Build a complete initial state from an API payload."""
    vin = payload.get("vin") or payload.get("vehicle", {}).get("vin") or ""
    return {
        "messages": [("human", payload.get("user_question") or "Please diagnose this vehicle fault.")],
        "diagnosis_id": diagnosis_id,
        "case_date": case_date,
        "vin": vin,
        "vehicle": payload.get("vehicle") or {},
        "symptoms": payload.get("symptoms") or [],
        "dtc_codes": payload.get("dtc_codes") or [],
        "dtc_history": [],
        "sensor_snapshot": payload.get("sensor_snapshot") or {},
        "sensor_timeseries": {},
        "event_logs": [],
        "freeze_frame": payload.get("freeze_frame") or {},
        "maintenance_history": payload.get("maintenance_history") or [],
        "user_question": payload.get("user_question") or "",
        "vehicle_profile_report": "",
        "symptom_report": "",
        "dtc_report": "",
        "telemetry_report": "",
        "knowledge_report": "",
        "vin_context_tool_call_count": 0,
        "symptom_tool_call_count": 0,
        "dtc_tool_call_count": 0,
        "telemetry_tool_call_count": 0,
        "knowledge_tool_call_count": 0,
        "diagnostic_debate_state": {
            "hypothesis_history": "",
            "counterfactual_history": "",
            "history": "",
            "current_response": "",
            "planner_decision": "",
            "count": 0,
        },
        "diagnostic_plan": "",
        "repair_advice": "",
        "safety_review_state": {
            "safety_history": "",
            "repair_history": "",
            "judge_decision": "",
            "latest_speaker": "",
            "count": 0,
        },
        "final_diagnosis": "",
        "structured_result": {},
    }

