from __future__ import annotations

import logging
import time

from open_rando.config import (
    ACCOMMODATION_SEARCH_RADIUS_METERS,
    OVERPASS_TIMEOUT_SECONDS,
)
from open_rando.fetchers.overpass import query_overpass
from open_rando.models import Accommodation, Station
from open_rando.processors.slice import haversine_distance

logger = logging.getLogger("open_rando")

HOTEL_TAGS = ("hotel", "guest_house", "hostel")
CAMPING_TAGS = ("camp_site",)
BATCH_SIZE = 15
DELAY_BETWEEN_BATCHES_SECONDS = 5


def fetch_accommodation(stations: list[Station]) -> None:
    """Fetch accommodation near each station and mutate their accommodation field."""
    if not stations:
        return

    total_batches = (len(stations) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_index, batch_start in enumerate(range(0, len(stations), BATCH_SIZE)):
        if batch_index > 0:
            logger.info(
                "Waiting %ds before next batch (%d/%d)...",
                DELAY_BETWEEN_BATCHES_SECONDS,
                batch_index + 1,
                total_batches,
            )
            time.sleep(DELAY_BETWEEN_BATCHES_SECONDS)
        batch = stations[batch_start : batch_start + BATCH_SIZE]
        _fetch_accommodation_batch(batch)

    stations_with_hotel = sum(1 for station in stations if station.accommodation.has_hotel)
    stations_with_camping = sum(1 for station in stations if station.accommodation.has_camping)
    logger.info(
        "Accommodation: %d/%d stations have hotel, %d/%d have camping",
        stations_with_hotel,
        len(stations),
        stations_with_camping,
        len(stations),
    )


def _fetch_accommodation_batch(stations: list[Station]) -> None:
    """Fetch accommodation for a batch of stations in a single Overpass query."""
    around_clauses: list[str] = []
    for station in stations:
        around = f"around:{ACCOMMODATION_SEARCH_RADIUS_METERS},{station.lat},{station.lon}"
        around_clauses.append(f'  node["tourism"~"hotel|guest_house|hostel|camp_site"]({around});')
        around_clauses.append(f'  way["tourism"~"hotel|guest_house|hostel|camp_site"]({around});')

    union_body = "\n".join(around_clauses)
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
{union_body}
);
out center;
"""
    data = query_overpass(query)

    for element in data.get("elements", []):
        tags = element.get("tags", {})
        tourism_tag = tags.get("tourism", "")

        if element.get("type") == "way":
            center = element.get("center", {})
            element_lat = center.get("lat")
            element_lon = center.get("lon")
        else:
            element_lat = element.get("lat")
            element_lon = element.get("lon")

        if element_lat is None or element_lon is None:
            continue

        for station in stations:
            distance = haversine_distance(station.lat, station.lon, element_lat, element_lon)
            if distance > ACCOMMODATION_SEARCH_RADIUS_METERS:
                continue

            if station.accommodation is None:
                station.accommodation = Accommodation()

            if tourism_tag in HOTEL_TAGS:
                station.accommodation.has_hotel = True
            elif tourism_tag in CAMPING_TAGS:
                station.accommodation.has_camping = True
