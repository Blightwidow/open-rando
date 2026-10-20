"""Query OSM data from a locally built extract index instead of Overpass.

The public Overpass API answers with 504s under load, and the pipeline's
queries are plain tag filters over France. `python -m open_rando osm-index`
turns Geofabrik extracts into the SQLite index read here; the fetchers fall
back to Overpass whenever a layer is missing, so the index is optional.

Query results are shaped like Overpass JSON responses on purpose: the existing
parsers, and their tests, stay untouched.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_rando.config import OSM_INDEX_PATH
from open_rando.osm_tags import (
    ACCOMMODATION_KINDS,
    FOREST_TAGS,
    LANDMARK_KINDS_BY_KEY,
    TRAIL_ROUTE_VALUES,
)

logger = logging.getLogger("open_rando")

LAYER_STATIONS = "stations"
LAYER_ACCOMMODATION = "accommodation"
LAYER_LANDMARKS = "landmarks"
LAYER_FOREST = "forest"
LAYER_TRAILS = "trails"

POINT_LAYERS = (LAYER_STATIONS, LAYER_ACCOMMODATION, LAYER_LANDMARKS)
ALL_LAYERS = (*POINT_LAYERS, LAYER_FOREST, LAYER_TRAILS)

SCHEMA_STATEMENTS = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS points (
        layer TEXT NOT NULL,
        osm_type TEXT NOT NULL,
        osm_id INTEGER NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        tags TEXT NOT NULL,
        PRIMARY KEY (layer, osm_type, osm_id)
    )""",
    "CREATE INDEX IF NOT EXISTS points_bbox ON points (layer, lat, lon)",
    """CREATE TABLE IF NOT EXISTS areas (
        layer TEXT NOT NULL,
        osm_type TEXT NOT NULL,
        osm_id INTEGER NOT NULL,
        min_lat REAL NOT NULL,
        min_lon REAL NOT NULL,
        max_lat REAL NOT NULL,
        max_lon REAL NOT NULL,
        geometry TEXT NOT NULL,
        PRIMARY KEY (layer, osm_type, osm_id)
    )""",
    "CREATE INDEX IF NOT EXISTS areas_bbox ON areas (layer, min_lat, max_lat)",
    """CREATE TABLE IF NOT EXISTS trail_relations (
        relation_id INTEGER PRIMARY KEY,
        tags TEXT NOT NULL,
        members TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS trail_ways (
        way_id INTEGER PRIMARY KEY,
        geometry TEXT NOT NULL
    )""",
)


# ---------------------------------------------------------------------------
# Tag matching — mirrors the Overpass selectors the fetchers use
# ---------------------------------------------------------------------------


def is_station_tagged(tags: dict[str, str]) -> bool:
    """Match the station/bus-stop selectors of `fetchers.stations`."""
    if tags.get("disused") == "yes" or tags.get("abandoned") == "yes":
        railway = tags.get("railway")
        if railway in ("station", "halt"):
            return False
    if tags.get("railway") in ("station", "halt"):
        return True
    if tags.get("highway") == "bus_stop":
        return True
    return tags.get("public_transport") == "platform" and tags.get("bus") == "yes"


def is_accommodation_tagged(tags: dict[str, str]) -> bool:
    """Match the accommodation selectors of `fetchers.pois`."""
    return tags.get("tourism", "") in ACCOMMODATION_KINDS


def landmark_kind_for_tags(tags: dict[str, str]) -> str | None:
    """Return the landmark kind of a feature, mirroring `fetchers.landmarks`."""
    for key, kinds in LANDMARK_KINDS_BY_KEY:
        value = tags.get(key, "")
        if value in kinds:
            return value
    return None


def is_forest_tagged(tags: dict[str, str]) -> bool:
    """Match the forest selectors of `processors.geography`."""
    return any(tags.get(key) == value for key, value in FOREST_TAGS)


def is_trail_relation_tagged(tags: dict[str, str]) -> bool:
    """Match hiking route relations."""
    return tags.get("route", "") in TRAIL_ROUTE_VALUES


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


