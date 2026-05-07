"""SQLite persistence for diagnosis tasks."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from app.models.vehicle_diagnosis import DiagnosisTask


class VehicleDiagnosisRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    async def create_task(self, task: DiagnosisTask) -> None:
        await asyncio.to_thread(self._create_task_sync, task)

    async def save_task(self, task: DiagnosisTask) -> None:
        await asyncio.to_thread(self._save_task_sync, task)

    async def get_task(self, task_id: str) -> DiagnosisTask | None:
        return await asyncio.to_thread(self._get_task_sync, task_id)

    async def list_tasks_by_status(self, statuses: list[str]) -> list[DiagnosisTask]:
        return await asyncio.to_thread(self._list_tasks_by_status_sync, statuses)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicle_diagnosis_tasks (
                    task_id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    current_step TEXT NOT NULL,
                    queue_position INTEGER,
                    result_json TEXT,
                    state_json TEXT,
                    outcome_json TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_vehicle_diagnosis_tasks_status
                ON vehicle_diagnosis_tasks(status)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_vehicle_diagnosis_tasks_created_at
                ON vehicle_diagnosis_tasks(created_at)
                """
            )
            self._ensure_column(connection, "vehicle_diagnosis_tasks", "queue_position", "INTEGER")
            self._ensure_column(connection, "vehicle_diagnosis_tasks", "state_json", "TEXT")

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def _create_task_sync(self, task: DiagnosisTask) -> None:
        values = self._task_to_values(task)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vehicle_diagnosis_tasks (
                    task_id, request_json, status, progress, current_step, queue_position,
                    result_json, state_json, outcome_json, error_message,
                    created_at, updated_at, started_at, completed_at
                )
                VALUES (
                    :task_id, :request_json, :status, :progress, :current_step, :queue_position,
                    :result_json, :state_json, :outcome_json, :error_message,
                    :created_at, :updated_at, :started_at, :completed_at
                )
                """,
                values,
            )

    def _save_task_sync(self, task: DiagnosisTask) -> None:
        values = self._task_to_values(task)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE vehicle_diagnosis_tasks
                SET request_json = :request_json,
                    status = :status,
                    progress = :progress,
                    current_step = :current_step,
                    queue_position = :queue_position,
                    result_json = :result_json,
                    state_json = :state_json,
                    outcome_json = :outcome_json,
                    error_message = :error_message,
                    created_at = :created_at,
                    updated_at = :updated_at,
                    started_at = :started_at,
                    completed_at = :completed_at
                WHERE task_id = :task_id
                """,
                values,
            )

    def _get_task_sync(self, task_id: str) -> DiagnosisTask | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM vehicle_diagnosis_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def _list_tasks_by_status_sync(self, statuses: list[str]) -> list[DiagnosisTask]:
        if not statuses:
            return []
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM vehicle_diagnosis_tasks
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                statuses,
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def _task_to_values(self, task: DiagnosisTask) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "request_json": _dumps(task.request),
            "status": task.status,
            "progress": task.progress,
            "current_step": task.current_step,
            "queue_position": task.queue_position,
            "result_json": _dumps(task.result) if task.result is not None else None,
            "state_json": _dumps(_json_safe(task.state)) if task.state is not None else None,
            "outcome_json": _dumps(task.outcome) if task.outcome is not None else None,
            "error_message": task.error_message,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
        }

    def _row_to_task(self, row: sqlite3.Row) -> DiagnosisTask:
        return DiagnosisTask(
            task_id=row["task_id"],
            request=_loads(row["request_json"], {}),
            status=row["status"],
            progress=row["progress"],
            current_step=row["current_step"],
            queue_position=_row_value(row, "queue_position"),
            result=_loads(row["result_json"], None),
            state=_loads(_row_value(row, "state_json"), None),
            outcome=_loads(row["outcome_json"], None),
            error_message=row["error_message"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "type") and hasattr(value, "content"):
        data = {"type": getattr(value, "type", value.__class__.__name__), "content": value.content}
        tool_calls = getattr(value, "tool_calls", None)
        if tool_calls:
            data["tool_calls"] = _json_safe(tool_calls)
        tool_call_id = getattr(value, "tool_call_id", None)
        if tool_call_id:
            data["tool_call_id"] = tool_call_id
        message_id = getattr(value, "id", None)
        if message_id:
            data["id"] = message_id
        return data
    return str(value)


def _row_value(row: sqlite3.Row, key: str) -> Any:
    return row[key] if key in row.keys() else None
