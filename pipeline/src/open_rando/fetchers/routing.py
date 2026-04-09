from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from pathlib import Path

import requests
from shapely.geometry import LineString

from open_rando.config import (
    OSRM_BASE_URL,
    OSRM_CACHE_DIRECTORY,
    OSRM_CACHE_TTL_SECONDS,
    OSRM_COOLDOWN_SECONDS,
    OSRM_TIMEOUT_SECONDS,
)

logger = logging.getLogger("open_rando")

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 5
EARTH_RADIUS_METERS = 6_371_000
COORDINATE_PRECISION = 6


def fetch_pedestrian_route(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> tuple[LineString | None, float, bool]:
    """Fetch a pedestrian walking route from OSRM.

    Returns (geometry, distance_km, cache_hit).
    On any failure, returns (None, 0.0, False).
    """
    cache_key = _build_cache_key(origin_lat, origin_lon, destination_lat, destination_lon)
    cached = _read_cache(cache_key)
    if cached is not None:
        geometry, distance_km = _parse_osrm_response(cached)
        return geometry, distance_km, True

    url = (
        f"{OSRM_BASE_URL}/"
        f"{origin_lon:.{COORDINATE_PRECISION}f},{origin_lat:.{COORDINATE_PRECISION}f};"
        f"{destination_lon:.{COORDINATE_PRECISION}f},{destination_lat:.{COORDINATE_PRECISION}f}"
        f"?overview=full&geometries=geojson"
    )

    response_data = _fetch_with_retry(url)
    if response_data is None:
        return None, 0.0, False

    _write_cache(cache_key, response_data)
    time.sleep(OSRM_COOLDOWN_SECONDS)

    geometry, distance_km = _parse_osrm_response(response_data)
    return geometry, distance_km, False


def make_straight_line_connector(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> tuple[LineString, float]:
    """Create a straight-line connector between two points.

    Returns (geometry, distance_km).
    """
    geometry = LineString([(origin_lon, origin_lat), (destination_lon, destination_lat)])
    distance_km = _haversine_km(origin_lat, origin_lon, destination_lat, destination_lon)
    return geometry, distance_km


def _parse_osrm_response(data: dict) -> tuple[LineString | None, float]:  # type: ignore[type-arg]
    """Extract geometry and distance from an OSRM response."""
    try:
        route = data["routes"][0]
        coordinates = route["geometry"]["coordinates"]
        distance_meters = route["distance"]
        if len(coordinates) < 2:
            return None, 0.0
        return LineString(coordinates), distance_meters / 1000.0
    except (KeyError, IndexError, TypeError):
        logger.warning("Failed to parse OSRM response")
        return None, 0.0


def _fetch_with_retry(url: str) -> dict | None:  # type: ignore[type-arg]
    """Fetch from OSRM with retry on transient errors."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.get(url, timeout=OSRM_TIMEOUT_SECONDS)
        except requests.exceptions.RequestException:
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("OSRM request failed, retrying in %ds...", wait)
            time.sleep(wait)
            continue

        if response.status_code in (429, 503, 504):
            wait = RETRY_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("OSRM %d, retrying in %ds...", response.status_code, wait)
            time.sleep(wait)
            continue

        if response.status_code != 200:
            logger.warning("OSRM returned %d", response.status_code)
            return None

        data = response.json()
        if data.get("code") != "Ok":
            logger.warning("OSRM returned code=%s", data.get("code"))
            return None

        return data  # type: ignore[no-any-return]

    logger.warning("OSRM failed after %d attempts", RETRY_ATTEMPTS)
    return None


def _build_cache_key(
    origin_lat: float,
    origin_lon: float,
    destination_lat: float,
    destination_lon: float,
) -> str:
    raw = (
        f"{origin_lon:.{COORDINATE_PRECISION}f},{origin_lat:.{COORDINATE_PRECISION}f};"
        f"{destination_lon:.{COORDINATE_PRECISION}f},{destination_lat:.{COORDINATE_PRECISION}f}"
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_path(cache_key: str) -> Path:
    cache_directory = Path(OSRM_CACHE_DIRECTORY).expanduser()
    cache_directory.mkdir(parents=True, exist_ok=True)
    return cache_directory / f"{cache_key}.json"


def _read_cache(cache_key: str) -> dict | None:  # type: ignore[type-arg]
    path = _cache_path(cache_key)
    if not path.exists():
        return None

    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > OSRM_CACHE_TTL_SECONDS:
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _write_cache(cache_key: str, data: dict) -> None:  # type: ignore[type-arg]
    path = _cache_path(cache_key)
    try:
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        logger.warning("Failed to write OSRM cache to %s", path)


def _haversine_km(
    latitude_1: float,
    longitude_1: float,
    latitude_2: float,
    longitude_2: float,
) -> float:
    """Distance in kilometers between two WGS84 points."""
    phi_1 = math.radians(latitude_1)
    phi_2 = math.radians(latitude_2)
    delta_phi = math.radians(latitude_2 - latitude_1)
    delta_lambda = math.radians(longitude_2 - longitude_1)

    half_chord = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2) ** 2
    )
    return (
        EARTH_RADIUS_METERS
        * 2
        * math.atan2(math.sqrt(half_chord), math.sqrt(1 - half_chord))
        / 1000.0
    )
