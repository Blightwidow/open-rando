"""A synthetic one-route dataset, built by running the real stages offline.

Each stage runs in its own process with OPEN_RANDO_* pointing at a temporary
data and cache directory, so every stage reads exactly the files the previous
one wrote. Network sources are replaced by seeded caches: SNCF stations, one
SRTM tile, and the OSM extract written with pyosmium. GTFS and OSRM are left
out (`pois --skip-gtfs`, `link --skip-walking-refinement`): both need
national-scale downloads or a running router.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from array import array
from pathlib import Path

from open_rando.commands.osm_index import EXTRACT_FILENAMES
from open_rando.fetchers.osm_extract import (
    LAYER_ACCOMMODATION,
    LAYER_FOREST,
    LAYER_LANDMARKS,
    LAYER_RESUPPLY,
    LAYER_STATIONS,
    LAYER_TRAILS,
)
from open_rando.fetchers.sncf import CACHE_FILENAME as SNCF_CACHE_FILENAME
from open_rando.fetchers.srtm import SRTM3_SAMPLES
from tests.osm_fixtures import write_pbf

PIPELINE_DIRECTORY = Path(__file__).resolve().parents[1]
ROUTE_REF = "GR 9999"
RELATION_ID = 900

# A ~14 km trail south-east of Paris, with a station near each end.
TRAIL_COORDINATES = [(2.50, 48.50), (2.55, 48.55), (2.60, 48.60)]


def write_extracts(directory: Path) -> None:
    directory.mkdir(parents=True)
    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_STATIONS],
        nodes=[
            {
                "id": 1,
                "location": (2.501, 48.501),
                "tags": {"railway": "station", "name": "Gare Sud", "ref:SNCF": "AAA"},
            },
            {
                "id": 2,
                "location": (2.599, 48.601),
                "tags": {"railway": "station", "name": "Gare Nord", "ref:SNCF": "BBB"},
            },
            {
                "id": 3,
                "location": (2.551, 48.551),
                "tags": {"highway": "bus_stop", "name": "Mairie"},
            },
        ],
        ways=[],
        relations=[],
    )
    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_ACCOMMODATION],
        nodes=[
            {"id": 11, "location": (2.552, 48.552), "tags": {"tourism": "hotel", "name": "Relais"}}
        ],
        ways=[],
        relations=[],
    )
    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_RESUPPLY],
        nodes=[
            {
                "id": 21,
                "location": (2.549, 48.549),
                "tags": {"shop": "bakery", "name": "Boulangerie"},
            }
        ],
        ways=[],
        relations=[],
    )
    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_LANDMARKS],
        nodes=[
            {
                "id": 31,
                "location": (2.553, 48.553),
                "tags": {"historic": "castle", "name": "Chateau"},
            }
        ],
        ways=[],
        relations=[],
    )
    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_FOREST],
        nodes=[
            {"id": 41, "location": (2.40, 48.40), "tags": {}},
            {"id": 42, "location": (2.70, 48.40), "tags": {}},
            {"id": 43, "location": (2.70, 48.70), "tags": {}},
            {"id": 44, "location": (2.40, 48.70), "tags": {}},
        ],
        ways=[{"id": 50, "nodes": [41, 42, 43, 44, 41], "tags": {"landuse": "forest"}}],
        relations=[],
    )
    trail_nodes = [
        {"id": 60 + position, "location": coordinate, "tags": {}}
        for position, coordinate in enumerate(TRAIL_COORDINATES)
    ]
    write_pbf(
        directory / EXTRACT_FILENAMES[LAYER_TRAILS],
        nodes=trail_nodes,
        ways=[
            {"id": 70, "nodes": [60, 61], "tags": {"highway": "path"}},
            {"id": 71, "nodes": [61, 62], "tags": {"highway": "path"}},
        ],
        relations=[
            {
                "id": RELATION_ID,
                "members": [("w", 70, ""), ("w", 71, "")],
                "tags": {"route": "hiking", "ref": ROUTE_REF, "name": "Sentier de test"},
            }
        ],
    )


def write_sncf_cache(directory: Path) -> None:
    directory.mkdir(parents=True)
    records = [
        {"nom": "Gare Sud", "libellecourt": "AAA", "codes_uic": "87000001", "codeinsee": "77288"},
        {"nom": "Gare Nord", "libellecourt": "BBB", "codes_uic": "87000002", "codeinsee": "77350"},
    ]
    (directory / SNCF_CACHE_FILENAME).write_text(json.dumps(records), encoding="utf-8")


def write_srtm_tile(directory: Path) -> None:
    """N48E002: elevation rises 1 m per row from north (100 m) to south."""
    directory.mkdir(parents=True)
    elevations = array(
        "h", (100 + row for row in range(SRTM3_SAMPLES) for _column in range(SRTM3_SAMPLES))
    )
    if sys.byteorder == "little":
        elevations.byteswap()  # .hgt is big-endian
    (directory / "N48E002.hgt").write_bytes(elevations.tobytes())


def write_routes(path: Path) -> None:
    path.write_text(
        f'routes:\n  - ref: "{ROUTE_REF}"\n    name: "Sentier de test"\n'
        f"    relation_id: {RELATION_ID}\n"
        '    description: "Une boucle de test."\n',
        encoding="utf-8",
    )


class StageFailedError(RuntimeError):
    pass


def run_stage(environment: dict[str, str], *arguments: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "open_rando", *arguments],
        cwd=PIPELINE_DIRECTORY,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise StageFailedError(f"{arguments} failed:\n{completed.stderr[-3000:]}")


def build_fixture_data(root: Path) -> Path:
    """Seed caches under root, run every offline stage, return the data directory."""
    data = root / "data"
    cache = root / "cache"
    write_extracts(cache / "osm")
    write_sncf_cache(cache / "sncf")
    write_srtm_tile(cache / "srtm")
    write_routes(root / "routes.yaml")

    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("OPEN_RANDO_")
    }
    environment.update(
        OPEN_RANDO_DATA_DIR=str(data),
        OPEN_RANDO_CACHE_DIR=str(cache),
        OPEN_RANDO_ROUTES_PATH=str(root / "routes.yaml"),
        # Nothing listens here: any stage reaching for OSRM fails.
        OPEN_RANDO_OSRM_URL="http://127.0.0.1:9",
    )

    run_stage(environment, "osm-index", "--extracts-dir", str(cache / "osm"))
    run_stage(environment, "tracks")
    run_stage(environment, "pois", "--skip-gtfs")
    run_stage(environment, "link", "--skip-walking-refinement")
    run_stage(environment, "catalog")
    return data


if __name__ == "__main__":
    # CI builds the website against this data: python -m tests.end_to_end_fixture <root>
    print(build_fixture_data(Path(sys.argv[1]).resolve()))
