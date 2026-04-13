from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import requests

from open_rando.config import (
    GTFS_CACHE_DIRECTORY,
    GTFS_CACHE_TTL_SECONDS,
    GTFS_DATASETS_API_URL,
    GTFS_FEEDS_CACHE_DIRECTORY,
    GTFS_MATCH_RADIUS_METERS,
    GTFS_STOPS_API_URL,
)
from open_rando.models import Station

logger = logging.getLogger("open_rando")

REQUEST_TIMEOUT_SECONDS = 60
FEED_DOWNLOAD_TIMEOUT_SECONDS = 120
TRAIN_ROUTE_SENTINEL = "__train__"

# Approximate meters per degree at mid-latitudes (France ~46°N)
METERS_PER_DEGREE_LAT = 111_320
METERS_PER_DEGREE_LON_AT_46 = 77_400


@dataclass
class GtfsStop:
    latitude: float
    longitude: float
    stop_id: str
    resource_id: int


# ---------------------------------------------------------------------------
# 1. Fetch GTFS stops (enhanced with stop_id and resource_id)
# ---------------------------------------------------------------------------


def fetch_gtfs_stops(
    south: float,
    west: float,
    north: float,
    east: float,
) -> tuple[list[GtfsStop], bool]:
    """Fetch GTFS-indexed stops from transport.data.gouv.fr.

    Returns (list of GtfsStop, cache_hit).
    """
    cache_key = _bbox_cache_key(south, west, north, east)
    cached = _read_stops_cache(cache_key)
    if cached is not None:
        return cached, True

    url = f"{GTFS_STOPS_API_URL}?south={south}&north={north}&west={west}&east={east}"

    logger.info("Fetching GTFS stops for bbox (%.2f,%.2f)-(%.2f,%.2f)", south, west, north, east)

    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    data = response.json()

    stops: list[GtfsStop] = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry", {})
        properties = feature.get("properties", {})
        if geometry.get("type") != "Point":
            continue
        coords = geometry.get("coordinates", [])
        if len(coords) < 2:
            continue
        stop_id = properties.get("stop_id", "")
        resource_id = properties.get("resource_id")
        if not stop_id or resource_id is None:
            continue
        stops.append(
            GtfsStop(
                latitude=coords[1],
                longitude=coords[0],
                stop_id=stop_id,
                resource_id=int(resource_id),
            )
        )

    logger.info("Found %d GTFS stops in bbox", len(stops))
    _write_stops_cache(cache_key, stops)
    return stops, False


# ---------------------------------------------------------------------------
# 2. Filter bus stops by GTFS proximity + annotate with matched GTFS stop IDs
# ---------------------------------------------------------------------------


def filter_and_annotate_bus_stops(
    stations: list[Station],
    gtfs_stops: list[GtfsStop],
) -> tuple[list[Station], dict[str, list[GtfsStop]]]:
    """Keep train stations unconditionally; keep bus stops near a GTFS stop.

    Returns (filtered_stations, gtfs_stop_id_map) where gtfs_stop_id_map
    maps station codes to their matched GTFS stops (for route connectivity).
    """
    gtfs_stop_id_map: dict[str, list[GtfsStop]] = {}

    if not gtfs_stops:
        train_stations = [station for station in stations if station.transport_type == "train"]
        for station in train_stations:
            station.connected_route_ids = {TRAIN_ROUTE_SENTINEL}
        dropped = len(stations) - len(train_stations)
        if dropped > 0:
            logger.info("No GTFS data available, dropped %d bus stops", dropped)
        return train_stations, gtfs_stop_id_map

    filtered: list[Station] = []
    dropped_count = 0

    for station in stations:
        if station.transport_type == "train":
            station.connected_route_ids = {TRAIN_ROUTE_SENTINEL}
            filtered.append(station)
            continue

        matched_gtfs = _find_nearby_gtfs_stops(station.lat, station.lon, gtfs_stops)
        if matched_gtfs:
            gtfs_stop_id_map[station.code] = matched_gtfs
            filtered.append(station)
        else:
            dropped_count += 1
            logger.debug(
                "Dropped bus stop without GTFS match: %s (%.4f, %.4f)",
                station.name,
                station.lat,
                station.lon,
            )

    if dropped_count > 0:
        bus_kept = sum(1 for station in filtered if station.transport_type == "bus")
        logger.info(
            "GTFS filter: kept %d bus stops, dropped %d without GTFS match",
            bus_kept,
            dropped_count,
        )

    return filtered, gtfs_stop_id_map