class OsmExtractIndex:
    """Read/write access to the local OSM extract index."""

    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self.connection = connection
        self.path = path

    # -- lifecycle ----------------------------------------------------------

    @classmethod
    def open_for_writing(cls, path: Path | None = None) -> OsmExtractIndex:
        index_path = path or default_index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(index_path)
        index = cls(connection, index_path)
        index.create_schema()
        return index

    @classmethod
    def open_for_reading(cls, path: Path | None = None) -> OsmExtractIndex | None:
        """Open the index, or return None when it has not been built."""
        index_path = path or default_index_path()
        if not index_path.exists():
            return None
        connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
        return cls(connection, index_path)

    def close(self) -> None:
        self.connection.close()

    def create_schema(self) -> None:
        for statement in SCHEMA_STATEMENTS:
            self.connection.execute(statement)
        self.connection.commit()

    # -- writing ------------------------------------------------------------

    def clear_layer(self, layer: str) -> None:
        if layer == LAYER_TRAILS:
            self.connection.execute("DELETE FROM trail_relations")
            self.connection.execute("DELETE FROM trail_ways")
        else:
            self.connection.execute("DELETE FROM points WHERE layer = ?", (layer,))
            self.connection.execute("DELETE FROM areas WHERE layer = ?", (layer,))
        self.connection.execute("DELETE FROM meta WHERE key = ?", (_layer_meta_key(layer),))
        self.connection.commit()

    def insert_points(
        self,
        layer: str,
        rows: Iterable[tuple[str, int, float, float, dict[str, str]]],
    ) -> int:
        payload = [
            (layer, osm_type, osm_id, lat, lon, json.dumps(tags, ensure_ascii=False))
            for osm_type, osm_id, lat, lon, tags in rows
        ]
        self.connection.executemany(
            "INSERT OR REPLACE INTO points (layer, osm_type, osm_id, lat, lon, tags) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            payload,
        )
        return len(payload)

    def insert_areas(
        self,
        layer: str,
        rows: Iterable[tuple[str, int, list[tuple[float, float]]]],
    ) -> int:
        payload = []
        for osm_type, osm_id, coordinates in rows:
            if len(coordinates) < 4:
                continue
            latitudes = [latitude for latitude, _longitude in coordinates]
            longitudes = [longitude for _latitude, longitude in coordinates]
            geometry = [{"lat": latitude, "lon": longitude} for latitude, longitude in coordinates]
            payload.append(
                (
                    layer,
                    osm_type,
                    osm_id,
                    min(latitudes),
                    min(longitudes),
                    max(latitudes),
                    max(longitudes),
                    json.dumps(geometry),
                )
            )
        self.connection.executemany(
            "INSERT OR REPLACE INTO areas "
            "(layer, osm_type, osm_id, min_lat, min_lon, max_lat, max_lon, geometry) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            payload,
        )
        return len(payload)

    def insert_trail_relations(
        self,
        rows: Iterable[tuple[int, dict[str, str], list[dict[str, Any]]]],
    ) -> int:
        payload = [
            (relation_id, json.dumps(tags, ensure_ascii=False), json.dumps(members))
            for relation_id, tags, members in rows
        ]
        self.connection.executemany(
            "INSERT OR REPLACE INTO trail_relations (relation_id, tags, members) VALUES (?, ?, ?)",
            payload,
        )
        return len(payload)

    def insert_trail_ways(
        self,
        rows: Iterable[tuple[int, list[tuple[float, float]]]],
    ) -> int:
        payload = []
        for way_id, coordinates in rows:
            if len(coordinates) < 2:
                continue
            geometry = [{"lat": latitude, "lon": longitude} for latitude, longitude in coordinates]
            payload.append((way_id, json.dumps(geometry)))
        self.connection.executemany(
            "INSERT OR REPLACE INTO trail_ways (way_id, geometry) VALUES (?, ?)",
            payload,
        )
        return len(payload)

    def record_layer(
        self,
        layer: str,
        feature_count: int,
        source: str,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Record a built layer, with the bounding box the extract covers.

        The bbox is what keeps a regional extract honest: a bbox query reaching
        outside it would silently return too few features, so callers fall back
        to Overpass instead.
        """
        details: dict[str, Any] = {
            "features": feature_count,
            "source": source,
            "built_at": datetime.now(UTC).isoformat(),
        }
        if bbox is not None:
            south, west, north, east = bbox
            details["bbox"] = {"south": south, "west": west, "north": north, "east": east}
        self.connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (_layer_meta_key(layer), json.dumps(details)),
        )
        self.connection.commit()

    def commit(self) -> None:
        self.connection.commit()

    # -- reading ------------------------------------------------------------

    def has_layer(self, layer: str) -> bool:
        row = self.connection.execute(
            "SELECT value FROM meta WHERE key = ?", (_layer_meta_key(layer),)
        ).fetchone()
        if row is None:
            return False
        try:
            return int(json.loads(row[0]).get("features", 0)) > 0
        except (ValueError, TypeError):
            return False

    def covers(self, layer: str, south: float, west: float, north: float, east: float) -> bool:
        """Whether the layer's extract covers the requested bounding box."""
        row = self.connection.execute(
            "SELECT value FROM meta WHERE key = ?", (_layer_meta_key(layer),)
        ).fetchone()
        if row is None:
            return False
        bbox = json.loads(row[0]).get("bbox")
        if not bbox:
            # Built before coverage was recorded: assume it covers everything.
            return True
        return bool(
            float(bbox["south"]) <= south
            and float(bbox["west"]) <= west
            and float(bbox["north"]) >= north
            and float(bbox["east"]) >= east
        )

    def layer_summary(self) -> dict[str, dict[str, Any]]:
        summary: dict[str, dict[str, Any]] = {}
        for layer in ALL_LAYERS:
            row = self.connection.execute(
                "SELECT value FROM meta WHERE key = ?", (_layer_meta_key(layer),)
            ).fetchone()
            if row is not None:
                summary[layer] = json.loads(row[0])
        return summary

    def point_elements(
        self,
        layer: str,
        south: float,
        west: float,
        north: float,
        east: float,
    ) -> dict[str, Any]:
        """Overpass-shaped response for a point layer inside a bounding box."""
        cursor = self.connection.execute(
            "SELECT osm_type, osm_id, lat, lon, tags FROM points "
            "WHERE layer = ? AND lat >= ? AND lat <= ? AND lon >= ? AND lon <= ?",
            (layer, south, north, west, east),
        )
        elements = [
            {
                "type": osm_type,
                "id": osm_id,
                "lat": latitude,
                "lon": longitude,
                "tags": json.loads(tags),
            }
            for osm_type, osm_id, latitude, longitude, tags in cursor
        ]
        return {"elements": elements}

    def area_elements(
        self,
        layer: str,
        south: float,
        west: float,
        north: float,
        east: float,
    ) -> dict[str, Any]:
        """Overpass-shaped response for an area layer overlapping a bounding box."""
        cursor = self.connection.execute(
            "SELECT osm_type, osm_id, geometry FROM areas "
            "WHERE layer = ? AND min_lat <= ? AND max_lat >= ? AND min_lon <= ? AND max_lon >= ?",
            (layer, north, south, east, west),
        )
        elements = [
            {"type": osm_type, "id": osm_id, "geometry": json.loads(geometry)}
            for osm_type, osm_id, geometry in cursor
        ]
        return {"elements": elements}

    def trail_elements(self, relation_id: int) -> dict[str, Any] | None:
        """Overpass-shaped response for a route relation and one level of children.

        Mirrors the `rel(id); rel(r); way(r)` recursion of the Overpass query.
        Returns None when the relation is absent, or when any member way is
        missing — a route clipped by the extract boundary would otherwise yield
        a silently truncated trail instead of falling back to Overpass.
        """
        row = self.connection.execute(
            "SELECT tags, members FROM trail_relations WHERE relation_id = ?", (relation_id,)
        ).fetchone()
        if row is None:
            return None

        tags, members = json.loads(row[0]), json.loads(row[1])
        elements: list[dict[str, Any]] = [
            {"type": "relation", "id": relation_id, "tags": tags, "members": members}
        ]

        way_ids: list[int] = [member["ref"] for member in members if member.get("type") == "way"]

        child_ids = [member["ref"] for member in members if member.get("type") == "relation"]
        for child_id in child_ids:
            child_row = self.connection.execute(
                "SELECT tags, members FROM trail_relations WHERE relation_id = ?", (child_id,)
            ).fetchone()
            if child_row is None:
                continue
            child_members = json.loads(child_row[1])
            elements.append(
                {
                    "type": "relation",
                    "id": child_id,
                    "tags": json.loads(child_row[0]),
                    "members": child_members,
                }
            )
            way_ids.extend(member["ref"] for member in child_members if member.get("type") == "way")

        way_elements = list(self._way_elements(way_ids))
        missing = len(set(way_ids)) - len(way_elements)
        if missing > 0:
            logger.info(
                "Relation %d is missing %d of %d member ways in the local extract",
                relation_id,
                missing,
                len(set(way_ids)),
            )
            return None

        elements.extend(way_elements)
        return {"elements": elements}

    def _way_elements(self, way_ids: Iterable[int]) -> Iterator[dict[str, Any]]:
        seen: set[int] = set()
        unique_ids: list[int] = []
        for way_id in way_ids:
            if way_id in seen:
                continue
            seen.add(way_id)
            unique_ids.append(way_id)
        for chunk_start in range(0, len(unique_ids), 500):
            chunk = unique_ids[chunk_start : chunk_start + 500]
            placeholders = ",".join("?" * len(chunk))
            cursor = self.connection.execute(
                f"SELECT way_id, geometry FROM trail_ways WHERE way_id IN ({placeholders})",
                chunk,
            )
            for way_id, geometry in cursor:
                yield {"type": "way", "id": way_id, "geometry": json.loads(geometry)}


def default_index_path() -> Path:
    return Path(OSM_INDEX_PATH).expanduser()


def _layer_meta_key(layer: str) -> str:
    return f"layer:{layer}"


def open_layer(
    layer: str,
    bbox: tuple[float, float, float, float] | None = None,
) -> OsmExtractIndex | None:
    """Open the index if it can answer for this layer (and bbox), else None.

    Callers use this to prefer local data and fall back to Overpass.
    """
    index = OsmExtractIndex.open_for_reading()
    if index is None:
        return None
    if not index.has_layer(layer):
        index.close()
        return None
    if bbox is not None and not index.covers(layer, *bbox):
        logger.info(
            "Local %s extract does not cover (%.3f,%.3f)-(%.3f,%.3f), using Overpass",
            layer,
            *bbox,
        )
        index.close()
        return None
    return index
