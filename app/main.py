"""Standalone FastAPI entrypoint for the vehicle diagnosis service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.logging import configure_logging
from .middleware.rate_limit import RedisRateLimitMiddleware
from .middleware.request_logging import RequestLoggingMiddleware
from .routers.vehicle_diagnosis import router as vehicle_diagnosis_router
from .services.vehicle_diagnosis_service import get_vehicle_diagnosis_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    service = get_vehicle_diagnosis_service()
    await service.initialize()
    await service.start_workers()
    yield
    await service.stop_workers()


settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    RedisRateLimitMiddleware,
    redis_url=settings.redis_url,
    window_seconds=settings.rate_limit_window_seconds,
    max_requests=settings.rate_limit_max_requests,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials="*" not in settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(vehicle_diagnosis_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.environment}
