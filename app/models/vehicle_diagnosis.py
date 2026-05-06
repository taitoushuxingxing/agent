"""Internal task model helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DiagnosisTask:
    task_id: str
    request: dict[str, Any]
    status: str = "submitted"
    progress: int = 0
    current_step: str = "submitted"
    queue_position: int | None = None
    result: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None

    def to_status(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "queue_position": self.queue_position,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
