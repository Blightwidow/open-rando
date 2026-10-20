from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
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
from open_rando.models import RailService, ServiceWindow, Station

logger = logging.getLogger("open_rando")

REQUEST_TIMEOUT_SECONDS = 60
FEED_DOWNLOAD_TIMEOUT_SECONDS = 120
TRAIN_ROUTE_SENTINEL = "__train__"

DAY_TYPE_WEEKDAY = "weekday"
DAY_TYPE_SATURDAY = "saturday"
DAY_TYPE_SUNDAY = "sunday"
DAY_TYPES = (DAY_TYPE_WEEKDAY, DAY_TYPE_SATURDAY, DAY_TYPE_SUNDAY)

# GTFS route_type values that mean rail: 2 in the base spec, 100-117 in the
# extended set (long distance, regional, suburban railway...). Departures are
# only counted for these, so a city bus stop next to a station cannot inflate
# a station's train count.
RAIL_ROUTE_TYPES = frozenset({2, *range(100, 118)})

# How many occurrences of each kind of day are sampled. Timetables change with
# seasons and lines close for works, so a single sampled date would report "no
# service" for a station whose trains resume a fortnight later.
CANDIDATE_DATES_PER_DAY_TYPE = 4

# calendar.txt service day columns, Monday first (GTFS order).
CALENDAR_DAY_COLUMNS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# Approximate meters per degree at mid-latitudes (France ~46°N)
METERS_PER_DEGREE_LAT = 111_320
METERS_PER_DEGREE_LON_AT_46 = 77_400


@dataclass
class FeedData:
    """Everything the pipeline extracts from a set of GTFS feeds."""

    connectivity: dict[str, set[str]] = field(default_factory=dict)
    route_names: dict[str, str] = field(default_factory=dict)
    # stop_id -> day type -> departures on that kind of day
    departures: dict[str, dict[str, ServiceWindow]] = field(default_factory=dict)


@dataclass
class GtfsStop:
    latitude: float
    longitude: float
    stop_id: str
    resource_id: int


# ---------------------------------------------------------------------------
# 1. Fetch GTFS stops (enhanced with stop_id and resource_id)
# ---------------------------------------------------------------------------


# Max bbox dimension in degrees before chunking (~0.25° ≈ 28km).
# Dense urban areas (Paris) cause 422 errors at larger sizes.
GTFS_MAX_BBOX_DEGREES = 0.25


def fetch_gtfs_stops(
    south: float,
    west: float,
    north: float,
    east: float,
) -> tuple[list[GtfsStop], bool]:
    """Fetch GTFS-indexed stops from transport.data.gouv.fr.

    Splits into chunks and deduplicates by stop_id.
    Returns (list of GtfsStop, all_cached).
    """
    seen_stop_ids: set[str] = set()
    all_stops: list[GtfsStop] = []
    all_cached = True

    for chunk in _split_bbox(south, west, north, east, GTFS_MAX_BBOX_DEGREES):
        chunk_stops, cached = _fetch_gtfs_stops_single(*chunk)
        all_cached = all_cached and cached
        for stop in chunk_stops:
            if stop.stop_id not in seen_stop_ids:
                seen_stop_ids.add(stop.stop_id)
                all_stops.append(stop)

    logger.info("Found %d unique GTFS stops", len(all_stops))
    return all_stops, all_cached


def _split_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
    max_degrees: float,
) -> list[tuple[float, float, float, float]]:
    """Split a bbox into chunks no larger than max_degrees on each side."""
    width = east - west
    height = north - south
    lat_steps = max(1, math.ceil(height / max_degrees))
    lon_steps = max(1, math.ceil(width / max_degrees))
    lat_size = height / lat_steps
    lon_size = width / lon_steps

    chunks: list[tuple[float, float, float, float]] = []
    for lat_index in range(lat_steps):
        for lon_index in range(lon_steps):
            chunks.append(
                (
                    south + lat_index * lat_size,
                    west + lon_index * lon_size,
                    south + (lat_index + 1) * lat_size,
                    west + (lon_index + 1) * lon_size,
                )
            )
    return chunks


