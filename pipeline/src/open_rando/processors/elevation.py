from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import LineString, MultiLineString

from open_rando.fetchers.srtm import SrtmReader
from open_rando.processors.slice import haversine_distance

ELEVATION_NOISE_THRESHOLD_METERS = 5

FLAT_SPEED_KMH = 4.0
SLOPE_THRESHOLD = 0.10  # 10%
ASCENT_RATE_METERS_PER_HOUR = 300
DESCENT_RATE_METERS_PER_HOUR = 450

# Difficulty bands, in metres of ascent per kilometre walked.
EASY_GAIN_PER_KM = 15.0
MODERATE_GAIN_PER_KM = 30.0
DIFFICULT_GAIN_PER_KM = 50.0
# Below this total ascent a route is easy whatever its steepness per km.
EASY_TOTAL_GAIN_CEILING_METERS = 300


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
    # Distances where the trail breaks between two mapped segments. The gap
    # itself is never walked, so it adds neither distance nor time.
    segment_boundaries_km: list[float] = field(default_factory=list)


def compute_trail_elevation_profile(
    trail: LineString | MultiLineString,
    reader: SrtmReader,
    sample_interval_meters: float = 50.0,
) -> ElevationProfile:
    """Profile a whole trail, segment by segment.

    A MultiLineString trail has gaps between its segments (unmapped stretches,
    ferry crossings, OSM breaks). Profiling the concatenated coordinates would
    charge the straight jump between two segments as walked distance, climb and
    time, so each segment is profiled on its own and the results are stitched.
    """
    if isinstance(trail, LineString):
        return compute_elevation_profile(trail, reader, sample_interval_meters)

    segment_profiles = [
        compute_elevation_profile(segment, reader, sample_interval_meters)
        for segment in trail.geoms
    ]
    return _stitch_profiles([profile for profile in segment_profiles if profile.distances_km])


def _stitch_profiles(profiles: list[ElevationProfile]) -> ElevationProfile:
    """Concatenate per-segment profiles without crossing the gaps between them."""
    if not profiles:
        return ElevationProfile()
    if len(profiles) == 1:
        return profiles[0]

    distances_km: list[float] = []
    elevations_m: list[float] = []
    cumulative_times_min: list[float] = []
    segment_boundaries_km: list[float] = []

    distance_offset = 0.0
    time_offset = 0.0

    for index, profile in enumerate(profiles):
        if index > 0:
            segment_boundaries_km.append(round(distance_offset, 3))

        for distance, elevation, time_minutes in zip(
            profile.distances_km,
            profile.elevations_m,
            profile.cumulative_times_min,
            strict=True,
        ):
            distances_km.append(distance + distance_offset)
            elevations_m.append(elevation)
            cumulative_times_min.append(time_minutes + time_offset)

        distance_offset += profile.distances_km[-1]
        time_offset += profile.cumulative_times_min[-1] if profile.cumulative_times_min else 0.0

    return ElevationProfile(
        distances_km=distances_km,
        elevations_m=elevations_m,
        cumulative_times_min=cumulative_times_min,
        # Summed per segment: the elevation step across a gap is not a climb.
        gain_m=sum(profile.gain_m for profile in profiles),
        loss_m=sum(profile.loss_m for profile in profiles),
        max_m=max(profile.max_m for profile in profiles),
        min_m=min(profile.min_m for profile in profiles),
        duration_minutes=int(round(cumulative_times_min[-1])) if cumulative_times_min else 0,
        segment_boundaries_km=segment_boundaries_km,
    )


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
    """Cumulative ascent and descent, with SRTM oscillation filtered out.

    Elevations are walked as monotone runs: consecutive deltas of the same sign
    accumulate, and a run is committed when the direction reverses — but only
    once it exceeds ELEVATION_NOISE_THRESHOLD_METERS. A smaller run is absorbed
    into the new direction, so sampling noise on flat ground adds nothing while
    real climbs are counted in full.
    """
    if len(elevations) < 2:
        return 0, 0

    total_gain = 0.0
    total_loss = 0.0
    run = 0.0

    for index in range(1, len(elevations)):
        delta = elevations[index] - elevations[index - 1]
        if delta == 0.0:
            continue

        same_direction = run == 0.0 or (run > 0.0) == (delta > 0.0)
        if same_direction:
            run += delta
            continue

        if abs(run) >= ELEVATION_NOISE_THRESHOLD_METERS:
            if run > 0.0:
                total_gain += run
            else:
                total_loss += -run
            run = delta
        else:
            # Too small to be real: fold it into the new direction.
            run += delta

    if run >= ELEVATION_NOISE_THRESHOLD_METERS:
        total_gain += run
    elif run <= -ELEVATION_NOISE_THRESHOLD_METERS:
        total_loss += -run

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
    """Classify hike difficulty from how steep the route is, not how long.

    Routes in the catalog run from 50km to over 2000km, so total ascent tracks
    length more than effort: a flat 1000km towpath out-climbs a short mountain
    stage. Difficulty therefore keys off ascent per kilometre, with an absolute
    floor so genuinely small climbs stay easy.
    """
    if distance_km <= 0:
        return "easy"

    if gain_m < EASY_TOTAL_GAIN_CEILING_METERS:
        return "easy"

    gain_per_km = gain_m / distance_km

    if gain_per_km < EASY_GAIN_PER_KM:
        return "easy"
    if gain_per_km < MODERATE_GAIN_PER_KM:
        return "moderate"
    if gain_per_km < DIFFICULT_GAIN_PER_KM:
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
