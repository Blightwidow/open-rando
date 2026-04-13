"""Tests for nearest-station filtering of matched stations."""

from shapely.geometry import LineString

from open_rando.models import Station
from open_rando.processors.match import MatchedStation, _filter_never_closest_stations


def _make_station(
    name: str,
    lon: float,
    lat: float,
    distance_meters: float,
    fraction: float,
) -> MatchedStation:
    station = Station(name=name, code=name, lat=lat, lon=lon)
    station.distance_to_trail_meters = distance_meters
    return (station, fraction, (lon, lat))


# Dense trail running west-to-east along lat=48.0, from lon=1.0 to lon=3.0
# One vertex every 0.01 degrees (~700m) so stations nearby always have a close vertex.
TRAIL = LineString([(1.0 + index * 0.01, 48.0) for index in range(201)])


class TestFilterNeverClosestStations:
    def test_empty_list(self) -> None:
        assert _filter_never_closest_stations([], TRAIL) == []

    def test_single_station_kept(self) -> None:
        candidates = [_make_station("A", 2.0, 48.01, 1000.0, 0.5)]
        result = _filter_never_closest_stations(candidates, TRAIL)
        assert len(result) == 1

    def test_far_station_removed_when_closer_exists_nearby(self) -> None:
        close = _make_station("Close", 2.0, 48.005, 500.0, 0.5)
        far = _make_station("Far", 2.01, 48.04, 4400.0, 0.505)
        result = _filter_never_closest_stations([close, far], TRAIL)
        names = [matched[0].name for matched in result]
        assert "Close" in names
        assert "Far" not in names

    def test_stations_at_different_trail_sections_both_kept(self) -> None:
        west = _make_station("West", 1.2, 48.005, 550.0, 0.1)
        east = _make_station("East", 2.8, 48.005, 550.0, 0.9)
        result = _filter_never_closest_stations([west, east], TRAIL)
        assert len(result) == 2

    def test_station_beyond_radius_of_all_trail_points_removed(self) -> None:
        close = _make_station("Close", 2.0, 48.005, 500.0, 0.5)
        far = _make_station("Far", 2.0, 48.10, 11000.0, 0.5)
        result = _filter_never_closest_stations([close, far], TRAIL)
        names = [matched[0].name for matched in result]
        assert "Close" in names
        assert len(result) == 1

    def test_three_stations_middle_one_never_closest(self) -> None:
        # West and east are very close to the trail and bracket middle,
        # so middle (0.04 degrees off trail) is never the closest
        west = _make_station("West", 1.48, 48.002, 220.0, 0.24)
        middle = _make_station("Middle", 1.5, 48.04, 4400.0, 0.25)
        east = _make_station("East", 1.52, 48.002, 220.0, 0.26)
        result = _filter_never_closest_stations([west, middle, east], TRAIL)
        names = [matched[0].name for matched in result]
        assert "West" in names
        assert "East" in names
        assert "Middle" not in names