def _fetch_gtfs_stops_single(
    south: float,
    west: float,
    north: float,
    east: float,
) -> tuple[list[GtfsStop], bool]:
    """Fetch GTFS stops for a single bbox (no chunking)."""
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


def match_stations_to_gtfs_stops(
    stations: list[Station],
    gtfs_stops: list[GtfsStop],
    radius_meters: float = GTFS_MATCH_RADIUS_METERS,
) -> dict[str, list[GtfsStop]]:
    """Map station codes to the GTFS stops sitting within radius_meters."""
    matches: dict[str, list[GtfsStop]] = {}
    for station in stations:
        nearby = _find_nearby_gtfs_stops(station.lat, station.lon, gtfs_stops, radius_meters)
        if nearby:
            matches[station.code] = nearby
    return matches


def _find_nearby_gtfs_stops(
    latitude: float,
    longitude: float,
    gtfs_stops: list[GtfsStop],
    radius_meters: float = GTFS_MATCH_RADIUS_METERS,
) -> list[GtfsStop]:
    """Find all GTFS stops within radius_meters."""
    threshold_lat = radius_meters / METERS_PER_DEGREE_LAT
    threshold_lon = radius_meters / METERS_PER_DEGREE_LON_AT_46

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
        if distance_meters <= radius_meters:
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


def fetch_gtfs_feed_data(
    resource_ids: set[int],
    resource_url_map: dict[int, str],
    reference_date: date | None = None,
) -> FeedData:
    """Download GTFS feeds and extract connectivity, route names and departures.

    Only downloads feeds for the given resource_ids. Feeds are parsed once and
    cached, so route connectivity and departures share a single download.
    """
    reference = reference_date or date.today()
    combined = FeedData()

    for resource_id in resource_ids:
        url = resource_url_map.get(resource_id)
        if not url:
            logger.warning("No download URL for GTFS resource %d", resource_id)
            continue

        feed = _fetch_feed_data(resource_id, url, reference)

        for stop_id, route_ids in feed.connectivity.items():
            combined.connectivity.setdefault(stop_id, set()).update(route_ids)
        combined.route_names.update(feed.route_names)
        for stop_id, windows in feed.departures.items():
            merged = combined.departures.setdefault(stop_id, {})
            for day_type, window in windows.items():
                merged[day_type] = _merge_service_windows(merged.get(day_type), window)

    logger.info(
        "Built feed data for %d stops (%d with departures) from %d feeds",
        len(combined.connectivity),
        len(combined.departures),
        len(resource_ids),
    )
    return combined


def build_rail_service(
    matched_gtfs_stops: list[GtfsStop],
    departures: dict[str, dict[str, ServiceWindow]],
) -> RailService | None:
    """Merge the departures of every GTFS stop matched to one train station.

    A large station is often split into several GTFS stops (one per platform,
    one per operator), so windows are merged: earliest first departure, latest
    last departure, summed departure counts.
    """
    merged: dict[str, ServiceWindow | None] = {day_type: None for day_type in DAY_TYPES}

    for gtfs_stop in matched_gtfs_stops:
        for day_type, window in departures.get(gtfs_stop.stop_id, {}).items():
            if day_type not in merged:
                continue
            merged[day_type] = _merge_service_windows(merged[day_type], window)

    rail_service = RailService(
        weekday=merged[DAY_TYPE_WEEKDAY],
        saturday=merged[DAY_TYPE_SATURDAY],
        sunday=merged[DAY_TYPE_SUNDAY],
    )
    return rail_service if rail_service.has_service() else None


def _merge_service_windows(
    existing: ServiceWindow | None,
    addition: ServiceWindow,
) -> ServiceWindow:
    if existing is None:
        return ServiceWindow(
            first_departure_minutes=addition.first_departure_minutes,
            last_departure_minutes=addition.last_departure_minutes,
            departure_count=addition.departure_count,
            sample_date=addition.sample_date,
        )
    # Platforms and feeds can be sampled on different dates; keep the date of
    # whichever side carried more departures.
    busier = existing if existing.departure_count >= addition.departure_count else addition
    return ServiceWindow(
        first_departure_minutes=min(
            existing.first_departure_minutes, addition.first_departure_minutes
        ),
        last_departure_minutes=max(
            existing.last_departure_minutes, addition.last_departure_minutes
        ),
        departure_count=existing.departure_count + addition.departure_count,
        sample_date=busier.sample_date,
    )


