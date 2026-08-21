"""A trail mapped in several pieces must not charge its gaps as walked."""

from __future__ import annotations

from shapely.geometry import LineString, MultiLineString

from open_rando.processors.elevation import compute_trail_elevation_profile
from open_rando.processors.slice import (
    compute_segment_distance_km,
    compute_segments_distance_km,
    compute_trail_gaps_km,
    extract_substring_segments,
)


class FlatReader:
    """SRTM stand-in: flat ground, so distance and time carry the assertions."""

    def __init__(self, elevation: float = 100.0) -> None:
        self.elevation = elevation

    def get_elevation(self, latitude: float, longitude: float) -> float:
        return self.elevation


class StepReader:
    """Flat within each segment, 500m higher east of the gap."""

    def get_elevation(self, latitude: float, longitude: float) -> float:
        # Threshold sits inside the gap, so each segment stays flat.
        return 600.0 if longitude > 0.5 else 100.0


# Two 0.1°-long segments (~7.4 km each at 45°N) separated by a ~78 km gap.
FIRST_SEGMENT = LineString([(0.0, 45.0), (0.1, 45.0)])
SECOND_SEGMENT = LineString([(1.0, 45.0), (1.1, 45.0)])
GAPPED_TRAIL = MultiLineString([FIRST_SEGMENT, SECOND_SEGMENT])
CONTINUOUS_TRAIL = LineString([(0.0, 45.0), (0.1, 45.0)])


class TestComputeTrailGapsKm:
    def test_a_continuous_trail_has_no_gap(self) -> None:
        assert compute_trail_gaps_km(CONTINUOUS_TRAIL) == 0.0

    def test_measures_the_jump_between_segments(self) -> None:
        gap_km = compute_trail_gaps_km(GAPPED_TRAIL)
        expected_km = compute_segment_distance_km(LineString([(0.1, 45.0), (1.0, 45.0)]))
        assert gap_km == expected_km
        assert gap_km > 60.0


class TestExtractSubstringSegments:
    def test_keeps_one_piece_per_segment(self) -> None:
        pieces = extract_substring_segments(GAPPED_TRAIL, 0.0, 1.0)

        assert len(pieces) == 2

    def test_excludes_the_gap_from_the_measured_distance(self) -> None:
        pieces = extract_substring_segments(GAPPED_TRAIL, 0.0, 1.0)

        walked_km = compute_segments_distance_km(pieces)
        segments_km = compute_segment_distance_km(FIRST_SEGMENT) + compute_segment_distance_km(
            SECOND_SEGMENT
        )
        assert walked_km == segments_km
        assert walked_km < compute_trail_gaps_km(GAPPED_TRAIL)

    def test_clips_within_a_single_segment(self) -> None:
        pieces = extract_substring_segments(GAPPED_TRAIL, 0.0, 0.25)

        assert len(pieces) == 1
        assert compute_segments_distance_km(pieces) < compute_segment_distance_km(FIRST_SEGMENT)

    def test_handles_a_continuous_trail(self) -> None:
        pieces = extract_substring_segments(CONTINUOUS_TRAIL, 0.0, 0.5)

        assert len(pieces) == 1


class TestComputeTrailElevationProfile:
    def test_total_distance_excludes_the_gap(self) -> None:
        profile = compute_trail_elevation_profile(GAPPED_TRAIL, FlatReader(), 100.0)

        walked_km = compute_segment_distance_km(FIRST_SEGMENT) + compute_segment_distance_km(
            SECOND_SEGMENT
        )
        assert profile.distances_km[-1] == pytest_approx(walked_km, 0.2)

    def test_duration_excludes_the_gap(self) -> None:
        profile = compute_trail_elevation_profile(GAPPED_TRAIL, FlatReader(), 100.0)

        # Flat ground at 4 km/h over the two segments only.
        expected_minutes = profile.distances_km[-1] / 4.0 * 60.0
        assert profile.cumulative_times_min[-1] == pytest_approx(expected_minutes, 0.5)

    def test_records_where_the_trail_breaks(self) -> None:
        profile = compute_trail_elevation_profile(GAPPED_TRAIL, FlatReader(), 100.0)

        assert len(profile.segment_boundaries_km) == 1
        boundary = profile.segment_boundaries_km[0]
        assert boundary == pytest_approx(compute_segment_distance_km(FIRST_SEGMENT), 0.2)

    def test_the_elevation_step_across_a_gap_is_not_a_climb(self) -> None:
        profile = compute_trail_elevation_profile(GAPPED_TRAIL, StepReader(), 100.0)

        # Each segment is flat; the 500m difference sits across the gap.
        assert profile.gain_m == 0
        assert profile.loss_m == 0
        assert profile.max_m == 600
        assert profile.min_m == 100

    def test_distances_stay_monotonic_across_the_break(self) -> None:
        profile = compute_trail_elevation_profile(GAPPED_TRAIL, FlatReader(), 100.0)

        assert profile.distances_km == sorted(profile.distances_km)
        assert profile.cumulative_times_min == sorted(profile.cumulative_times_min)

    def test_a_continuous_trail_reports_no_break(self) -> None:
        profile = compute_trail_elevation_profile(CONTINUOUS_TRAIL, FlatReader(), 100.0)

        assert profile.segment_boundaries_km == []
        assert profile.distances_km[-1] > 0


def pytest_approx(value: float, tolerance: float) -> object:
    import pytest

    return pytest.approx(value, abs=tolerance)
