"""Detached fragments collected by OSM superroutes must not become trail."""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString

from open_rando.fetchers.overpass import _drop_spurious_segments, _segment_length_km


def line_along_latitude(start_longitude: float, latitude: float, span: float) -> LineString:
    """A straight line at a fixed latitude, span degrees long."""
    steps = 20
    return LineString(
        [(start_longitude + span * step / steps, latitude) for step in range(steps + 1)]
    )


# ~1200 km main line, and a 300 km continuation 0.2 degrees further east.
MAIN_LINE = line_along_latitude(-1.0, 45.0, 15.0)
CONTINUATION = line_along_latitude(14.5, 44.0, 4.0)


class TestDropSpuriousSegments:
    def test_a_continuous_trail_is_untouched(self) -> None:
        assert _drop_spurious_segments(MAIN_LINE) is MAIN_LINE

    def test_keeps_a_long_second_half(self) -> None:
        trail = MultiLineString([MAIN_LINE, CONTINUATION])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, MultiLineString)
        assert len(result.geoms) == 2

    def test_drops_a_short_fragment_far_from_the_trail(self) -> None:
        """GR 4 collected 12-15 km variants 180-385 km away from its line."""
        far_fragment = line_along_latitude(2.8, 40.0, 0.15)
        trail = MultiLineString([MAIN_LINE, far_fragment])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, LineString)
        assert result.equals(MAIN_LINE)

    def test_drops_a_branch_that_rejoins_the_trail(self) -> None:
        """GR 11 and GR 34 carry variants that touch the main line at a junction."""
        branch = line_along_latitude(5.0, 45.001, 0.5)
        assert _segment_length_km(branch) > 10.0
        trail = MultiLineString([MAIN_LINE, branch])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, LineString)
        assert result.equals(MAIN_LINE)

    def test_keeps_a_continuation_that_later_runs_past_the_trail(self) -> None:
        """GR 34 rounds peninsulas: a continuation can pass within a km of the
        main line again without being a branch. Half of it was dropped before
        the ends, rather than the nearest approach, decided."""
        continuation = LineString(
            [(14.5, 45.0), (15.5, 45.0), (15.5, 46.0), (5.0, 46.0), (5.0, 45.005)]
        )
        trail = MultiLineString([MAIN_LINE, continuation])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, MultiLineString)
        assert len(result.geoms) == 2

    def test_keeps_a_continuation_across_an_unmapped_stretch(self) -> None:
        """GR 4 resumes 19km further on: too far to be a branch, too close to be
        another trail."""
        continuation = line_along_latitude(14.2, 44.9, 1.0)
        trail = MultiLineString([MAIN_LINE, continuation])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, MultiLineString)
        assert len(result.geoms) == 2

    def test_drops_a_tiny_stub_wherever_it_sits(self) -> None:
        tiny_stub = line_along_latitude(5.0, 45.02, 0.02)
        assert _segment_length_km(tiny_stub) < 10.0
        trail = MultiLineString([MAIN_LINE, tiny_stub])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, LineString)

    def test_keeps_the_longest_segment_when_everything_looks_spurious(self) -> None:
        first = line_along_latitude(0.0, 45.0, 0.05)
        second = line_along_latitude(10.0, 40.0, 0.04)
        trail = MultiLineString([first, second])

        result = _drop_spurious_segments(trail)

        assert isinstance(result, LineString)
        assert result.equals(first)