def _fetch_feed_data(resource_id: int, url: str, reference_date: date) -> FeedData:
    """Download a single GTFS feed and extract stop→routes, names, departures.

    Cached per resource_id and per reference week: departures are counted on
    representative dates of that week, so a new week needs a fresh parse. A
    feed that cannot be parsed caches an empty result; a feed that cannot be
    downloaded does not, since that failure is usually transient.
    """
    week_start = reference_date - timedelta(days=reference_date.weekday())
    cache_path = _generic_cache_path(f"feed_data_v4_{resource_id}_{week_start:%Y-%m-%d}")
    cached = _read_generic_cache(cache_path)
    if cached is not None:
        return _feed_data_from_cache(cached)

    logger.info("Downloading GTFS feed for resource %d", resource_id)

    try:
        response = requests.get(url, timeout=FEED_DOWNLOAD_TIMEOUT_SECONDS, allow_redirects=True)
        response.raise_for_status()
    except (requests.RequestException, requests.Timeout) as error:
        logger.warning("Failed to download GTFS feed %d: %s", resource_id, error)
        return FeedData()

    try:
        feed = parse_gtfs_zip(response.content, reference_date)
    except (zipfile.BadZipFile, KeyError, csv.Error) as error:
        # A feed that is not GTFS (NeTEx behind a GTFS label, nested archive,
        # missing table) fails the same way on every run, so the empty result
        # is cached: re-downloading megabytes weekly to fail again is waste.
        logger.warning(
            "Failed to parse GTFS feed %d: %s (caching empty result)", resource_id, error
        )
        empty = FeedData()
        _write_generic_cache(cache_path, _feed_data_to_cache(empty))
        return empty

    _write_generic_cache(cache_path, _feed_data_to_cache(feed))

    logger.info(
        "Parsed GTFS feed %d: %d stops, %d route names, %d stops with departures",
        resource_id,
        len(feed.connectivity),
        len(feed.route_names),
        len(feed.departures),
    )
    return feed


def _feed_data_to_cache(feed: FeedData) -> dict[str, object]:
    return {
        "connectivity": {
            stop_id: sorted(route_ids) for stop_id, route_ids in feed.connectivity.items()
        },
        "route_names": feed.route_names,
        "departures": {
            stop_id: {day_type: window.to_dict() for day_type, window in windows.items()}
            for stop_id, windows in feed.departures.items()
        },
    }


def _feed_data_from_cache(cached: dict) -> FeedData:  # type: ignore[type-arg]
    return FeedData(
        connectivity={
            stop_id: set(route_ids) for stop_id, route_ids in cached.get("connectivity", {}).items()
        },
        route_names=cached.get("route_names", {}),
        departures={
            stop_id: {
                day_type: ServiceWindow.from_dict(window) for day_type, window in windows.items()
            }
            for stop_id, windows in cached.get("departures", {}).items()
        },
    )