def _find_nearby_gtfs_stops(
    latitude: float,
    longitude: float,
    gtfs_stops: list[GtfsStop],
) -> list[GtfsStop]:
    """Find all GTFS stops within GTFS_MATCH_RADIUS_METERS."""
    threshold_lat = GTFS_MATCH_RADIUS_METERS / METERS_PER_DEGREE_LAT
    threshold_lon = GTFS_MATCH_RADIUS_METERS / METERS_PER_DEGREE_LON_AT_46

    matches: list[GtfsStop] = []
    for gtfs_stop in gtfs_stops:
        delta_lat = abs(latitude - gtfs_stop.latitude)
        if delta_lat > threshold_lat:
            continue
        delta_lon = abs(longitude - gtfs_stop.longitude)
        if delta_lon > threshold_lon:
            continue
        distance_meters = math.sqrt(
            (delta_lat * METERS_PER_DEGREE_LAT) ** 2
            + (delta_lon * METERS_PER_DEGREE_LON_AT_46) ** 2
        )
        if distance_meters <= GTFS_MATCH_RADIUS_METERS:
            matches.append(gtfs_stop)
    return matches


# ---------------------------------------------------------------------------
# 3. GTFS route connectivity: download feeds, parse, build stop→routes map
# ---------------------------------------------------------------------------


def fetch_resource_url_map() -> dict[int, str]:
    """Fetch the resource_id → download URL mapping from transport.data.gouv.fr.

    Cached to disk for 30 days.
    """
    cache_path = _generic_cache_path("resource_url_map")
    cached = _read_generic_cache(cache_path)
    if cached is not None:
        return {int(key): value for key, value in cached.items()}

    logger.info("Fetching dataset catalog from transport.data.gouv.fr")
    response = requests.get(GTFS_DATASETS_API_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    datasets = response.json()

    resource_map: dict[int, str] = {}
    for dataset in datasets:
        for resource in dataset.get("resources", []):
            if resource.get("format") == "GTFS" and resource.get("is_available"):
                resource_id = resource.get("id")
                url = resource.get("url", "")
                if resource_id and url:
                    resource_map[int(resource_id)] = url

    logger.info("Built resource URL map with %d GTFS feeds", len(resource_map))
    _write_generic_cache(cache_path, {str(key): value for key, value in resource_map.items()})
    return resource_map


def fetch_gtfs_route_connectivity(
    resource_ids: set[int],
    resource_url_map: dict[int, str],
) -> dict[str, set[str]]:
    """Download GTFS feeds and build stop_id → set[route_id] mapping.

    Only downloads feeds for the given resource_ids.
    Returns a combined mapping across all feeds.
    """
    combined_connectivity: dict[str, set[str]] = {}

    for resource_id in resource_ids:
        url = resource_url_map.get(resource_id)
        if not url:
            logger.warning("No download URL for GTFS resource %d", resource_id)
            continue

        connectivity = _fetch_feed_connectivity(resource_id, url)
        for stop_id, route_ids in connectivity.items():
            if stop_id in combined_connectivity:
                combined_connectivity[stop_id].update(route_ids)
            else:
                combined_connectivity[stop_id] = set(route_ids)

    logger.info(
        "Built route connectivity for %d stops from %d feeds",
        len(combined_connectivity),
        len(resource_ids),
    )
    return combined_connectivity


def _fetch_feed_connectivity(resource_id: int, url: str) -> dict[str, set[str]]:
    """Download a single GTFS feed and extract stop_id → route_ids mapping.

    Cached per resource_id.
    """
    cache_path = _generic_cache_path(f"feed_connectivity_{resource_id}")
    cached = _read_generic_cache(cache_path)
    if cached is not None:
        return {stop_id: set(route_ids) for stop_id, route_ids in cached.items()}

    logger.info("Downloading GTFS feed for resource %d", resource_id)

    try:
        response = requests.get(url, timeout=FEED_DOWNLOAD_TIMEOUT_SECONDS, allow_redirects=True)
        response.raise_for_status()
    except (requests.RequestException, requests.Timeout) as error:
        logger.warning("Failed to download GTFS feed %d: %s", resource_id, error)
        return {}

    try:
        connectivity = _parse_gtfs_zip(response.content)
    except (zipfile.BadZipFile, KeyError, csv.Error) as error:
        logger.warning("Failed to parse GTFS feed %d: %s", resource_id, error)
        return {}

    # Cache as JSON-serializable format
    serializable = {stop_id: list(route_ids) for stop_id, route_ids in connectivity.items()}
    _write_generic_cache(cache_path, serializable)

    logger.info(
        "Parsed GTFS feed %d: %d stops with route connectivity",
        resource_id,
        len(connectivity),
    )
    return connectivity


def _parse_gtfs_zip(content: bytes) -> dict[str, set[str]]:
    """Parse a GTFS zip in memory, extracting stop_id → route_ids mapping.

    Only reads trips.txt and stop_times.txt (streaming to minimize memory).
    """
    with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
        # Step 1: Build trip_id → route_id from trips.txt
        trip_to_route: dict[str, str] = {}
        with zip_file.open("trips.txt") as trips_file:
            reader = csv.DictReader(io.TextIOWrapper(trips_file, encoding="utf-8-sig"))
            for row in reader:
                trip_id = row.get("trip_id", "")
                route_id = row.get("route_id", "")
                if trip_id and route_id:
                    trip_to_route[trip_id] = route_id

        # Step 2: Build stop_id → route_ids from stop_times.txt
        stop_to_routes: dict[str, set[str]] = {}
        with zip_file.open("stop_times.txt") as stop_times_file:
            reader = csv.DictReader(io.TextIOWrapper(stop_times_file, encoding="utf-8-sig"))
            for row in reader:
                stop_id = row.get("stop_id", "")
                trip_id = row.get("trip_id", "")
                if not stop_id or not trip_id:
                    continue
                route_id = trip_to_route.get(trip_id)
                if route_id:
                    if stop_id not in stop_to_routes:
                        stop_to_routes[stop_id] = set()
                    stop_to_routes[stop_id].add(route_id)

    return stop_to_routes


# ---------------------------------------------------------------------------
# 4. Annotate stations with route connectivity
# ---------------------------------------------------------------------------


def annotate_station_connectivity(
    stations: list[Station],
    gtfs_stop_id_map: dict[str, list[GtfsStop]],
    route_connectivity: dict[str, set[str]],
) -> None:
    """Set connected_route_ids on bus stop stations based on GTFS route data.

    Train stations already have {TRAIN_ROUTE_SENTINEL} set during filtering.
    """
    for station in stations:
        if station.transport_type == "train":
            # Already set during filter_and_annotate_bus_stops
            if not station.connected_route_ids:
                station.connected_route_ids = {TRAIN_ROUTE_SENTINEL}
            continue

        matched_gtfs_stops = gtfs_stop_id_map.get(station.code, [])
        route_ids: set[str] = set()
        for gtfs_stop in matched_gtfs_stops:
            stop_routes = route_connectivity.get(gtfs_stop.stop_id, set())
            route_ids.update(stop_routes)

        station.connected_route_ids = route_ids
        if route_ids:
            logger.debug(
                "Bus stop %s connected to %d routes",
                station.name,
                len(route_ids),
            )
        else:
            logger.debug("Bus stop %s has no route connectivity", station.name)


def are_stations_transport_connected(station_a: Station, station_b: Station) -> bool:
    """Check if two stations can be connected by the same transport mode.

    Both train stations → connected (train network).
    Both have overlapping bus route_ids → connected (same bus line).
    Mixed or no overlap → not connected.
    """
    routes_a = station_a.connected_route_ids
    routes_b = station_b.connected_route_ids

    if not routes_a or not routes_b:
        return False

    # Both train stations
    if TRAIN_ROUTE_SENTINEL in routes_a and TRAIN_ROUTE_SENTINEL in routes_b:
        return True

    # Both have bus routes — check for shared route_id (excluding train sentinel)
    bus_routes_a = routes_a - {TRAIN_ROUTE_SENTINEL}
    bus_routes_b = routes_b - {TRAIN_ROUTE_SENTINEL}
    return bool(bus_routes_a and bus_routes_b and bus_routes_a & bus_routes_b)


# ---------------------------------------------------------------------------
# Caching helpers
# ---------------------------------------------------------------------------


def _bbox_cache_key(south: float, west: float, north: float, east: float) -> str:
    raw = f"gtfs-stops:{south:.4f},{west:.4f},{north:.4f},{east:.4f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _read_stops_cache(cache_key: str) -> list[GtfsStop] | None:
    path = _stops_cache_path(cache_key)
    if not path.exists():
        return None

    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > GTFS_CACHE_TTL_SECONDS:
        logger.info("GTFS cache expired for %s (%.0fs old)", path.name, age_seconds)
        return None

    logger.info("Using cached GTFS response %s (%.0fs old)", path.name, age_seconds)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        GtfsStop(
            latitude=entry["lat"],
            longitude=entry["lon"],
            stop_id=entry["stop_id"],
            resource_id=entry["resource_id"],
        )
        for entry in data
    ]


