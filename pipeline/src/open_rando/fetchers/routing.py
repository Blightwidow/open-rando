from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import requests

from open_rando.config import (
    OSRM_CACHE_DIRECTORY,
    OSRM_CACHE_TTL_SECONDS,
    OSRM_COOLDOWN_SECONDS,
    OSRM_HOST,
    OSRM_TABLE_URL,
    OSRM_TIMEOUT_SECONDS,
)
from open_rando.json_types import JsonObject, as_json_object, load_json_object

logger = logging.getLogger("open_rando")

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5
COORDINATE_PRECISION = 6
# OSRM's answer when a coordinate cannot be snapped to the walking network.
OFF_NETWORK_CODE = "NoSegment"


class RoutingUnavailableError(RuntimeError):
    """OSRM cannot answer: server down, overloaded, or rejecting the request."""


def fetch_pedestrian_distance_matrix(
    source: tuple[float, float],
    destinations: list[tuple[float, float]],
) -> list[float | None]:
    """Fetch walking distances in meters from source to each destination via OSRM table.

    source and destinations are (lat, lon) tuples. Returns one distance per destination;
    unreachable destinations yield None, and every destination is None when the
    source itself is off the walking network. Raises RoutingUnavailableError
    when OSRM is down.
    """
    if not destinations:
        return []

    cache_key = _build_table_cache_key(source, destinations)
    cached = _read_cache(cache_key)
    if cached is not None:
        return _parse_table_response(cached, len(destinations))

    coordinate_parts: list[str] = [
        f"{source[1]:.{COORDINATE_PRECISION}f},{source[0]:.{COORDINATE_PRECISION}f}"
    ]
    for destination_latitude, destination_longitude in destinations:
        coordinate_parts.append(
            f"{destination_longitude:.{COORDINATE_PRECISION}f},"
            f"{destination_latitude:.{COORDINATE_PRECISION}f}"
        )

    destination_indices = ";".join(str(index) for index in range(1, len(destinations) + 1))
    url = (
        f"{OSRM_TABLE_URL}/"
        f"{';'.join(coordinate_parts)}"
        f"?sources=0&destinations={destination_indices}&annotations=distance"
    )

    response_data = _fetch_with_retry(url)
    if response_data is None:
        return [None] * len(destinations)

    _write_cache(cache_key, response_data)
    time.sleep(OSRM_COOLDOWN_SECONDS)

    return _parse_table_response(response_data, len(destinations))


def _parse_table_response(
    data: JsonObject,
    destination_count: int,
) -> list[float | None]:
    """Extract one row of walking distances from an OSRM table response."""
    try:
        distances_row = data["distances"][0]
    except (KeyError, IndexError, TypeError):
        logger.warning("Failed to parse OSRM table response")
        return [None] * destination_count

    result: list[float | None] = []
    for value in distances_row:
        if value is None:
            result.append(None)
        else:
            try:
                result.append(float(value))
            except (TypeError, ValueError):
                result.append(None)
    if len(result) != destination_count:
        logger.warning(
            "OSRM table returned %d distances, expected %d", len(result), destination_count
        )
        return [None] * destination_count
    return result


def _build_table_cache_key(
    source: tuple[float, float],
    destinations: list[tuple[float, float]],
) -> str:
    source_key = f"{source[1]:.{COORDINATE_PRECISION}f},{source[0]:.{COORDINATE_PRECISION}f}"
    destination_keys = ";".join(
        f"{longitude:.{COORDINATE_PRECISION}f},{latitude:.{COORDINATE_PRECISION}f}"
        for latitude, longitude in destinations
    )
    raw = f"table:{source_key}|{destination_keys}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _fetch_with_retry(url: str) -> JsonObject | None:
    """Fetch from OSRM, retrying transient errors.

    Returns None when OSRM answers that a point is off the network (NoSegment).
    Raises RoutingUnavailableError when OSRM cannot answer at all: a route
    whose junctions silently fall back to crow-fly distance is a wrong route,
    so it goes to failed-routes.json for --retry-failed instead.
    """
    last_problem = "no attempt made"
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.get(url, timeout=OSRM_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException as error:
            last_problem = f"request failed: {error}"
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("OSRM request failed, retrying in %ds...", wait)
            time.sleep(wait)
            continue

        if response.status_code in (429, 503, 504):
            last_problem = f"HTTP {response.status_code}"
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("OSRM %d, retrying in %ds...", response.status_code, wait)
            time.sleep(wait)
            continue

        try:
            data = as_json_object(response.json())
        except ValueError as error:
            raise RoutingUnavailableError(
                f"OSRM at {OSRM_HOST} returned HTTP {response.status_code} without JSON"
            ) from error
        code = data.get("code")
        if code == "Ok":
            return data
        if code == OFF_NETWORK_CODE:
            logger.warning("OSRM: a point is too far from any walkable way")
            return None
        raise RoutingUnavailableError(
            f"OSRM at {OSRM_HOST} returned HTTP {response.status_code}, code={code}"
        )

    raise RoutingUnavailableError(
        f"OSRM at {OSRM_HOST} unavailable after {RETRY_ATTEMPTS} attempts ({last_problem}). "
        "Start the local router with `make -f Makefile.osrm serve` (in pipeline/)."
    )


def _cache_path(cache_key: str) -> Path:
    cache_directory = Path(OSRM_CACHE_DIRECTORY).expanduser()
    cache_directory.mkdir(parents=True, exist_ok=True)
    return cache_directory / f"{cache_key}.json"


def _read_cache(cache_key: str) -> JsonObject | None:
    path = _cache_path(cache_key)
    if not path.exists():
        return None

    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > OSRM_CACHE_TTL_SECONDS:
        return None

    try:
        return load_json_object(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_key: str, data: JsonObject) -> None:
    path = _cache_path(cache_key)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        logger.warning("Failed to write OSRM cache to %s", path)