def parse_gtfs_zip(content: bytes, reference_date: date) -> FeedData:
    """Parse a GTFS zip in memory.

    Reads routes.txt, the service calendars, trips.txt and stop_times.txt.
    Departures are counted for rail routes only, on real calendar dates: each
    kind of day (weekday, Saturday, Sunday) is sampled on several upcoming
    dates and the busiest one is kept, so the numbers read as "trains on a
    Saturday" instead of a sum over every timetable variant.
    """
    candidate_dates = _candidate_dates(reference_date)
    all_candidates = [day for days in candidate_dates.values() for day in days]

    with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
        route_names, rail_route_ids = _parse_routes(zip_file)
        service_dates = _parse_service_dates(zip_file, all_candidates)

        # Step 1: trips.txt gives trip → route and trip → service. Only rail
        # trips need their running dates resolved.
        trip_to_route: dict[str, str] = {}
        rail_trip_dates: dict[str, frozenset[date]] = {}
        with zip_file.open("trips.txt") as trips_file:
            reader = csv.DictReader(io.TextIOWrapper(trips_file, encoding="utf-8-sig"))
            for row in reader:
                trip_id = row.get("trip_id", "")
                route_id = row.get("route_id", "")
                if not trip_id or not route_id:
                    continue
                trip_to_route[trip_id] = route_id
                if route_id not in rail_route_ids:
                    continue
                running_dates = service_dates.get(row.get("service_id", ""))
                if running_dates:
                    rail_trip_dates[trip_id] = running_dates

        # Step 2: Walk stop_times.txt once for connectivity and departures.
        # Aggregates stay as [first, last, count] lists: stop_times.txt holds
        # millions of rows in national feeds, so no object is built per row.
        stop_to_routes: dict[str, set[str]] = {}
        raw_departures: dict[str, dict[date, list[int]]] = {}
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

                running_dates = rail_trip_dates.get(trip_id)
                if not running_dates:
                    continue
                departure_minutes = _parse_departure_minutes(row.get("departure_time", ""))
                if departure_minutes is None:
                    continue

                per_date = raw_departures.setdefault(stop_id, {})
                for running_date in running_dates:
                    aggregate = per_date.get(running_date)
                    if aggregate is None:
                        per_date[running_date] = [departure_minutes, departure_minutes, 1]
                        continue
                    if departure_minutes < aggregate[0]:
                        aggregate[0] = departure_minutes
                    if departure_minutes > aggregate[1]:
                        aggregate[1] = departure_minutes
                    aggregate[2] += 1

    departures = {
        stop_id: _pick_representative_windows(per_date, candidate_dates)
        for stop_id, per_date in raw_departures.items()
    }
    return FeedData(
        connectivity=stop_to_routes,
        route_names=route_names,
        departures={stop_id: windows for stop_id, windows in departures.items() if windows},
    )


def _pick_representative_windows(
    per_date: dict[date, list[int]],
    candidate_dates: dict[str, list[date]],
) -> dict[str, ServiceWindow]:
    """Keep the busiest sampled date for each kind of day."""
    windows: dict[str, ServiceWindow] = {}
    for day_type, days in candidate_dates.items():
        sampled = [(day, per_date[day]) for day in days if day in per_date]
        if not sampled:
            continue
        # Most departures wins; the earliest date breaks ties.
        best_day, aggregate = max(sampled, key=lambda entry: (entry[1][2], -entry[0].toordinal()))
        windows[day_type] = ServiceWindow(
            first_departure_minutes=aggregate[0],
            last_departure_minutes=aggregate[1],
            departure_count=aggregate[2],
            sample_date=best_day.isoformat(),
        )
    return windows


def _parse_routes(zip_file: zipfile.ZipFile) -> tuple[dict[str, str], set[str]]:
    """Read routes.txt for display names and for which routes are rail."""
    route_names: dict[str, str] = {}
    rail_route_ids: set[str] = set()

    try:
        routes_file = zip_file.open("routes.txt")
    except KeyError:
        logger.debug("No routes.txt in GTFS feed, skipping route names and departures")
        return route_names, rail_route_ids

    with routes_file:
        reader = csv.DictReader(io.TextIOWrapper(routes_file, encoding="utf-8-sig"))
        for row in reader:
            route_id = row.get("route_id", "")
            if not route_id:
                continue
            short_name = row.get("route_short_name", "").strip()
            long_name = row.get("route_long_name", "").strip()
            if short_name:
                route_names[route_id] = short_name
            elif long_name:
                route_names[route_id] = long_name
            if _is_rail_route_type(row.get("route_type", "")):
                rail_route_ids.add(route_id)

    return route_names, rail_route_ids


def _is_rail_route_type(raw: str) -> bool:
    try:
        return int(raw.strip()) in RAIL_ROUTE_TYPES
    except ValueError:
        return False


