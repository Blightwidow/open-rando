from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from open_rando.fetchers import gtfs
from open_rando.fetchers.gtfs import (
    DAY_TYPE_SATURDAY,
    DAY_TYPE_SUNDAY,
    DAY_TYPE_WEEKDAY,
    GtfsStop,
    build_rail_service,
    parse_gtfs_zip,
)
from open_rando.models import ServiceWindow

# Sampled dates start from that week: Wednesdays 06-03, 06-10, 06-17, 06-24;
# Saturdays 06-06, 06-13, 06-20, 06-27; Sundays 06-07, 06-14, 06-21, 06-28.
REFERENCE_DATE = date(2026, 6, 1)  # a Monday


def build_gtfs_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_file:
        for name, content in files.items():
            zip_file.writestr(name, content)
    return buffer.getvalue()


def gtfs_stop(stop_id: str) -> GtfsStop:
    return GtfsStop(latitude=48.0, longitude=2.0, stop_id=stop_id, resource_id=1)


WEEKLY_CALENDAR = (
    "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
    "WEEK,1,1,1,1,1,0,0,20260101,20261231\n"
    "WEEKEND,0,0,0,0,0,1,1,20260101,20261231\n"
)

TRIPS = (
    "trip_id,route_id,service_id\n"
    "trip-week-1,route-A,WEEK\n"
    "trip-week-2,route-A,WEEK\n"
    "trip-weekend-1,route-A,WEEKEND\n"
)

STOP_TIMES = (
    "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
    "trip-week-1,gare-nord,05:40:00,05:42:00,1\n"
    "trip-week-2,gare-nord,22:10:00,22:15:00,1\n"
    "trip-weekend-1,gare-nord,09:00:00,09:05:00,1\n"
)

ROUTES = (
    "route_id,route_short_name,route_long_name,route_type\n"
    "route-A,TER 12,Paris - Melun,2\n"
    "route-BUS,Bus 7,Melun - Fontainebleau,3\n"
)