def _write_stops_cache(cache_key: str, stops: list[GtfsStop]) -> None:
    path = _stops_cache_path(cache_key)
    data = [
        {
            "lat": stop.latitude,
            "lon": stop.longitude,
            "stop_id": stop.stop_id,
            "resource_id": stop.resource_id,
        }
        for stop in stops
    ]
    path.write_text(json.dumps(data), encoding="utf-8")
    logger.info("Cached GTFS stops to %s", path.name)


def _stops_cache_path(cache_key: str) -> Path:
    cache_directory = Path(GTFS_CACHE_DIRECTORY).expanduser()
    cache_directory.mkdir(parents=True, exist_ok=True)
    return cache_directory / f"{cache_key}.json"


def _generic_cache_path(name: str) -> Path:
    cache_directory = Path(GTFS_FEEDS_CACHE_DIRECTORY).expanduser()
    cache_directory.mkdir(parents=True, exist_ok=True)
    return cache_directory / f"{name}.json"


def _read_generic_cache(path: Path) -> dict | None:  # type: ignore[type-arg]
    if not path.exists():
        return None
    age_seconds = time.time() - path.stat().st_mtime
    if age_seconds > GTFS_CACHE_TTL_SECONDS:
        return None
    logger.info("Using cached %s (%.0fs old)", path.name, age_seconds)
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _write_generic_cache(path: Path, data: dict) -> None:  # type: ignore[type-arg]
    path.write_text(json.dumps(data), encoding="utf-8")
