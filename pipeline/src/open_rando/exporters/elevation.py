from __future__ import annotations

import json
from pathlib import Path

from open_rando.processors.elevation import ElevationProfile


def export_elevation_profile(
    step_profiles: list[ElevationProfile],
    hike_id: str,
    output_directory: str,
) -> None:
    """Export combined elevation profile for all steps as a JSON file."""
    distances_km: list[float] = []
    elevations_m: list[float] = []
    times_min: list[float] = []
    step_boundaries_km: list[float] = []

    cumulative_offset_km = 0.0
    cumulative_offset_min = 0.0

    for step_index, profile in enumerate(step_profiles):
        if not profile.distances_km:
            continue

        if step_index > 0:
            step_boundaries_km.append(cumulative_offset_km)

        for distance, elevation, time_min in zip(
            profile.distances_km,
            profile.elevations_m,
            profile.cumulative_times_min,
            strict=True,
        ):
            distances_km.append(round(distance + cumulative_offset_km, 3))
            elevations_m.append(round(elevation, 1))
            times_min.append(round(time_min + cumulative_offset_min, 1))

        if profile.distances_km:
            cumulative_offset_km += profile.distances_km[-1]
        if profile.cumulative_times_min:
            cumulative_offset_min += profile.cumulative_times_min[-1]

    if not distances_km:
        return

    output_path = Path(output_directory) / f"{hike_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "distances_km": distances_km,
        "elevations_m": elevations_m,
        "times_min": times_min,
        "step_boundaries_km": step_boundaries_km,
    }

    output_path.write_text(json.dumps(data), encoding="utf-8")


def export_route_elevation(
    profile: ElevationProfile,
    route_id: str,
    output_directory: str,
) -> None:
    """Export elevation profile for a full route."""
    if not profile.distances_km:
        return

    output_path = Path(output_directory) / f"{route_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "distances_km": [round(distance, 3) for distance in profile.distances_km],
        "elevations_m": [round(elevation, 1) for elevation in profile.elevations_m],
        "times_min": [round(time, 1) for time in profile.cumulative_times_min],
    }

    output_path.write_text(json.dumps(data), encoding="utf-8")