class TestParseGtfsZipDepartures:
    def test_aggregates_weekday_departures(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": TRIPS,
                    "stop_times.txt": STOP_TIMES,
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        weekday = feed.departures["gare-nord"][DAY_TYPE_WEEKDAY]
        assert weekday.first_departure_minutes == 5 * 60 + 42
        assert weekday.last_departure_minutes == 22 * 60 + 15
        assert weekday.departure_count == 2

    def test_separates_saturday_from_sunday(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": TRIPS,
                    "stop_times.txt": STOP_TIMES,
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        windows = feed.departures["gare-nord"]
        assert windows[DAY_TYPE_SATURDAY].departure_count == 1
        assert windows[DAY_TYPE_SUNDAY].first_departure_minutes == 9 * 60 + 5

    def test_keeps_after_midnight_times_beyond_24h(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": "trip_id,route_id,service_id\ntrip-late,route-A,WEEK\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-late,gare-nord,24:50:00,25:10:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures["gare-nord"][DAY_TYPE_WEEKDAY].last_departure_minutes == 25 * 60 + 10

    def test_ignores_services_that_ended_before_the_sampled_dates(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": (
                        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
                        "start_date,end_date\n"
                        "OLD,1,1,1,1,1,0,0,20250101,20251231\n"
                    ),
                    "trips.txt": "trip_id,route_id,service_id\ntrip-old,route-A,OLD\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-old,gare-nord,08:00:00,08:05:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures == {}

    def test_reads_feeds_built_only_from_calendar_dates(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar_dates.txt": (
                        "service_id,date,exception_type\n"
                        "SUMMER,20260606,1\n"  # a sampled Saturday
                        "SUMMER,20260601,1\n"  # a Monday, never sampled
                    ),
                    "trips.txt": "trip_id,route_id,service_id\ntrip-summer,route-A,SUMMER\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-summer,gare-nord,07:30:00,07:35:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        windows = feed.departures["gare-nord"]
        assert list(windows) == [DAY_TYPE_SATURDAY]
        assert windows[DAY_TYPE_SATURDAY].first_departure_minutes == 7 * 60 + 35

    def test_skips_rows_without_a_departure_time(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": "trip_id,route_id,service_id\ntrip-week-1,route-A,WEEK\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-week-1,gare-nord,08:00:00,,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures == {}

    def test_still_builds_route_connectivity(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": TRIPS,
                    "stop_times.txt": STOP_TIMES,
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.connectivity["gare-nord"] == {"route-A"}
        assert feed.route_names["route-A"] == "TER 12"

    def test_counts_only_rail_departures(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": (
                        "trip_id,route_id,service_id\n"
                        "trip-train,route-A,WEEK\n"
                        "trip-bus-1,route-BUS,WEEK\n"
                        "trip-bus-2,route-BUS,WEEK\n"
                    ),
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-train,gare-nord,06:00:00,06:05:00,1\n"
                        "trip-bus-1,gare-nord,07:00:00,07:05:00,1\n"
                        "trip-bus-2,gare-nord,23:00:00,23:05:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        weekday = feed.departures["gare-nord"][DAY_TYPE_WEEKDAY]
        assert weekday.departure_count == 1
        assert weekday.last_departure_minutes == 6 * 60 + 5
        # The bus route still shows up as connectivity for bus stop naming.
        assert feed.connectivity["gare-nord"] == {"route-A", "route-BUS"}

    def test_counts_a_trip_once_per_sampled_day(self) -> None:
        """Two calendars covering the same Wednesday must not double-count."""
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": (
                        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
                        "start_date,end_date\n"
                        "WEEK-A,1,1,1,1,1,0,0,20260101,20261231\n"
                        "WEEK-B,1,1,1,1,1,0,0,20260101,20261231\n"
                    ),
                    "trips.txt": (
                        "trip_id,route_id,service_id\n"
                        "trip-a,route-A,WEEK-A\n"
                        "trip-b,route-A,WEEK-B\n"
                    ),
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-a,gare-nord,06:00:00,06:05:00,1\n"
                        "trip-b,gare-nord,07:00:00,07:05:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures["gare-nord"][DAY_TYPE_WEEKDAY].departure_count == 2

    def test_skips_a_cancelled_date_and_samples_the_next_one(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "calendar_dates.txt": ("service_id,date,exception_type\nWEEK,20260603,2\n"),
                    "trips.txt": "trip_id,route_id,service_id\ntrip-week-1,route-A,WEEK\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-week-1,gare-nord,06:00:00,06:05:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures["gare-nord"][DAY_TYPE_WEEKDAY].sample_date == "2026-06-10"

    def test_finds_service_that_only_resumes_in_a_later_week(self) -> None:
        """A line closed for works this week still reports its normal timetable."""
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": (
                        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
                        "start_date,end_date\n"
                        "AUTUMN,1,1,1,1,1,0,0,20260615,20261231\n"
                    ),
                    "trips.txt": "trip_id,route_id,service_id\ntrip-autumn,route-A,AUTUMN\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-autumn,gare-nord,06:00:00,06:05:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures["gare-nord"][DAY_TYPE_WEEKDAY].sample_date == "2026-06-17"

    def test_keeps_the_busiest_sampled_date(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": (
                        "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
                        "start_date,end_date\n"
                        "EVERY-WEDNESDAY,0,0,1,0,0,0,0,20260101,20261231\n"
                    ),
                    "calendar_dates.txt": ("service_id,date,exception_type\nEXTRA,20260610,1\n"),
                    "trips.txt": (
                        "trip_id,route_id,service_id\n"
                        "trip-regular,route-A,EVERY-WEDNESDAY\n"
                        "trip-extra,route-A,EXTRA\n"
                    ),
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-regular,gare-nord,06:00:00,06:05:00,1\n"
                        "trip-extra,gare-nord,20:00:00,20:05:00,1\n"
                    ),
                    "routes.txt": ROUTES,
                }
            ),
            REFERENCE_DATE,
        )

        weekday = feed.departures["gare-nord"][DAY_TYPE_WEEKDAY]
        assert weekday.sample_date == "2026-06-10"
        assert weekday.departure_count == 2
        assert weekday.last_departure_minutes == 20 * 60 + 5

    def test_skips_departures_when_routes_txt_is_missing(self) -> None:
        feed = parse_gtfs_zip(
            build_gtfs_zip(
                {
                    "calendar.txt": WEEKLY_CALENDAR,
                    "trips.txt": "trip_id,route_id,service_id\ntrip-week-1,route-A,WEEK\n",
                    "stop_times.txt": (
                        "trip_id,stop_id,arrival_time,departure_time,stop_sequence\n"
                        "trip-week-1,gare-nord,06:00:00,06:05:00,1\n"
                    ),
                }
            ),
            REFERENCE_DATE,
        )

        assert feed.departures == {}
        assert feed.connectivity["gare-nord"] == {"route-A"}


