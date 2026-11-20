"""Where OSM data comes from for one pipeline run.

A run reads one source: the local extract index (the default, and the only
one meant for real runs), or the Overpass API when `OPEN_RANDO_ALLOW_OVERPASS=1`
is set for development without the ~5GB France extract.

One exception: a trail relation that crosses the border is missing ways from
the France extract. The local source fetches that relation, and only that
relation, from Overpass, and records it in `border_fallback_relations`.
"""

from __future__ import annotations

import logging
import os
from functools import cache
from pathlib import Path
from typing import Protocol

from open_rando.config import OVERPASS_TIMEOUT_SECONDS, OVERPASS_TRAIL_CACHE_TTL_SECONDS
from open_rando.fetchers import osm_extract
from open_rando.fetchers.osm_extract import (
    LAYER_FOREST,
    LAYER_LANDMARKS,
    LAYER_STATIONS,
    LAYER_TRAILS,
    OsmExtractIndex,
)
from open_rando.fetchers.overpass import query_overpass
from open_rando.json_types import JsonObject
from open_rando.osm_tags import FOREST_TAGS, LANDMARK_KINDS_BY_KEY

logger = logging.getLogger("open_rando")

ALLOW_OVERPASS_ENVIRONMENT_VARIABLE = "OPEN_RANDO_ALLOW_OVERPASS"

# (south, west, north, east), the order Overpass bounding boxes use.
BoundingBox = tuple[float, float, float, float]


class OsmSourceUnavailableError(RuntimeError):
    """The selected source cannot answer: index missing or a layer not built."""


class OsmSource(Protocol):
    """OSM data for one run. Every method returns (Overpass-shaped data, cache_hit)."""

    name: str

    def trail(self, relation_id: int) -> tuple[JsonObject, bool]: ...

    def stations(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]: ...

    def landmarks(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]: ...

    def forest(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]: ...


class LocalExtractSource:
    """Reads the SQLite index built by `python -m open_rando osm-index`."""

    name = "local-extract"

    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self.border_fallback_relations: list[int] = []

    def trail(self, relation_id: int) -> tuple[JsonObject, bool]:
        index = self._open(LAYER_TRAILS, bounding_box=None)
        try:
            data = index.trail_elements(relation_id)
        finally:
            index.close()
        if data is not None:
            return data, True
        logger.warning(
            "Relation %d is incomplete in the local extract (crosses the border?), "
            "fetching it from Overpass",
            relation_id,
        )
        self.border_fallback_relations.append(relation_id)
        return OverpassSource().trail(relation_id)

    def stations(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]:
        return self._points(LAYER_STATIONS, bounding_box), True

    def landmarks(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]:
        return self._points(LAYER_LANDMARKS, bounding_box), True

    def forest(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]:
        index = self._open(LAYER_FOREST, bounding_box)
        try:
            return index.area_elements(LAYER_FOREST, *bounding_box), True
        finally:
            index.close()

    def _points(self, layer: str, bounding_box: BoundingBox) -> JsonObject:
        index = self._open(layer, bounding_box)
        try:
            return index.point_elements(layer, *bounding_box)
        finally:
            index.close()

    def _open(self, layer: str, bounding_box: BoundingBox | None) -> OsmExtractIndex:
        index = OsmExtractIndex.open_for_reading(self.index_path)
        if index is None:
            raise OsmSourceUnavailableError(f"No OSM extract index at {self.index_path}")
        if not index.has_layer(layer):
            index.close()
            raise OsmSourceUnavailableError(
                f"The OSM extract index has no {layer} layer. "
                "Run `make -f Makefile.osm` (in pipeline/) to build it."
            )
        if bounding_box is not None and not index.covers(layer, *bounding_box):
            # Outside the extract there is no French data to find; answer with
            # what the extract holds rather than switching source mid-run.
            logger.warning(
                "Local %s extract does not fully cover (%.3f,%.3f)-(%.3f,%.3f)",
                layer,
                *bounding_box,
            )
        return index


class OverpassSource:
    """Public Overpass API, with the disk cache in `fetchers/overpass.py`."""

    name = "overpass"

    def trail(self, relation_id: int) -> tuple[JsonObject, bool]:
        logger.info("Fetching relation %d from Overpass with full recursion...", relation_id)
        # The superroute, its child relations, and all ways with geometry.
        query = f"""
[out:json][timeout:300];
rel({relation_id});
out body;
rel({relation_id});
rel(r);
out body;
rel({relation_id});
way(r);
out geom;
rel({relation_id});
rel(r);
way(r);
out geom;
"""
        return query_overpass(query, cache_ttl_seconds=OVERPASS_TRAIL_CACHE_TTL_SECONDS)

    def stations(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]:
        box = _format_bounding_box(bounding_box)
        query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
  node["railway"="station"]["disused"!="yes"]["abandoned"!="yes"]({box});
  node["railway"="halt"]["disused"!="yes"]["abandoned"!="yes"]({box});
  node["highway"="bus_stop"]({box});
  node["public_transport"="platform"]["bus"="yes"]({box});
);
out body;
"""
        return query_overpass(query)

    def landmarks(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]:
        box = _format_bounding_box(bounding_box)
        selectors = [
            f'  {element_type}["{key}"="{kind}"]({box});'
            for key, kinds in LANDMARK_KINDS_BY_KEY
            for kind in kinds
            for element_type in ("node", "way")
        ]
        body = "\n".join(selectors)
        query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
{body}
);
out center;
"""
        return query_overpass(query)

    def forest(self, bounding_box: BoundingBox) -> tuple[JsonObject, bool]:
        box = _format_bounding_box(bounding_box)
        selectors = [
            f'  {element_type}["{key}"="{value}"]({box});'
            for element_type in ("way", "rel")
            for key, value in FOREST_TAGS
        ]
        body = "\n".join(selectors)
        query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
(
{body}
);
out geom;
"""
        return query_overpass(query)


def _format_bounding_box(bounding_box: BoundingBox) -> str:
    return ",".join(str(coordinate) for coordinate in bounding_box)


def overpass_allowed() -> bool:
    return os.environ.get(ALLOW_OVERPASS_ENVIRONMENT_VARIABLE) == "1"


@cache
def get_osm_source() -> OsmSource:
    """The source for this run: the local index, or Overpass when explicitly allowed."""
    index_path = osm_extract.default_index_path()
    if index_path.exists():
        return LocalExtractSource(index_path)
    if overpass_allowed():
        logger.warning("No local OSM extract index; reading from the Overpass API")
        return OverpassSource()
    raise OsmSourceUnavailableError(
        f"No OSM extract index at {index_path}. Build it with `make -f Makefile.osm` "
        f"(in pipeline/), or set {ALLOW_OVERPASS_ENVIRONMENT_VARIABLE}=1 to read from "
        "the public Overpass API (development only)."
    )
