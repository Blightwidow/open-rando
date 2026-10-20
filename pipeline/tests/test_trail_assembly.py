"""Assembling a trail from relation elements — the code that keeps breaking.

Three separate commits fixed bugs here (1f3452c ways not fetched for simple
routes, f14dfeb MultiLineString extraction skipping gap jumps, 2e19acc trails
not split at large gaps) with no test covering any of them.
"""

from __future__ import annotations

from typing import Any

import pytest
from shapely.geometry import LineString, MultiLineString

from open_rando.fetchers.overpass import _build_trail_from_elements, _chain_ways

RELATION_ID = 900


def way(way_id: int, points: list[tuple[float, float]]) -> dict[str, Any]:
    """A way element as Overpass returns it with `out geom` (lat/lon points)."""
    return {
        "type": "way",
        "id": way_id,
        "geometry": [{"lat": latitude, "lon": longitude} for longitude, latitude in points],
    }


def relation(
    relation_id: int,
    members: list[tuple[str, int]],
    tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "relation",
        "id": relation_id,
        "tags": tags if tags is not None else {"route": "hiking"},
        "members": [{"type": kind, "ref": ref, "role": ""} for kind, ref in members],
    }


def straight(start: float, end: float, latitude: float = 45.0) -> list[tuple[float, float]]:
    steps = 4
    return [(start + (end - start) * step / steps, latitude) for step in range(steps + 1)]


def build(elements: list[dict[str, Any]]) -> tuple[Any, dict[str, str | int]]:
    trail, metadata, cache_hit = _build_trail_from_elements(
        RELATION_ID, {"elements": elements}, cache_hit=True
    )
    assert cache_hit is True
    return trail, metadata


class TestSimpleRoute:
    def test_chains_member_ways_into_one_line(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("way", 1), ("way", 2)], {"ref": "GR 1", "name": "Tour"}),
                way(1, straight(0.0, 1.0)),
                way(2, straight(1.0, 2.0)),
            ]
        )

        assert isinstance(trail, LineString)
        assert trail.coords[0] == (0.0, 45.0)
        assert trail.coords[-1] == (2.0, 45.0)

    def test_reads_name_and_ref_from_the_relation(self) -> None:
        _trail, metadata = build(
            [
                relation(RELATION_ID, [("way", 1)], {"ref": "GR 1", "name": "Tour"}),
                way(1, straight(0.0, 1.0)),
            ]
        )

        assert metadata == {"name": "Tour", "ref": "GR 1", "osm_relation_id": RELATION_ID}

    def test_follows_member_order_not_response_order(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("way", 2), ("way", 1)]),
                way(1, straight(1.0, 2.0)),
                way(2, straight(0.0, 1.0)),
            ]
        )

        assert trail.coords[0] == (0.0, 45.0)
        assert trail.coords[-1] == (2.0, 45.0)

    def test_reverses_a_way_stored_against_the_walking_direction(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("way", 1), ("way", 2)]),
                way(1, straight(0.0, 1.0)),
                way(2, list(reversed(straight(1.0, 2.0)))),
            ]
        )

        assert isinstance(trail, LineString)
        assert trail.coords[-1] == (2.0, 45.0)
        # No zigzag: a reversed way would double back to 1.0 and out again.
        longitudes = [longitude for longitude, _latitude in trail.coords]
        assert longitudes == sorted(longitudes)

    def test_skips_a_member_whose_geometry_is_missing(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("way", 1), ("way", 2), ("way", 3)]),
                way(1, straight(0.0, 1.0)),
                way(3, straight(1.0, 2.0)),
            ]
        )

        assert isinstance(trail, LineString)
        assert trail.coords[-1] == (2.0, 45.0)

    def test_ignores_a_way_with_a_single_point(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("way", 1), ("way", 2)]),
                way(1, straight(0.0, 1.0)),
                way(2, [(5.0, 45.0)]),
            ]
        )

        assert isinstance(trail, LineString)
        assert trail.coords[-1] == (1.0, 45.0)

    def test_raises_when_the_relation_is_absent(self) -> None:
        with pytest.raises(RuntimeError, match="not found"):
            build([way(1, straight(0.0, 1.0))])

    def test_raises_when_no_member_way_has_geometry(self) -> None:
        with pytest.raises(RuntimeError, match="No ways found"):
            build([relation(RELATION_ID, [("way", 1)])])


class TestSuperroute:
    def test_joins_children_in_member_order(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("relation", 901), ("relation", 902)]),
                relation(901, [("way", 1)]),
                relation(902, [("way", 2)]),
                way(1, straight(0.0, 1.0)),
                way(2, straight(1.0, 2.0)),
            ]
        )

        assert isinstance(trail, LineString)
        assert trail.coords[0] == (0.0, 45.0)
        assert trail.coords[-1] == (2.0, 45.0)

    def test_splits_the_trail_at_a_large_gap_between_children(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("relation", 901), ("relation", 902)]),
                relation(901, [("way", 1)]),
                relation(902, [("way", 2)]),
                way(1, straight(0.0, 1.0)),
                # Resumes 2 degrees further east: past MAX_CHAIN_GAP_DEGREES.
                way(2, straight(3.0, 4.0)),
            ]
        )

        assert isinstance(trail, MultiLineString)
        assert len(trail.geoms) == 2

    def test_survives_a_child_missing_from_the_response(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("relation", 901), ("relation", 902)]),
                relation(901, [("way", 1)]),
                way(1, straight(0.0, 1.0)),
            ]
        )

        assert isinstance(trail, LineString)

    def test_survives_a_child_without_ways(self) -> None:
        trail, _metadata = build(
            [
                relation(RELATION_ID, [("relation", 901), ("relation", 902)]),
                relation(901, [("way", 1)]),
                relation(902, []),
                way(1, straight(0.0, 1.0)),
            ]
        )

        assert isinstance(trail, LineString)

    def test_raises_when_no_child_yields_geometry(self) -> None:
        with pytest.raises(RuntimeError, match="No geometry found"):
            build(
                [
                    relation(RELATION_ID, [("relation", 901)]),
                    relation(901, []),
                ]
            )


class TestChainWays:
    def test_joins_ways_that_share_an_endpoint(self) -> None:
        segments = _chain_ways([straight(0.0, 1.0), straight(1.0, 2.0)])

        assert len(segments) == 1
        assert segments[0].coords[-1] == (2.0, 45.0)

    def test_starts_a_new_segment_past_the_gap_threshold(self) -> None:
        segments = _chain_ways([straight(0.0, 1.0), straight(3.0, 4.0)])

        assert len(segments) == 2

    def test_bridges_a_small_gap_within_one_segment(self) -> None:
        segments = _chain_ways([straight(0.0, 1.0), straight(1.01, 2.0)])

        assert len(segments) == 1
