"""Default configuration for the vehicle diagnosis agent."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_VEHICLE_CONFIG = {
    "project_dir": str(PROJECT_ROOT),
    "llm_provider": "openai",
    "quick_think_llm": "gpt-4o-mini",
    "deep_think_llm": "gpt-4o",
    "backend_url": "https://api.openai.com/v1",
    "max_tool_calls": 2,
    "analyst_max_tool_calls": {
        "vin_context": 2,
        "symptom": 1,
        "dtc": 4,
        "telemetry": 3,
        "knowledge": 1,
    },
    "tool_timeout_seconds": 10,
    "tool_max_retries": 1,
    "max_debate_rounds": 1,
    "max_safety_discuss_rounds": 1,
    "memory_enabled": True,
    "knowledge_base_dir": str(PROJECT_ROOT / "data" / "vehicle_knowledge"),
    "result_dir": str(PROJECT_ROOT / "results" / "vehicle_diagnosis"),
    "vin_database": {
        "provider": "mock",
        "uri_env": "VEHICLE_VIN_DB_URI",
        "database": "vehicle_data",
    },
}
