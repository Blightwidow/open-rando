"""Trail segments must be stored in the order they are walked."""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString

from open_rando.fetchers.overpass import order_segments_along_route
from open_rando.processors.slice import compute_trail_gaps_km


def line(start: float, end: float, latitude: float = 45.0) -> LineString:
    """A straight west-to-east line between two longitudes."""
    steps = 10
    return LineString(
        [(start + (end - start) * step / steps, latitude) for step in range(steps + 1)]
    )


class TestOrderSegmentsAlongRoute:
    def test_a_single_line_is_untouched(self) -> None:
        single = line(0.0, 1.0)

        assert order_segments_along_route(single) is single

    def test_orders_shuffled_segments_along_the_route(self) -> None:
        first, second, third = line(0.0, 1.0), line(1.1, 2.0), line(2.1, 3.0)
        shuffled = MultiLineString([second, third, first])

        result = order_segments_along_route(shuffled)

        assert isinstance(result, MultiLineString)
        starts = [round(segment.coords[0][0], 1) for segment in result.geoms]
        assert starts == [0.0, 1.1, 2.1]

    def test_reverses_a_segment_stored_backwards(self) -> None:
        forward = line(0.0, 1.0)
        backwards = LineString(list(line(1.1, 2.0).coords)[::-1])
        trail = MultiLineString([forward, backwards])

        result = order_segments_along_route(trail)

        second = result.geoms[1]
        assert round(second.coords[0][0], 1) == 1.1
        assert round(second.coords[-1][0], 1) == 2.0

    def test_puts_an_extension_before_the_middle(self) -> None:
        """GR 70 stores its middle first, then its southern end, then the
        northern extension that starts where the middle starts."""
        middle = line(1.0, 3.0)
        southern_end = line(3.1, 3.6)
        northern_extension = LineString(list(line(0.4, 1.0).coords))
        trail = MultiLineString([middle, southern_end, northern_extension])

        result = order_segments_along_route(trail)

        starts = [round(segment.coords[0][0], 1) for segment in result.geoms]
        assert starts == [0.4, 1.0, 3.1]

    def test_ordering_shrinks_the_reported_gaps(self) -> None:
        middle = line(1.0, 3.0)
        southern_end = line(3.1, 3.6)
        northern_extension = line(0.4, 1.0)
        stored_order = MultiLineString([middle, southern_end, northern_extension])

        before = compute_trail_gaps_km(stored_order)
        after = compute_trail_gaps_km(order_segments_along_route(stored_order))

        # Stored order jumps back and forth across the route; walking order
        # leaves only the one real 0.1 degree join (~7.9 km at this latitude).
        assert before > 150.0
        assert after < 10.0

    def test_is_deterministic_whatever_the_stored_order(self) -> None:
        first, second, third = line(0.0, 1.0), line(1.1, 2.0), line(2.1, 3.0)

        one = order_segments_along_route(MultiLineString([second, third, first]))
        another = order_segments_along_route(MultiLineString([third, first, second]))

        assert [segment.coords[0] for segment in one.geoms] == [
            segment.coords[0] for segment in another.geoms
        ]

    def test_keeps_every_segment(self) -> None:
        segments = [line(0.0, 1.0), line(5.0, 6.0), line(2.0, 3.0)]
        trail = MultiLineString(segments)

        result = order_segments_along_route(trail)

        assert isinstance(result, MultiLineString)
        assert len(result.geoms) == 3
        assert sum(len(segment.coords) for segment in result.geoms) == sum(
            len(segment.coords) for segment in segments
        )
