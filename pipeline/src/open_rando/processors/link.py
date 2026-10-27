"""Join POIs to a track: which POIs are reachable from it, and where along it.

Pure geometry over already-computed POIs. The same rules apply to a curated
track and (in the companion app) to an imported GPX.
"""

from __future__ import annotations

import logging

from shapely.geometry import LineString, MultiLineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from shapely.prepared import prep

from open_rando.config import MAX_BUS_STOP_DISTANCE_METERS, MAX_STATION_DISTANCE_METERS
from open_rando.fetchers.pois import POI_ACCOMMODATION_RADIUS_METERS
from open_rando.models import PoiLink, PointOfInterest, Station
from open_rando.processors.match import (
    MatchedStation,
    degrees_to_meters,
    match_stations_to_trail,
    refine_junctions_by_walking_distance,
)
from open_rando.processors.slice import compute_segments_distance_km, extract_substring_segments

logger = logging.getLogger("open_rando")

# Wider than the largest link distance (5 km is ~0.065 deg of longitude in France),
# so the pre-filter never drops a POI the precise match would keep.
CANDIDATE_BUFFER_DEGREES = 0.07
# Vertices closer than ~100 m are irrelevant to a 0.07 deg buffer.
CANDIDATE_SIMPLIFY_TOLERANCE_DEGREES = 0.001


def candidate_zone(trail: LineString | MultiLineString) -> BaseGeometry:
    return trail.simplify(CANDIDATE_SIMPLIFY_TOLERANCE_DEGREES).buffer(CANDIDATE_BUFFER_DEGREES)


def link_pois_to_trail(
    trail: LineString | MultiLineString,
    pois: list[PointOfInterest],
    refine_junctions: bool = True,
) -> list[PoiLink]:
    """Links for every POI near the trail, ordered along it.

    Train stations and bus stops go through station matching (nearest point,
    duplicate and never-closest filtering). Train junctions are then refined
    by walking distance (OSRM) unless refine_junctions is off. Accommodation
    only needs to lie within its radius.
    """
    zone = prep(candidate_zone(trail))
    nearby = [poi for poi in pois if zone.contains(Point(poi.lon, poi.lat))]
    logger.info("  %d of %d POIs inside the candidate zone", len(nearby), len(pois))

    train_stations = _stations_of_kind(nearby, "train_station", "train")
    matched_trains = match_stations_to_trail(train_stations, trail, MAX_STATION_DISTANCE_METERS)
    if refine_junctions:
        matched_trains = refine_junctions_by_walking_distance(matched_trains, trail)

    bus_stops = _stations_of_kind(nearby, "bus_stop", "bus")
    matched_buses = match_stations_to_trail(bus_stops, trail, MAX_BUS_STOP_DISTANCE_METERS)

    links = [_train_link(matched, trail) for matched in matched_trains]
    links.extend(_bus_link(matched) for matched in matched_buses)
    links.extend(_accommodation_links(nearby, trail))
    return sorted(links, key=_link_order)


def _stations_of_kind(pois: list[PointOfInterest], kind: str, transport_type: str) -> list[Station]:
    return [
        Station(
            name=poi.name,
            code=poi.osm_id,
            lat=poi.lat,
            lon=poi.lon,
            transport_type=transport_type,
            osm_id=poi.osm_id,
        )
        for poi in pois
        if poi.poi_type == kind
    ]


def _train_link(matched: MatchedStation, trail: LineString | MultiLineString) -> PoiLink:
    station, fraction, junction = matched
    # The fraction comes from Shapely's Euclidean project() in degree space, while
    # elevation profiles use haversine distances: measure the actual substring.
    pieces_to_station = extract_substring_segments(trail, 0.0, fraction)
    return PoiLink(
        poi_id=station.osm_id,
        kind="train_station",
        distance_to_trail_meters=station.distance_to_trail_meters,
        distance_km=round(compute_segments_distance_km(pieces_to_station), 2),
        junction=junction,
    )


def _bus_link(matched: MatchedStation) -> PoiLink:
    station, _fraction, junction = matched
    return PoiLink(
        poi_id=station.osm_id,
        kind="bus_stop",
        distance_to_trail_meters=station.distance_to_trail_meters,
        junction=junction,
    )


def _accommodation_links(
    pois: list[PointOfInterest],
    trail: LineString | MultiLineString,
) -> list[PoiLink]:
    links: list[PoiLink] = []
    for poi in pois:
        if poi.poi_type not in ("hotel", "camping"):
            continue
        point = Point(poi.lon, poi.lat)
        nearest_on_trail = nearest_points(trail, point)[0]
        distance_meters = degrees_to_meters(point.distance(nearest_on_trail), poi.lat)
        if distance_meters <= POI_ACCOMMODATION_RADIUS_METERS:
            links.append(
                PoiLink(
                    poi_id=poi.osm_id,
                    kind=poi.poi_type,
                    distance_to_trail_meters=round(distance_meters, 1),
                    junction=(nearest_on_trail.x, nearest_on_trail.y),
                )
            )
    return links


def _link_order(link: PoiLink) -> tuple[bool, float, float, str]:
    """Along the trail first; POIs with no position (not train stations) last."""
    return (
        link.distance_km is None,
        link.distance_km or 0.0,
        link.distance_to_trail_meters,
        link.poi_id,
    )


def summarize_links(links: list[PoiLink], pois: list[PointOfInterest]) -> dict[str, int]:
    """How many linked POIs of each kind, and how many stations have departures."""
    served_station_ids = {
        poi.osm_id for poi in pois if poi.poi_type == "train_station" and poi.rail_service
    }
    counts = {"train_station": 0, "bus_stop": 0, "hotel": 0, "camping": 0}
    for link in links:
        counts[link.kind] += 1
    counts["train_station_with_rail_service"] = sum(
        1 for link in links if link.poi_id in served_station_ids
    )
    return counts
