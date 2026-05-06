"""Shared MongoDB helpers for vehicle data providers."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from app.core.config import load_environment


def get_data_provider_mode() -> str:
    load_environment()
    return os.getenv("VEHICLE_DIAGNOSIS_DATA_PROVIDER", "auto").strip().lower()


@lru_cache
def get_database() -> Any | None:
    load_environment()
    mode = get_data_provider_mode()
    if mode == "mock":
        return None
    try:
        from pymongo import MongoClient
    except Exception:
        if mode == "mongo":
            raise
        return None

    uri = os.getenv("VEHICLE_DIAGNOSIS_MONGO_URI", "mongodb://127.0.0.1:27017")
    database = os.getenv("VEHICLE_DIAGNOSIS_MONGO_DATABASE", "vehicle_diagnosis")
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=1000)
        client.admin.command("ping")
    except Exception:
        if mode == "mongo":
            raise
        return None
    return client[database]


def strip_mongo_id(document: dict[str, Any] | None) -> dict[str, Any]:
    if not document:
        return {}
    cleaned = dict(document)
    cleaned.pop("_id", None)
    return cleaned


def strip_mongo_ids(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [strip_mongo_id(document) for document in documents]


def safe_find_one(collection: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return strip_mongo_id(collection.find_one(*args, **kwargs))
    except Exception:
        if get_data_provider_mode() == "mongo":
            raise
        return {}


def safe_find_many(collection: Any, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    try:
        sort_args = kwargs.pop("_sort", None)
        limit = kwargs.pop("_limit", None)
        cursor = collection.find(*args, **kwargs)
        if sort_args:
            cursor = cursor.sort(*sort_args)
        if limit:
            cursor = cursor.limit(limit)
        return strip_mongo_ids(list(cursor))
    except Exception:
        if get_data_provider_mode() == "mongo":
            raise
        return []