class TestBuildRailService:
    def test_merges_windows_across_platform_stops(self) -> None:
        departures = {
            "platform-1": {
                DAY_TYPE_WEEKDAY: ServiceWindow(
                    first_departure_minutes=400,
                    last_departure_minutes=1200,
                    departure_count=10,
                )
            },
            "platform-2": {
                DAY_TYPE_WEEKDAY: ServiceWindow(
                    first_departure_minutes=350,
                    last_departure_minutes=1300,
                    departure_count=5,
                )
            },
        }

        rail_service = build_rail_service(
            [gtfs_stop("platform-1"), gtfs_stop("platform-2")], departures
        )

        assert rail_service is not None
        assert rail_service.weekday == ServiceWindow(
            first_departure_minutes=350,
            last_departure_minutes=1300,
            departure_count=15,
        )

    def test_returns_none_without_any_departure(self) -> None:
        assert build_rail_service([gtfs_stop("unknown")], {}) is None

    def test_leaves_days_without_service_empty(self) -> None:
        departures = {
            "platform-1": {
                DAY_TYPE_SATURDAY: ServiceWindow(
                    first_departure_minutes=500,
                    last_departure_minutes=1100,
                    departure_count=4,
                )
            }
        }

        rail_service = build_rail_service([gtfs_stop("platform-1")], departures)

        assert rail_service is not None
        assert rail_service.weekday is None
        assert rail_service.sunday is None
        assert rail_service.saturday is not None


class TestFetchFeedData:
    def test_caches_an_unparseable_feed_so_it_is_downloaded_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gtfs, "GTFS_FEEDS_CACHE_DIRECTORY", str(tmp_path))
        download_count = 0

        class FakeResponse:
            content = b"not a zip"

            def raise_for_status(self) -> None:
                return None

        def fake_get(*_args: object, **_kwargs: object) -> FakeResponse:
            nonlocal download_count
            download_count += 1
            return FakeResponse()

        monkeypatch.setattr(gtfs.requests, "get", fake_get)

        for _ in range(2):
            feed = gtfs._fetch_feed_data(84073, "https://example.invalid/feed", REFERENCE_DATE)
            assert feed.departures == {}
            assert feed.connectivity == {}

        assert download_count == 1

    def test_does_not_cache_a_failed_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(gtfs, "GTFS_FEEDS_CACHE_DIRECTORY", str(tmp_path))
        download_count = 0

        def fake_get(*_args: object, **_kwargs: object) -> object:
            nonlocal download_count
            download_count += 1
            raise gtfs.requests.RequestException("network down")

        monkeypatch.setattr(gtfs.requests, "get", fake_get)

        for _ in range(2):
            assert gtfs._fetch_feed_data(1, "https://example.invalid/feed", REFERENCE_DATE) == (
                gtfs.FeedData()
            )

        assert download_count == 2
