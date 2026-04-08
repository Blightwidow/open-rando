from __future__ import annotations

from pathlib import Path

import gpxpy
import gpxpy.gpx
from shapely.geometry import LineString


def export_gpx(
    segments: list[LineString],
    name: str,
    description: str,
    output_path: str,
    segment_elevations: list[list[float | None]] | None = None,
) -> None:
    """Export segments as a GPX file. Each segment becomes a track segment within one track."""
    gpx = gpxpy.gpx.GPX()
    gpx.name = name
    gpx.description = description
    gpx.creator = "open-rando"

    track = gpxpy.gpx.GPXTrack(name=name)
    gpx.tracks.append(track)

    for segment_index, segment in enumerate(segments):
        track_segment = gpxpy.gpx.GPXTrackSegment()
        track.segments.append(track_segment)

        elevations = segment_elevations[segment_index] if segment_elevations is not None else None

        for point_index, (longitude, latitude) in enumerate(segment.coords):
            elevation = (
                elevations[point_index]
                if elevations is not None and point_index < len(elevations)
                else None
            )
            track_point = gpxpy.gpx.GPXTrackPoint(
                latitude=latitude, longitude=longitude, elevation=elevation
            )
            track_segment.points.append(track_point)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(gpx.to_xml(), encoding="utf-8")
