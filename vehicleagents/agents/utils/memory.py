"""Memory abstraction for vehicle diagnosis cases.

The interface is intentionally small: planners ask for similar historical
cases, and outcome feedback writes confirmed cases. The default in-process
store keeps tests fast, while SQLiteVehicleMemoryStore provides durable storage
for the API service. A vector store can replace either backend without changing
agent code.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


class VehicleMemoryStore(Protocol):
    def add_case(self, situation: str, recommendation: str, metadata: dict[str, Any] | None = None) -> None:
        ...

    def search(self, current_situation: str, n_matches: int = 3) -> list[dict[str, Any]]:
        ...


class InMemoryVehicleMemoryStore:
    def __init__(self) -> None:
        self._items: list[dict[str, Any]] = []

    def add_case(self, situation: str, recommendation: str, metadata: dict[str, Any] | None = None) -> None:
        self._items.append(
            {
                "situation": situation,
                "recommendation": recommendation,
                "metadata": metadata or {},
                "score": 1.0,
            }
        )

    def search(self, current_situation: str, n_matches: int = 3) -> list[dict[str, Any]]:
        scored = _rank_by_token_overlap(self._items, current_situation)
        return scored[:n_matches]


class SQLiteVehicleMemoryStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._initialized = False

    def add_case(self, situation: str, recommendation: str, metadata: dict[str, Any] | None = None) -> None:
        self._initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO vehicle_memory_cases (
                    memory_id, situation, recommendation, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    situation,
                    recommendation,
                    json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def search(self, current_situation: str, n_matches: int = 3) -> list[dict[str, Any]]:
        self._initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT situation, recommendation, metadata_json, created_at
                FROM vehicle_memory_cases
                ORDER BY created_at DESC
                LIMIT 100
                """
            ).fetchall()
        items = [
            {
                "situation": row["situation"],
                "recommendation": row["recommendation"],
                "metadata": _loads(row["metadata_json"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]
        return _rank_by_token_overlap(items, current_situation)[:n_matches]

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        if self._initialized:
            return
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS vehicle_memory_cases (
                    memory_id TEXT PRIMARY KEY,
                    situation TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_vehicle_memory_cases_created_at
                ON vehicle_memory_cases(created_at)
                """
            )
        self._initialized = True


class MongoVehicleMemoryStore:
    def __init__(self, mongo_uri: str, database: str) -> None:
        self.mongo_uri = mongo_uri
        self.database_name = database
        self._client: Any = None
        self._collection: Any = None

    def add_case(self, situation: str, recommendation: str, metadata: dict[str, Any] | None = None) -> None:
        self._initialize()
        self._collection.insert_one(
            {
                "memory_id": str(uuid4()),
                "situation": situation,
                "recommendation": recommendation,
                "metadata": metadata or {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def search(self, current_situation: str, n_matches: int = 3) -> list[dict[str, Any]]:
        self._initialize()
        documents = self._collection.find({}, {"_id": 0}).sort("created_at", -1).limit(100)
        items = list(documents)
        return _rank_by_token_overlap(items, current_situation)[:n_matches]

    def _initialize(self) -> None:
        if self._collection is not None:
            return
        from pymongo import ASCENDING, MongoClient

        self._client = MongoClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
        self._client.admin.command("ping")
        database = self._client[self.database_name]
        self._collection = database.vehicle_memory_cases
        self._collection.create_index([("created_at", ASCENDING)])


class VehicleDiagnosisMemory:
    def __init__(self, store: VehicleMemoryStore | None = None) -> None:
        self.store = store or InMemoryVehicleMemoryStore()

    def add_case(self, situation: str, recommendation: str, metadata: dict[str, Any] | None = None) -> None:
        self.store.add_case(situation, recommendation, metadata)

    def get_memories(self, current_situation: str, n_matches: int = 3) -> list[dict[str, Any]]:
        return self.store.search(current_situation, n_matches)


def _rank_by_token_overlap(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    ranked: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        item_tokens = _tokens(f"{item.get('situation', '')} {item.get('recommendation', '')}")
        overlap = len(query_tokens.intersection(item_tokens))
        score = overlap / max(len(query_tokens), 1)
        ranked_item = dict(item)
        ranked_item["score"] = score
        ranked_item["_recency_rank"] = index
        ranked.append(ranked_item)
    ranked.sort(key=lambda item: (item["score"], -item["_recency_rank"]), reverse=True)
    for item in ranked:
        item.pop("_recency_rank", None)
    return ranked


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9_]+", value)}


def _loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    return json.loads(value)
