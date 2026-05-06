"""Task queue adapters for diagnosis jobs."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class TaskQueue(Protocol):
    async def initialize(self) -> None:
        ...

    async def close(self) -> None:
        ...

    async def put(self, task_id: str) -> None:
        ...

    async def get(self) -> str:
        ...

    async def qsize(self) -> int:
        ...

    def task_done(self) -> None:
        ...

    async def join(self) -> None:
        ...

    async def remove(self, task_id: str) -> int:
        ...


class InMemoryTaskQueue:
    def __init__(self, maxsize: int = 100) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)

    async def initialize(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def put(self, task_id: str) -> None:
        self._queue.put_nowait(task_id)

    async def get(self) -> str:
        return await self._queue.get()

    async def qsize(self) -> int:
        return self._queue.qsize()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    async def remove(self, task_id: str) -> int:
        removed = 0
        retained: list[str] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if item == task_id:
                removed += 1
                self._queue.task_done()
            else:
                retained.append(item)
        for item in retained:
            self._queue.put_nowait(item)
        return removed


class RedisTaskQueue:
    def __init__(self, redis_url: str, queue_name: str, max_size: int = 100) -> None:
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.max_size = max_size
        self._redis: Any = None

    async def initialize(self) -> None:
        if self._redis is not None:
            return
        from redis import asyncio as redis_asyncio

        self._redis = redis_asyncio.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def put(self, task_id: str) -> None:
        await self.initialize()
        if await self.qsize() >= self.max_size:
            raise asyncio.QueueFull
        await self._redis.rpush(self.queue_name, task_id)

    async def get(self) -> str:
        await self.initialize()
        while True:
            item = await self._redis.blpop(self.queue_name, timeout=5)
            if item:
                _, task_id = item
                return task_id

    async def qsize(self) -> int:
        await self.initialize()
        return int(await self._redis.llen(self.queue_name))

    def task_done(self) -> None:
        return None

    async def join(self) -> None:
        return None

    async def remove(self, task_id: str) -> int:
        await self.initialize()
        return int(await self._redis.lrem(self.queue_name, 0, task_id))
