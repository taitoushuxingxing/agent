"""LangGraph state definitions for vehicle diagnosis."""

from typing import Annotated, Any
from langgraph.graph import MessagesState


class VehicleDiagnosisState(MessagesState):
    diagnosis_id: Annotated[str, "Diagnosis id"]
    case_date: Annotated[str, "Case date"]
    vin: Annotated[str, "Vehicle identification number"]
    vehicle: Annotated[dict[str, Any], "Vehicle profile"]
    symptoms: Annotated[list[dict[str, Any]], "User reported symptoms"]
    dtc_codes: Annotated[list[str], "Submitted DTC codes"]
    dtc_history: Annotated[list[dict[str, Any]], "DTC history from VIN database"]
    freeze_frame: Annotated[dict[str, Any], "Freeze frame data"]
    maintenance_history: Annotated[list[dict[str, Any]], "Maintenance history"]
    user_question: Annotated[str, "User question"]

    vehicle_profile_report: Annotated[str, "VIN context report"]
    symptom_report: Annotated[str, "Symptom report"]
    dtc_report: Annotated[str, "DTC report"]
    knowledge_report: Annotated[str, "Knowledge report"]
    experience_report: Annotated[str, "Experience report"]

    vin_context_tool_call_count: Annotated[int, "VIN context tool calls"]
    symptom_tool_call_count: Annotated[int, "Symptom tool calls"]
    dtc_tool_call_count: Annotated[int, "DTC tool calls"]
    knowledge_tool_call_count: Annotated[int, "Knowledge tool calls"]
    experience_tool_call_count: Annotated[int, "Experience tool calls"]

    final_diagnosis: Annotated[str, "Final diagnosis"]
    structured_result: Annotated[dict[str, Any], "Machine readable result"]
    current_node: Annotated[str, "Current graph node"]
    graph_trace: Annotated[list[dict[str, Any]], "Graph transition trace"]
    analyst_conclusions: Annotated[dict[str, str], "Compact analyst conclusions"]
    analyst_tool_results: Annotated[dict[str, list[dict[str, Any]]], "Tool results grouped by analyst"]
    pending_tool_owner: Annotated[str, "Analyst currently waiting for tool output"]
    tool_errors: Annotated[list[dict[str, Any]], "Recoverable tool execution errors"]


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
        "freeze_frame": payload.get("freeze_frame") or {},
        "maintenance_history": payload.get("maintenance_history") or [],
        "user_question": payload.get("user_question") or "",
        "vehicle_profile_report": "",
        "symptom_report": "",
        "dtc_report": "",
        "knowledge_report": "",
        "experience_report": "",
        "vin_context_tool_call_count": 0,
        "symptom_tool_call_count": 0,
        "dtc_tool_call_count": 0,
        "knowledge_tool_call_count": 0,
        "experience_tool_call_count": 0,
        "final_diagnosis": "",
        "structured_result": {},
        "current_node": "START",
        "graph_trace": [
            {
                "node": "START",
                "status": "entered",
                "detail": "initial_state_created",
            }
        ],
        "analyst_conclusions": {},
        "analyst_tool_results": {},
        "pending_tool_owner": "",
        "tool_errors": [],
    }
