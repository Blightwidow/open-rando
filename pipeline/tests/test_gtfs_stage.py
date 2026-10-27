from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from open_rando.fetchers import gtfs
from open_rando.fetchers.gtfs import (
    FEED_STATUS_DOWNLOAD_FAILED,
    FEED_STATUS_INDEXED,
    FEED_STATUS_UNPARSEABLE,
    GtfsStop,
    fetch_gtfs_feed_data,
    index_feed,
    parse_gtfs_stops,
)
from open_rando.fetchers.gtfs_stops_index import GtfsStopsIndex

REFERENCE_DATE = date(2026, 6, 1)

STOPS_TXT = (
    "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
    "A,Boarding,45.0,5.0,0\n"
    "B,Default type,45.1,5.1,\n"
    "STATION,Station,45.2,5.2,1\n"
    "BAD,No coordinates,,,0\n"
    "ZERO,Null island,0,0,0\n"
)
MINIMAL_FEED = {
    "stops.txt": STOPS_TXT,
    "routes.txt": "route_id,route_short_name,route_type\nR1,12,3\n",
    "trips.txt": "route_id,service_id,trip_id\nR1,S,T1\n",
    "stop_times.txt": "trip_id,stop_id,departure_time,stop_sequence\nT1,A,08:00:00,1\n",
    "calendar.txt": (
        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
        "start_date,end_date\nS,1,1,1,1,1,0,0,20260101,20261231\n"
    ),
}


def build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name, content in files.items():
            zip_file.writestr(name, content)
    return buffer.getvalue()


@pytest.fixture
def feed_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(gtfs, "GTFS_FEEDS_CACHE_DIRECTORY", str(tmp_path / "feeds"))
    monkeypatch.setattr(gtfs, "GTFS_CACHE_DIRECTORY", str(tmp_path))
    return tmp_path


class TestParseStops:
    def test_keeps_boarding_stops_only(self):
        stops = parse_gtfs_stops(build_zip(MINIMAL_FEED), resource_id=7)

        assert [stop.stop_id for stop in stops] == ["A", "B"]

    def test_stop_carries_coordinates_and_resource(self):
        stop = parse_gtfs_stops(build_zip(MINIMAL_FEED), resource_id=7)[0]

        assert stop == GtfsStop(latitude=45.0, longitude=5.0, stop_id="A", resource_id=7)

    def test_zip_without_stops_table_raises(self):
        with pytest.raises(KeyError):
            parse_gtfs_stops(build_zip({"routes.txt": "route_id\n"}), resource_id=1)


class TestIndexFeed:
    def test_indexes_stops_and_caches_feed_data(
        self, feed_cache: Path, monkeypatch: pytest.MonkeyPatch
    ):
        downloads: list[int] = []

        def fake_download(resource_id: int, _url: str) -> bytes:
            downloads.append(resource_id)
            return build_zip(MINIMAL_FEED)

        monkeypatch.setattr(gtfs, "_download_feed", fake_download)

        result = index_feed(5, "https://example.test/feed.zip", REFERENCE_DATE)
        feed_data = fetch_gtfs_feed_data({5}, {5: "https://example.test/feed.zip"}, REFERENCE_DATE)

        assert result.status == FEED_STATUS_INDEXED
        assert feed_data.connectivity == {"A": {"R1"}}
        assert downloads == [5]  # the second read came from the cache

    def test_failed_download_is_reported_not_cached(
        self, feed_cache: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(gtfs, "_download_feed", lambda _resource_id, _url: None)

        result = index_feed(5, "https://example.test/feed.zip", REFERENCE_DATE)

        assert result.status == FEED_STATUS_DOWNLOAD_FAILED
        assert result.stops == []

    def test_corrupt_archive_is_unparseable(
        self, feed_cache: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(gtfs, "_download_feed", lambda _resource_id, _url: b"not a zip")

        result = index_feed(5, "https://example.test/feed.zip", REFERENCE_DATE)

        assert result.status == FEED_STATUS_UNPARSEABLE

    def test_feed_missing_departure_tables_still_yields_stops(
        self, feed_cache: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            gtfs, "_download_feed", lambda _resource_id, _url: build_zip({"stops.txt": STOPS_TXT})
        )

        result = index_feed(5, "https://example.test/feed.zip", REFERENCE_DATE)

        assert result.status == FEED_STATUS_INDEXED
        assert len(result.stops) == 2


class TestStopsIndex:
    def _open(self, tmp_path: Path) -> GtfsStopsIndex:
        return GtfsStopsIndex.open_for_writing(tmp_path / "stops.sqlite")

    def test_query_returns_stops_inside_the_box(self, tmp_path: Path):
        index = self._open(tmp_path)
        index.replace_feed(
            1,
            FEED_STATUS_INDEXED,
            [
                GtfsStop(latitude=45.0, longitude=5.0, stop_id="in", resource_id=1),
                GtfsStop(latitude=50.0, longitude=5.0, stop_id="out", resource_id=1),
            ],
        )

        found = index.stops_in_bounding_box(44.5, 4.5, 45.5, 5.5)

        assert [stop.stop_id for stop in found] == ["in"]

    def test_replacing_a_feed_drops_its_old_stops(self, tmp_path: Path):
        index = self._open(tmp_path)
        old = GtfsStop(latitude=45.0, longitude=5.0, stop_id="old", resource_id=1)
        new = GtfsStop(latitude=45.0, longitude=5.0, stop_id="new", resource_id=1)
        index.replace_feed(1, FEED_STATUS_INDEXED, [old])

        index.replace_feed(1, FEED_STATUS_INDEXED, [new])

        assert [stop.stop_id for stop in index.stops_in_bounding_box(44, 4, 46, 6)] == ["new"]

    def test_same_stop_id_in_two_feeds_is_kept_twice(self, tmp_path: Path):
        index = self._open(tmp_path)
        for resource_id in (1, 2):
            index.replace_feed(
                resource_id,
                FEED_STATUS_INDEXED,
                [GtfsStop(latitude=45.0, longitude=5.0, stop_id="S", resource_id=resource_id)],
            )

        assert index.stop_count() == 2

    def test_recent_feed_is_fresh_and_unknown_feed_is_not(self, tmp_path: Path):
        index = self._open(tmp_path)
        index.replace_feed(1, FEED_STATUS_INDEXED, [])

        assert index.is_feed_fresh(1, max_age_seconds=3600)
        assert not index.is_feed_fresh(2, max_age_seconds=3600)

    def test_missing_index_opens_as_none(self, tmp_path: Path):
        assert GtfsStopsIndex.open_for_reading(tmp_path / "absent.sqlite") is None
