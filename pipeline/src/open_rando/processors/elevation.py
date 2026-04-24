from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import LineString

from open_rando.fetchers.srtm import SrtmReader
from open_rando.processors.slice import haversine_distance

ELEVATION_NOISE_THRESHOLD_METERS = 5

FLAT_SPEED_KMH = 4.0
SLOPE_THRESHOLD = 0.10  # 10%
ASCENT_RATE_METERS_PER_HOUR = 300
DESCENT_RATE_METERS_PER_HOUR = 450


@dataclass
class ElevationProfile:
    distances_km: list[float] = field(default_factory=list)
    elevations_m: list[float] = field(default_factory=list)
    cumulative_times_min: list[float] = field(default_factory=list)
    gain_m: int = 0
    loss_m: int = 0
    max_m: int = 0
    min_m: int = 0
    duration_minutes: int = 0


def compute_elevation_profile(
    geometry: LineString,
    reader: SrtmReader,
    sample_interval_meters: float = 50.0,
) -> ElevationProfile:
    """Sample elevation along a LineString every sample_interval_meters."""
    coords = list(geometry.coords)
    if len(coords) < 2:
        return ElevationProfile()

    sample_distances: list[float] = []
    sample_elevations: list[float] = []

    cumulative_meters = 0.0
    next_sample_meters = 0.0

    for index in range(len(coords)):
        longitude, latitude = coords[index]

        if index > 0:
            previous_longitude, previous_latitude = coords[index - 1]
            segment_meters = haversine_distance(
                previous_latitude, previous_longitude, latitude, longitude
            )

            # Interpolate samples along this segment
            while next_sample_meters <= cumulative_meters + segment_meters:
                if segment_meters > 0:
                    fraction = (next_sample_meters - cumulative_meters) / segment_meters
                else:
                    fraction = 0.0
                interpolated_latitude = (
                    previous_latitude + (latitude - previous_latitude) * fraction
                )
                interpolated_longitude = (
                    previous_longitude + (longitude - previous_longitude) * fraction
                )
                elevation = reader.get_elevation(interpolated_latitude, interpolated_longitude)
                if elevation is not None:
                    sample_distances.append(next_sample_meters / 1000.0)
                    sample_elevations.append(elevation)
                next_sample_meters += sample_interval_meters

            cumulative_meters += segment_meters

    # Always include the last point
    last_longitude, last_latitude = coords[-1]
    last_elevation = reader.get_elevation(last_latitude, last_longitude)
    if last_elevation is not None and (
        not sample_distances or sample_distances[-1] < cumulative_meters / 1000.0 - 0.001
    ):
        sample_distances.append(cumulative_meters / 1000.0)
        sample_elevations.append(last_elevation)

    if not sample_elevations:
        return ElevationProfile()

    gain_m, loss_m = _compute_gain_loss(sample_elevations)
    max_m = int(round(max(sample_elevations)))
    min_m = int(round(min(sample_elevations)))
    cumulative_times = _compute_cumulative_times(sample_distances, sample_elevations)
    duration_minutes = int(round(cumulative_times[-1])) if cumulative_times else 0

    return ElevationProfile(
        distances_km=sample_distances,
        elevations_m=sample_elevations,
        cumulative_times_min=cumulative_times,
        gain_m=gain_m,
        loss_m=loss_m,
        max_m=max_m,
        min_m=min_m,
        duration_minutes=duration_minutes,
    )


def _compute_gain_loss(elevations: list[float]) -> tuple[int, int]:
    """Compute gain/loss with noise threshold to filter SRTM oscillations."""
    if len(elevations) < 2:
        return 0, 0

    total_gain = 0.0
    total_loss = 0.0
    pending = 0.0

    for index in range(1, len(elevations)):
        delta = elevations[index] - elevations[index - 1]
        new_pending = pending + delta

        # Direction change or threshold crossed
        if pending >= 0 and new_pending < 0:
            if pending >= ELEVATION_NOISE_THRESHOLD_METERS:
                total_gain += pending
            pending = delta
        elif pending <= 0 and new_pending > 0:
            if abs(pending) >= ELEVATION_NOISE_THRESHOLD_METERS:
                total_loss += abs(pending)
            pending = delta
        else:
            pending = new_pending

    # Flush remaining
    if pending >= ELEVATION_NOISE_THRESHOLD_METERS:
        total_gain += pending
    elif abs(pending) >= ELEVATION_NOISE_THRESHOLD_METERS:
        total_loss += abs(pending)

    return int(round(total_gain)), int(round(total_loss))


def _compute_cumulative_times(
    distances_km: list[float],
    elevations_m: list[float],
) -> list[float]:
    """Compute cumulative walking time at each sample point.

    Rules:
    - Flat (slope < 10%): 4 km/h
    - Uphill (slope >= 10%): 300m ascent per hour
    - Downhill (slope >= 10%): 450m descent per hour
    """
    if len(distances_km) < 2:
        return [0.0] if distances_km else []

    cumulative_times: list[float] = [0.0]

    for index in range(1, len(distances_km)):
        horizontal_km = distances_km[index] - distances_km[index - 1]
        elevation_delta = elevations_m[index] - elevations_m[index - 1]
        horizontal_meters = horizontal_km * 1000.0

        slope = abs(elevation_delta) / horizontal_meters if horizontal_meters > 0 else 0.0

        if slope >= SLOPE_THRESHOLD and elevation_delta > 0:
            segment_hours = elevation_delta / ASCENT_RATE_METERS_PER_HOUR
        elif slope >= SLOPE_THRESHOLD and elevation_delta < 0:
            segment_hours = abs(elevation_delta) / DESCENT_RATE_METERS_PER_HOUR
        else:
            segment_hours = horizontal_km / FLAT_SPEED_KMH

        cumulative_times.append(cumulative_times[-1] + segment_hours * 60.0)

    return cumulative_times


def estimate_duration(distance_km: float, elevation_gain_m: int) -> int:
    """Fallback duration estimate when no profile is available. Returns minutes."""
    flat_minutes = distance_km / FLAT_SPEED_KMH * 60.0
    ascent_minutes = elevation_gain_m / ASCENT_RATE_METERS_PER_HOUR * 60.0
    return int(round(flat_minutes + ascent_minutes))


def classify_difficulty(gain_m: int, loss_m: int, distance_km: float) -> str:
    """Classify hike difficulty based on elevation gain per km and total gain."""
    if distance_km <= 0:
        return "easy"

    gain_per_km = gain_m / distance_km

    if gain_m < 500 and gain_per_km < 30:
        return "easy"
    if gain_m < 1000 and gain_per_km < 50:
        return "moderate"
    if gain_m < 1500 and gain_per_km < 70:
        return "difficult"
    return "very_difficult"


def elevations_for_geometry(
    geometry: LineString,
    reader: SrtmReader,
) -> list[float | None]:
    """Return elevation at each vertex of the geometry (for GPX export)."""
    result: list[float | None] = []
    for longitude, latitude in geometry.coords:
        result.append(reader.get_elevation(latitude, longitude))
    return result
