from __future__ import annotations

import json
from pathlib import Path

from open_rando.models import Track

TRACK_METADATA_FILE_NAME = "track.json"
TRAIL_GEOJSON_FILE_NAME = "trail.geojson"
TRAIL_GPX_FILE_NAME = "trail.gpx"
ELEVATION_FILE_NAME = "elevation.json"


def export_track_metadata(track: Track, track_directory: Path) -> None:
    """Write the per-track metadata file the catalog stage reads."""
    track_directory.mkdir(parents=True, exist_ok=True)
    (track_directory / TRACK_METADATA_FILE_NAME).write_text(
        json.dumps(track.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_track_metadata(track_directory: Path) -> Track:
    raw = json.loads((track_directory / TRACK_METADATA_FILE_NAME).read_text(encoding="utf-8"))
    return Track.from_dict(raw)
