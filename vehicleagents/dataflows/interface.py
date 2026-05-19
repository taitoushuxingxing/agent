"""Unified dataflow interface for VIN, DTC, and case data."""

from __future__ import annotations

from typing import Any

from .providers import local_cases, local_dtc, vin_database


def get_vehicle_profile_by_vin(vin: str) -> dict[str, Any]:
    return vin_database.get_vehicle_profile_by_vin(vin)


def get_dtc_history_by_vin(vin: str, time_range: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return vin_database.get_dtc_history_by_vin(vin, time_range)


def get_maintenance_history_by_vin(vin: str) -> list[dict[str, Any]]:
    return vin_database.get_maintenance_history_by_vin(vin)


def lookup_dtc_code(code: str, vehicle: dict[str, Any] | None = None) -> dict[str, Any]:
    return local_dtc.lookup_dtc_code(code, vehicle or {})


def search_dtc_combinations(codes: list[str]) -> list[dict[str, Any]]:
    return local_dtc.search_dtc_combinations(codes)


def retrieve_repair_cases(query: dict[str, Any]) -> list[dict[str, Any]]:
    return local_cases.retrieve_repair_cases(query)
