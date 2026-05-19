"""Pydantic schemas for vehicle diagnosis API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SUPPORTED_ANALYSTS = {"vin_context", "symptom", "dtc", "knowledge", "experience"}
SUPPORTED_DEPTHS = {"quick", "basic", "standard"}


class VehicleInfo(BaseModel):
    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    model_year: int | None = None
    engine: str | dict[str, Any] | None = None
    mileage: int | None = None
    mileage_km: int | None = None
    powertrain_type: str | None = None
    region: str | None = None


class Symptom(BaseModel):
    name: str
    description: str | None = None
    condition: str | None = None
    severity: Literal["low", "medium", "high", "critical"] | str = "medium"
    frequency: str | None = None
    first_seen_at: str | None = None


class TimeRange(BaseModel):
    start: str | None = None
    end: str | None = None


class DiagnosisParameters(BaseModel):
    selected_analysts: list[str] = Field(
        default_factory=lambda: ["vin_context", "symptom", "dtc", "knowledge", "experience"]
    )
    diagnosis_depth: str = "standard"
    max_tool_calls: int | None = None
    analyst_max_tool_calls: dict[str, int] | None = None
    tool_timeout_seconds: float | None = None
    tool_max_retries: int | None = None

    @field_validator("selected_analysts")
    @classmethod
    def validate_selected_analysts(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("selected_analysts must include at least one analyst")
        unknown = [item for item in value if item not in SUPPORTED_ANALYSTS]
        if unknown:
            supported = ", ".join(sorted(SUPPORTED_ANALYSTS))
            raise ValueError(f"unknown analysts: {', '.join(unknown)}. Supported analysts: {supported}")
        return value

    @field_validator("diagnosis_depth")
    @classmethod
    def validate_diagnosis_depth(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in SUPPORTED_DEPTHS:
            supported = ", ".join(sorted(SUPPORTED_DEPTHS))
            raise ValueError(f"diagnosis_depth must be one of: {supported}")
        return normalized

    @field_validator("max_tool_calls")
    @classmethod
    def validate_max_tool_calls(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 0 or value > 20:
            raise ValueError("max_tool_calls must be between 0 and 20")
        return value

    @field_validator("analyst_max_tool_calls")
    @classmethod
    def validate_analyst_max_tool_calls(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return value
        unknown = [key for key in value if key not in SUPPORTED_ANALYSTS and key != "default"]
        if unknown:
            supported = ", ".join(sorted(SUPPORTED_ANALYSTS | {"default"}))
            raise ValueError(f"unknown analyst_max_tool_calls keys: {', '.join(unknown)}. Supported keys: {supported}")
        invalid = {key: count for key, count in value.items() if count < 0 or count > 20}
        if invalid:
            raise ValueError("analyst_max_tool_calls values must be between 0 and 20")
        return value

    @field_validator("tool_timeout_seconds")
    @classmethod
    def validate_tool_timeout_seconds(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if value < 0 or value > 120:
            raise ValueError("tool_timeout_seconds must be between 0 and 120")
        return value

    @field_validator("tool_max_retries")
    @classmethod
    def validate_tool_max_retries(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 0 or value > 5:
            raise ValueError("tool_max_retries must be between 0 and 5")
        return value


class VehicleDiagnosisRequest(BaseModel):
    vin: str | None = None
    vehicle: VehicleInfo = Field(default_factory=VehicleInfo)
    symptoms: list[Symptom] = Field(default_factory=list)
    dtc_codes: list[str] = Field(default_factory=list)
    freeze_frame: dict[str, Any] = Field(default_factory=dict)
    maintenance_history: list[dict[str, Any]] = Field(default_factory=list)
    time_range: TimeRange | None = None
    user_question: str | None = None
    user_id: str | None = None
    parameters: DiagnosisParameters = Field(default_factory=DiagnosisParameters)

    def to_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        if not data.get("vin") and data.get("vehicle", {}).get("vin"):
            data["vin"] = data["vehicle"]["vin"]
        return data


class DiagnosisOutcomeRequest(BaseModel):
    confirmed_root_cause: str
    repairs_performed: list[str] = Field(default_factory=list)
    resolved: bool = True
    notes: str | None = None
