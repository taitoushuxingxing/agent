"""Application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


def load_environment() -> None:
    """Load local .env values without overriding real environment variables."""
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(ENV_FILE, override=False)


@dataclass(frozen=True)
class AppSettings:
    app_name: str
    environment: str
    data_dir: Path
    sqlite_path: Path
    mongo_uri: str
    mongo_database: str
    data_provider: str
    redis_url: str
    redis_queue_name: str
    cors_origins: list[str]
    log_level: str
    worker_concurrency: int
    queue_max_size: int
    task_timeout_seconds: int
    rate_limit_window_seconds: int
    rate_limit_max_requests: int
    llm_config_path: Path
    graph_cache_max_size: int
    graph_cache_ttl_seconds: int


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> AppSettings:
    load_environment()
    data_dir = Path(os.getenv("VEHICLE_DIAGNOSIS_DATA_DIR", PROJECT_ROOT / "data")).resolve()
    sqlite_path = Path(
        os.getenv("VEHICLE_DIAGNOSIS_DB_PATH", data_dir / "vehicle_diagnosis.sqlite3")
    ).resolve()
    llm_config_path = Path(
        os.getenv("VEHICLE_DIAGNOSIS_LLM_CONFIG_PATH", PROJECT_ROOT / "config" / "llm_config.json")
    ).resolve()
    cors_origins = _split_csv(os.getenv("VEHICLE_DIAGNOSIS_CORS_ORIGINS", "*"))
    return AppSettings(
        app_name=os.getenv("VEHICLE_DIAGNOSIS_APP_NAME", "Vehicle Fault Diagnosis Agent"),
        environment=os.getenv("VEHICLE_DIAGNOSIS_ENV", "local"),
        data_dir=data_dir,
        sqlite_path=sqlite_path,
        mongo_uri=os.getenv("VEHICLE_DIAGNOSIS_MONGO_URI", "mongodb://127.0.0.1:27017"),
        mongo_database=os.getenv("VEHICLE_DIAGNOSIS_MONGO_DATABASE", "vehicle_diagnosis"),
        data_provider=os.getenv("VEHICLE_DIAGNOSIS_DATA_PROVIDER", "auto").lower(),
        redis_url=os.getenv("VEHICLE_DIAGNOSIS_REDIS_URL", "redis://127.0.0.1:6379/0"),
        redis_queue_name=os.getenv("VEHICLE_DIAGNOSIS_REDIS_QUEUE", "vehicle_diagnosis:tasks"),
        cors_origins=cors_origins or ["*"],
        log_level=os.getenv("VEHICLE_DIAGNOSIS_LOG_LEVEL", "INFO"),
        worker_concurrency=int(os.getenv("VEHICLE_DIAGNOSIS_WORKER_CONCURRENCY", "2")),
        queue_max_size=int(os.getenv("VEHICLE_DIAGNOSIS_QUEUE_MAX_SIZE", "100")),
        task_timeout_seconds=int(os.getenv("VEHICLE_DIAGNOSIS_TASK_TIMEOUT_SECONDS", "120")),
        rate_limit_window_seconds=int(os.getenv("VEHICLE_DIAGNOSIS_RATE_LIMIT_WINDOW_SECONDS", "60")),
        rate_limit_max_requests=int(os.getenv("VEHICLE_DIAGNOSIS_RATE_LIMIT_MAX_REQUESTS", "120")),
        llm_config_path=llm_config_path,
        graph_cache_max_size=int(os.getenv("VEHICLE_DIAGNOSIS_GRAPH_CACHE_MAX_SIZE", "8")),
        graph_cache_ttl_seconds=int(os.getenv("VEHICLE_DIAGNOSIS_GRAPH_CACHE_TTL_SECONDS", "1800")),
    )
