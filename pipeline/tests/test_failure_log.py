from __future__ import annotations

from pathlib import Path

from open_rando.exporters.failures import (
    build_failure_entry,
    export_failure_log,
    load_failure_log,
)

FIRST_FAILURE_AT = "2026-10-19T00:00:00+00:00"
SECOND_FAILURE_AT = "2026-10-20T00:00:00+00:00"


def raise_and_capture(error: Exception) -> Exception:
    try:
        raise error
    except Exception as captured:
        return captured


class TestBuildFailureEntry:
    def test_records_error_type(self) -> None:
        entry = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError("The read operation timed out")),
            failed_at=FIRST_FAILURE_AT,
        )
        assert entry["error_type"] == "TimeoutError"

    def test_records_traceback(self) -> None:
        entry = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError("The read operation timed out")),
            failed_at=FIRST_FAILURE_AT,
        )
        assert "TimeoutError: The read operation timed out" in entry["traceback"]

    def test_first_failure_counts_one_attempt(self) -> None:
        entry = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError()),
            failed_at=FIRST_FAILURE_AT,
        )
        assert entry["attempts"] == 1

    def test_repeated_failure_increments_attempts(self) -> None:
        first = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError()),
            failed_at=FIRST_FAILURE_AT,
        )
        second = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError()),
            previous_entry=first,
            failed_at=SECOND_FAILURE_AT,
        )
        assert second["attempts"] == 2

    def test_repeated_failure_keeps_first_failure_date(self) -> None:
        first = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError()),
            failed_at=FIRST_FAILURE_AT,
        )
        second = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError()),
            previous_entry=first,
            failed_at=SECOND_FAILURE_AT,
        )
        assert second["first_failed_at"] == FIRST_FAILURE_AT


class TestFailureLogPersistence:
    def test_round_trips_entries_by_ref(self, tmp_path: Path) -> None:
        log_path = str(tmp_path / "failed-routes.json")
        entry = build_failure_entry(
            route_ref="GR 13",
            relation_ids=[111],
            error=raise_and_capture(TimeoutError()),
            failed_at=FIRST_FAILURE_AT,
        )
        export_failure_log({"GR 13": entry}, log_path)
        assert load_failure_log(log_path) == {"GR 13": entry}

    def test_missing_file_loads_empty(self, tmp_path: Path) -> None:
        assert load_failure_log(str(tmp_path / "absent.json")) == {}

    def test_corrupt_file_loads_empty(self, tmp_path: Path) -> None:
        log_path = tmp_path / "failed-routes.json"
        log_path.write_text("{not json", encoding="utf-8")
        assert load_failure_log(str(log_path)) == {}
