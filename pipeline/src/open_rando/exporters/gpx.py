from __future__ import annotations

from pathlib import Path

import gpxpy
import gpxpy.gpx
from shapely.geometry import LineString, MultiLineString

from open_rando.models import PointOfInterest


def export_route_gpx(
    trail: LineString | MultiLineString,
    name: str,
    description: str,
    pois: list[PointOfInterest],
    output_path: str,
    elevations: list[float | None] | None = None,
) -> None:
    """Export a full route trail as a GPX file with POI waypoints."""
    gpx = gpxpy.gpx.GPX()
    gpx.name = name
    gpx.description = description
    gpx.creator = "open-rando"

    # Add POI waypoints (train stations only — keeps GPX useful for navigation)
    for poi in pois:
        if poi.poi_type == "train_station":
            waypoint = gpxpy.gpx.GPXWaypoint(
                latitude=poi.lat,
                longitude=poi.lon,
                name=poi.name,
            )
            gpx.waypoints.append(waypoint)

    # Add trail as track
    track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(track)

    segments = list(trail.geoms) if isinstance(trail, MultiLineString) else [trail]

    elevation_index = 0
    for segment in segments:
        track_segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(track_segment)

        for longitude, latitude in segment.coords:
            elevation = None
            if elevations is not None and elevation_index < len(elevations):
                elevation = elevations[elevation_index]
            elevation_index += 1

            track_point = gpxpy.gpx.GPXTrackPoint(
                latitude=latitude, longitude=longitude, elevation=elevation
            )
            track_segment.points.append(track_point)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gpx.to_xml(), encoding="utf-8")
