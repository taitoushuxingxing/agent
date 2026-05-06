"""Redis-backed request rate limiting."""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("vehicle_diagnosis.rate_limit")


class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, redis_url: str, window_seconds: int, max_requests: int) -> None:
        super().__init__(app)
        self.redis_url = redis_url
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._redis: Any = None

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        redis = await self._get_redis()
        client = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client}:{request.url.path}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds)
        if count > self.max_requests:
            logger.warning(
                "rate_limited",
                extra={
                    "_client": client,
                    "_path": request.url.path,
                    "_count": count,
                    "_max_requests": self.max_requests,
                },
            )
            return JSONResponse(
                status_code=429,
                content={"success": False, "detail": "rate limit exceeded"},
                headers={"Retry-After": str(self.window_seconds)},
            )
        return await call_next(request)

    async def _get_redis(self):
        if self._redis is None:
            from redis import asyncio as redis_asyncio

            self._redis = redis_asyncio.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
        return self._redis
