"""Typed entry points for untyped JSON (API responses, caches, schemas)."""

from __future__ import annotations

import json
from typing import Any

JsonObject = dict[str, Any]


def as_json_object(value: object) -> JsonObject:
    """Narrow a decoded JSON value to an object, refusing anything else."""
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object, got {type(value).__name__}")
    return value


def load_json_object(text: str) -> JsonObject:
    """Decode text that must hold a JSON object."""
    return as_json_object(json.loads(text))


def load_json_object_list(text: str) -> list[JsonObject]:
    """Decode text that must hold a JSON array of objects."""
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError(f"expected a JSON array, got {type(value).__name__}")
    return [as_json_object(item) for item in value]
