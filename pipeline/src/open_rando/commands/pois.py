"""`pois` subcommand — build the France-wide POI grid.

POIs (train stations, bus stops, hotels, campings) are computed per grid
square, independent of any track, so the same files serve curated routes and
custom GPX imports. Linking POIs to a track happens in a later stage.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from open_rando.config import POIS_DIRECTORY, TRAIN_GTFS_MATCH_RADIUS_METERS
from open_rando.exporters.pois import export_poi_index, export_poi_square, read_poi_index_counts
from open_rando.fetchers.gtfs import (
    FeedData,
    GtfsStop,
    build_rail_service,
    fetch_gtfs_feed_data,
    fetch_resource_url_map,
    match_stations_to_gtfs_stops,
    resolve_transit_line_names,
)
from open_rando.fetchers.gtfs_stops_index import GtfsStopsIndex
from open_rando.fetchers.osm_extract import (
    LAYER_ACCOMMODATION,
    LAYER_STATIONS,
    OsmExtractIndex,
    open_layer,
)
from open_rando.fetchers.pois import _parse_accommodation_elements
from open_rando.fetchers.sncf import build_sncf_code_set, build_sncf_url, fetch_sncf_stations
from open_rando.fetchers.stations import _parse_station_elements, filter_stations_by_sncf
from open_rando.models import PointOfInterest, Station
from open_rando.poi_grid import PoiGrid, Square, square_file_name

logger = logging.getLogger("open_rando")

# A train station sprawls up to TRAIN_GTFS_MATCH_RADIUS_METERS from its OSM node.
GTFS_MARGIN_DEGREES = 0.01

FeedLoader = Callable[[set[int]], FeedData]


def add_pois_subparser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "pois",
        help="Build the France-wide POI grid (stations, bus stops, hotels, campings).",
    )
    parser.add_argument(
        "--square",
        action="append",
        metavar="COL_ROW",
        help="Build only this grid square (repeatable), for example '8_3'.",
    )
    parser.add_argument(
        "--skip-gtfs",
        action="store_true",
        help="Skip GTFS enrichment: train stations get no departures, bus stops "
        "keep only the lines tagged in OSM.",
    )
    parser.set_defaults(func=run_pois)


def parse_square(raw: str) -> Square:
    column_text, _, row_text = raw.partition("_")
    return int(column_text), int(row_text)


def build_square_pois(
    stations: list[Station],
    accommodation: list[PointOfInterest],
    sncf_codes: set[str],
    gtfs_stops: list[GtfsStop],
    load_feed_data: FeedLoader,
) -> list[PointOfInterest]:
    """Turn the raw OSM features of one square into enriched POIs."""
    sncf_stations = filter_stations_by_sncf(stations, sncf_codes) if sncf_codes else stations

    # GTFS matches are keyed by station.code, a `ref` shared by many stops in
    # one grid square, so match on copies keyed by the unique OSM id instead.
    keyed_stations = [replace(station, code=station.osm_id) for station in sncf_stations]
    train_stations = [s for s in keyed_stations if s.transport_type == "train"]
    bus_stops = [s for s in keyed_stations if s.transport_type == "bus"]
    train_gtfs_stop_map = match_stations_to_gtfs_stops(
        train_stations, gtfs_stops, TRAIN_GTFS_MATCH_RADIUS_METERS
    )
    bus_gtfs_stop_map = match_stations_to_gtfs_stops(bus_stops, gtfs_stops)

    resource_ids = {
        gtfs_stop.resource_id
        for matches in (*bus_gtfs_stop_map.values(), *train_gtfs_stop_map.values())
        for gtfs_stop in matches
    }
    feed_data = load_feed_data(resource_ids) if resource_ids else FeedData()

    pois: list[PointOfInterest] = []
    for station in sncf_stations:
        if station.transport_type == "train":
            pois.append(
                PointOfInterest(
                    name=station.name,
                    lat=station.lat,
                    lon=station.lon,
                    poi_type="train_station",
                    url=build_sncf_url(station.name),
                    rail_service=build_rail_service(
                        train_gtfs_stop_map.get(station.osm_id, []),
                        feed_data.departures,
                    ),
                    osm_id=station.osm_id,
                )
            )
            continue

        # Bus stops without a GTFS match stay: OSM-only stops are still stops.
        route_ids: set[str] = set()
        for gtfs_stop in bus_gtfs_stop_map.get(station.osm_id, []):
            route_ids.update(feed_data.connectivity.get(gtfs_stop.stop_id, set()))
        lines = (
            resolve_transit_line_names(route_ids, feed_data.route_names)
            if route_ids
            else station.transit_lines
        )
        pois.append(
            PointOfInterest(
                name=station.name,
                lat=station.lat,
                lon=station.lon,
                poi_type="bus_stop",
                transit_lines=lines,
                osm_id=station.osm_id,
            )
        )

    pois.extend(accommodation)
    return pois


def keep_in_square(
    pois: list[PointOfInterest],
    grid: PoiGrid,
    square: Square,
) -> list[PointOfInterest]:
    """Drop POIs sitting on a shared edge but owned by the neighbouring square."""
    return [poi for poi in pois if grid.square_for_point(poi.lat, poi.lon) == square]


def run_pois(arguments: argparse.Namespace) -> None:
    grid = PoiGrid()
    squares = (
        [parse_square(raw) for raw in arguments.square]
        if arguments.square
        else [(column, row) for row in range(grid.rows) for column in range(grid.columns)]
    )
    output_directory = str(Path(POIS_DIRECTORY).expanduser())

    sncf_codes = build_sncf_code_set(fetch_sncf_stations())
    resource_url_map: dict[int, str] = {}
    stops_index: GtfsStopsIndex | None = None
    if not arguments.skip_gtfs:
        stops_index = GtfsStopsIndex.open_for_reading()
        if stops_index is None:
            raise SystemExit(
                "No GTFS stop index. Run `python -m open_rando gtfs` first, or pass --skip-gtfs."
            )
        resource_url_map = fetch_resource_url_map()

    def load_feed_data(resource_ids: set[int]) -> FeedData:
        return fetch_gtfs_feed_data(resource_ids, resource_url_map)

    counts_by_square = read_poi_index_counts(output_directory)

    stations_index = open_layer(LAYER_STATIONS)
    accommodation_index = open_layer(LAYER_ACCOMMODATION)
    if stations_index is None or accommodation_index is None:
        for opened in (stations_index, accommodation_index):
            if opened is not None:
                opened.close()
        raise SystemExit(
            "Local OSM extract index is missing the stations or accommodation layer. "
            "Run `python -m open_rando osm-index --status` to see what it holds, "
            "or `python -m open_rando osm-index` to build it: the POI grid is read from it."
        )

    try:
        for square in squares:
            west, south, east, north = grid.square_bounding_box(square)
            bounds = (south, west, north, east)
            station_elements = _elements_in_square(stations_index, LAYER_STATIONS, bounds)
            accommodation_elements = _elements_in_square(
                accommodation_index, LAYER_ACCOMMODATION, bounds
            )

            stations = [
                station
                for station in _parse_station_elements(station_elements)
                if grid.square_for_point(station.lat, station.lon) == square
            ]
            accommodation = keep_in_square(
                _parse_accommodation_elements(accommodation_elements), grid, square
            )

            gtfs_stops: list[GtfsStop] = []
            if stops_index is not None and stations:
                gtfs_stops = stops_index.stops_in_bounding_box(
                    south - GTFS_MARGIN_DEGREES,
                    west - GTFS_MARGIN_DEGREES,
                    north + GTFS_MARGIN_DEGREES,
                    east + GTFS_MARGIN_DEGREES,
                )

            pois = build_square_pois(
                stations, accommodation, sncf_codes, gtfs_stops, load_feed_data
            )
            counts_by_square[square] = len(pois)
            if pois:
                export_poi_square(square, pois, output_directory)
            else:
                (Path(output_directory) / square_file_name(square)).unlink(missing_ok=True)
            logger.info("Square %d_%d: %d POIs", square[0], square[1], len(pois))
    finally:
        stations_index.close()
        accommodation_index.close()
        if stops_index is not None:
            stops_index.close()

    export_poi_index(grid, counts_by_square, output_directory)
    logger.info("POI grid written to %s", output_directory)


def _elements_in_square(
    index: OsmExtractIndex,
    layer: str,
    bounds: tuple[float, float, float, float],
) -> dict[str, Any]:
    """OSM points of a layer inside a square, restricted to what the extract covers.

    The grid reaches past the France extract (south of 41.24 N, north of 51.43 N):
    nothing exists there in the extract, so those parts are empty, not an error.
    """
    clipped = index.clip_to_coverage(layer, *bounds)
    if clipped is None:
        return {"elements": []}
    return index.point_elements(layer, *clipped)