def _candidate_dates(reference_date: date) -> dict[str, list[date]]:
    """Dates sampled for each kind of day, starting from the reference week.

    A Wednesday stands in for a weekday because Mondays and Fridays carry the
    most timetable exceptions. Anchoring on the reference week (rather than on
    the exact day) keeps the parsed feed cache stable for a whole week.
    """
    week_start = reference_date - timedelta(days=reference_date.weekday())
    offsets = {DAY_TYPE_WEEKDAY: 2, DAY_TYPE_SATURDAY: 5, DAY_TYPE_SUNDAY: 6}
    return {
        day_type: [
            week_start + timedelta(days=offset + 7 * week)
            for week in range(CANDIDATE_DATES_PER_DAY_TYPE)
        ]
        for day_type, offset in offsets.items()
    }


def _parse_service_dates(
    zip_file: zipfile.ZipFile,
    candidate_dates: list[date],
) -> dict[str, frozenset[date]]:
    """Map service_id → which of the candidate dates the service runs on.

    calendar.txt gives the weekly pattern and the validity range;
    calendar_dates.txt adds one-off dates (feeds built only from exceptions
    have no calendar.txt) and removes cancelled ones.
    """
    active: dict[str, set[date]] = {}
    names = set(zip_file.namelist())

    if "calendar.txt" in names:
        with zip_file.open("calendar.txt") as calendar_file:
            reader = csv.DictReader(io.TextIOWrapper(calendar_file, encoding="utf-8-sig"))
            for row in reader:
                service_id = row.get("service_id", "")
                if not service_id:
                    continue
                start_date = _parse_gtfs_date(row.get("start_date", ""))
                end_date = _parse_gtfs_date(row.get("end_date", ""))
                for day in candidate_dates:
                    if start_date is not None and day < start_date:
                        continue
                    if end_date is not None and day > end_date:
                        continue
                    if row.get(CALENDAR_DAY_COLUMNS[day.weekday()], "").strip() != "1":
                        continue
                    active.setdefault(service_id, set()).add(day)

    if "calendar_dates.txt" in names:
        sampled = set(candidate_dates)
        with zip_file.open("calendar_dates.txt") as calendar_dates_file:
            reader = csv.DictReader(io.TextIOWrapper(calendar_dates_file, encoding="utf-8-sig"))
            for row in reader:
                service_id = row.get("service_id", "")
                exception_date = _parse_gtfs_date(row.get("date", ""))
                if not service_id or exception_date not in sampled:
                    continue
                exception_type = row.get("exception_type", "").strip()
                if exception_type == "1":
                    active.setdefault(service_id, set()).add(exception_date)
                elif exception_type == "2":
                    active.get(service_id, set()).discard(exception_date)

    return {service_id: frozenset(days) for service_id, days in active.items() if days}


def _day_type_for_weekday(weekday_index: int) -> str:
    """Map a Monday-first weekday index to a day type."""
    if weekday_index == 5:
        return DAY_TYPE_SATURDAY
    if weekday_index == 6:
        return DAY_TYPE_SUNDAY
    return DAY_TYPE_WEEKDAY


def _parse_gtfs_date(raw: str) -> date | None:
    """Parse a GTFS YYYYMMDD date."""
    cleaned = raw.strip()
    if len(cleaned) != 8 or not cleaned.isdigit():
        return None
    try:
        return date(int(cleaned[0:4]), int(cleaned[4:6]), int(cleaned[6:8]))
    except ValueError:
        return None


def _parse_departure_minutes(raw: str) -> int | None:
    """Parse a GTFS HH:MM:SS time into minutes after midnight.

    Hours can exceed 23 for trips running past midnight; those values are kept
    as-is so a 00:35 last train stays greater than the 23:50 one before it.
    """
    parts = raw.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    if hours < 0 or not 0 <= minutes <= 59:
        return None
    return hours * 60 + minutes


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


def resolve_transit_line_names(
    connected_route_ids: set[str],
    route_names: dict[str, str],
) -> list[str]:
    """Resolve route IDs to human-readable display names, sorted alphabetically."""
    names: list[str] = []
    for route_id in connected_route_ids:
        if route_id == TRAIN_ROUTE_SENTINEL:
            continue
        display_name = route_names.get(route_id, route_id)
        names.append(display_name)
    names.sort()
    return names


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
