from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import requests

from open_rando.config import (
    OVERPASS_API_URL,
    OVERPASS_CACHE_DIRECTORY,
    OVERPASS_CACHE_TTL_SECONDS,
    OVERPASS_TIMEOUT_SECONDS,
)
from open_rando.json_types import JsonObject, as_json_object, load_json_object

logger = logging.getLogger("open_rando")

RETRY_ATTEMPTS = 5
RETRY_BACKOFF_SECONDS = 15


def query_overpass(
    query: str,
    cache_ttl_seconds: int | None = None,
) -> tuple[JsonObject, bool]:
    """Query Overpass API with disk caching.

    Responses are cached by query hash. Pass cache_ttl_seconds to override default TTL,
    or 0 to bypass cache entirely.

    Returns (data, cache_hit) where cache_hit is True if the response came from cache.
    """
    ttl = cache_ttl_seconds if cache_ttl_seconds is not None else OVERPASS_CACHE_TTL_SECONDS

    if ttl > 0:
        cached = _read_cache(query, ttl)
        if cached is not None:
            return cached, True

    result = _fetch_overpass(query)

    if ttl > 0:
        _write_cache(query, result)

    return result, False


def _fetch_overpass(query: str) -> JsonObject:
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.post(
                OVERPASS_API_URL,
                data={"data": query},
                headers={"User-Agent": "open-rando-pipeline/0.1"},
                timeout=OVERPASS_TIMEOUT_SECONDS + 30,
            )
        except requests.exceptions.Timeout:
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("Request timeout, retrying in %ds...", wait)
            time.sleep(wait)
            continue

        if response.status_code in (429, 504):
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("Overpass %d, retrying in %ds...", response.status_code, wait)
            time.sleep(wait)
            continue
        response.raise_for_status()
        return as_json_object(response.json())
    raise RuntimeError("Overpass API failed after retries")


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]


def _cache_path(query: str) -> Path:
    cache_directory = Path(OVERPASS_CACHE_DIRECTORY).expanduser()
    cache_directory.mkdir(parents=True, exist_ok=True)
    return cache_directory / f"{_cache_key(query)}.json"


def _read_cache(query: str, ttl_seconds: int) -> JsonObject | None:
    path = _cache_path(query)
    if not path.exists():
        return None

    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > ttl_seconds:
        logger.info("Cache expired for %s (%.0fs old)", path.name, age_seconds)
        return None

    logger.info("Using cached response %s (%.0fs old)", path.name, age_seconds)
    return load_json_object(path.read_text(encoding="utf-8"))


def _write_cache(query: str, data: JsonObject) -> None:
    path = _cache_path(query)
    path.write_text(json.dumps(data), encoding="utf-8")
    logger.info("Cached Overpass response to %s", path.name)
