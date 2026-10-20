"""Gain and loss must count every climb, not the net difference end to end."""

from __future__ import annotations

import pytest

from open_rando.processors.elevation import (
    ELEVATION_NOISE_THRESHOLD_METERS,
    _compute_gain_loss,
    classify_difficulty,
)


class TestComputeGainLoss:
    def test_a_monotone_climb_counts_once(self) -> None:
        assert _compute_gain_loss([100.0, 200.0, 300.0, 600.0]) == (500, 0)

    def test_a_monotone_descent_counts_as_loss(self) -> None:
        assert _compute_gain_loss([600.0, 300.0, 100.0]) == (0, 500)

    def test_a_sawtooth_counts_every_climb(self) -> None:
        """The bug this replaces returned the net difference: 0 gain, 0 loss."""
        elevations: list[float] = []
        for _ in range(10):
            elevations.extend([100.0, 200.0])
        elevations.append(100.0)

        gain_m, loss_m = _compute_gain_loss(elevations)

        assert gain_m == 1000
        assert loss_m == 1000

    def test_an_out_and_back_profile_is_not_flat(self) -> None:
        gain_m, loss_m = _compute_gain_loss([0.0, 500.0, 1000.0, 500.0, 0.0])

        assert (gain_m, loss_m) == (1000, 1000)

    def test_sampling_noise_below_the_threshold_is_ignored(self) -> None:
        elevations: list[float] = []
        for index in range(50):
            elevations.append(100.0 + (2.0 if index % 2 else 0.0))

        assert _compute_gain_loss(elevations) == (0, 0)

    def test_noise_does_not_break_a_real_climb(self) -> None:
        elevations = [100.0, 102.0, 101.0, 300.0, 299.0, 500.0]

        gain_m, _loss_m = _compute_gain_loss(elevations)

        assert gain_m == pytest.approx(400, abs=5)

    def test_a_climb_at_the_threshold_counts(self) -> None:
        assert _compute_gain_loss([0.0, float(ELEVATION_NOISE_THRESHOLD_METERS)]) == (5, 0)

    def test_flat_ground_has_neither(self) -> None:
        assert _compute_gain_loss([200.0] * 20) == (0, 0)

    def test_a_single_sample_has_neither(self) -> None:
        assert _compute_gain_loss([200.0]) == (0, 0)


class TestClassifyDifficulty:
    def test_a_flat_towpath_stays_easy_however_long(self) -> None:
        # 1100 km along the Seine, real ascent but spread thin.
        assert classify_difficulty(gain_m=6_000, loss_m=6_000, distance_km=1100.0) == "easy"

    def test_a_rolling_route_is_moderate(self) -> None:
        assert classify_difficulty(gain_m=4_000, loss_m=4_000, distance_km=200.0) == "moderate"

    def test_a_hilly_route_is_difficult(self) -> None:
        assert classify_difficulty(gain_m=7_000, loss_m=7_000, distance_km=200.0) == "difficult"

    def test_a_mountain_route_is_very_difficult(self) -> None:
        # GR 10 across the Pyrenees: ~55 m of ascent per km.
        assert (
            classify_difficulty(gain_m=60_000, loss_m=60_000, distance_km=1100.0)
            == "very_difficult"
        )

    def test_a_small_total_climb_stays_easy(self) -> None:
        assert classify_difficulty(gain_m=250, loss_m=250, distance_km=5.0) == "easy"

    def test_a_route_without_distance_is_easy(self) -> None:
        assert classify_difficulty(gain_m=1_000, loss_m=1_000, distance_km=0.0) == "easy"
