"""Vehicle diagnosis API routes."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from ..schemas.vehicle_diagnosis import DiagnosisOutcomeRequest, VehicleDiagnosisRequest
from ..services.vehicle_diagnosis_service import get_vehicle_diagnosis_service


router = APIRouter(prefix="/api/vehicle-diagnosis", tags=["vehicle-diagnosis"])


@router.post("/tasks")
async def create_diagnosis_task(request: VehicleDiagnosisRequest) -> dict[str, Any]:
    service = get_vehicle_diagnosis_service()
    try:
        result = await service.submit_task(request.to_payload())
    except asyncio.QueueFull as exc:
        raise HTTPException(status_code=503, detail="diagnosis queue is full") from exc
    return {"success": True, "data": result, "message": "diagnosis task queued"}


@router.get("/tasks/{task_id}/status")
async def get_diagnosis_status(task_id: str) -> dict[str, Any]:
    service = get_vehicle_diagnosis_service()
    status = await service.get_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="task not found")
    return {"success": True, "data": status}


@router.get("/tasks/{task_id}/result")
async def get_diagnosis_result(task_id: str) -> dict[str, Any]:
    service = get_vehicle_diagnosis_service()
    result = await service.get_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="task not found")
    return {"success": True, "data": result}


@router.post("/tasks/{task_id}/cancel")
async def cancel_diagnosis_task(task_id: str) -> dict[str, Any]:
    service = get_vehicle_diagnosis_service()
    result = await service.cancel_task(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="task not found")
    return {"success": True, "data": result}


@router.post("/tasks/{task_id}/outcome")
async def record_diagnosis_outcome(task_id: str, request: DiagnosisOutcomeRequest) -> dict[str, Any]:
    service = get_vehicle_diagnosis_service()
    result = await service.record_outcome(task_id, request.model_dump(mode="json"))
    if not result:
        raise HTTPException(status_code=404, detail="task not found")
    return {"success": True, "data": result}
