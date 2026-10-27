"""Local index of every boarding stop in the national GTFS feeds.

Replaces the transport.data.gouv.fr `gtfs-stops` API, which needs one call per
~28 km chunk. The `gtfs` stage fills it from the feeds themselves; the `pois`
stage queries it by bounding box.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from open_rando.config import GTFS_STOPS_INDEX_PATH
from open_rando.fetchers.gtfs import FEED_STATUS_INDEXED, FEED_STATUS_UNPARSEABLE, GtfsStop

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS feeds (
        resource_id INTEGER PRIMARY KEY,
        status TEXT NOT NULL,
        stop_count INTEGER NOT NULL,
        indexed_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS stops (
        resource_id INTEGER NOT NULL,
        stop_id TEXT NOT NULL,
        lat REAL NOT NULL,
        lon REAL NOT NULL,
        PRIMARY KEY (resource_id, stop_id)
    )""",
    "CREATE INDEX IF NOT EXISTS stops_bbox ON stops (lat, lon)",
)


def default_stops_index_path() -> Path:
    return Path(GTFS_STOPS_INDEX_PATH).expanduser()


class GtfsStopsIndex:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    @classmethod
    def open_for_writing(cls, path: Path | None = None) -> GtfsStopsIndex:
        index_path = path or default_stops_index_path()
        index_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(index_path)
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()
        return cls(connection)

    @classmethod
    def open_for_reading(cls, path: Path | None = None) -> GtfsStopsIndex | None:
        """The index, or None when the `gtfs` stage never ran."""
        index_path = path or default_stops_index_path()
        if not index_path.exists():
            return None
        connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
        return cls(connection)

    def close(self) -> None:
        self.connection.close()

    def replace_feed(self, resource_id: int, status: str, stops: list[GtfsStop]) -> None:
        """Swap a feed's stops for a fresh set, atomically."""
        with self.connection:
            self.connection.execute("DELETE FROM stops WHERE resource_id = ?", (resource_id,))
            self.connection.executemany(
                "INSERT OR REPLACE INTO stops (resource_id, stop_id, lat, lon) VALUES (?, ?, ?, ?)",
                [(stop.resource_id, stop.stop_id, stop.latitude, stop.longitude) for stop in stops],
            )
            self.connection.execute(
                "INSERT OR REPLACE INTO feeds (resource_id, status, stop_count, indexed_at) "
                "VALUES (?, ?, ?, ?)",
                (resource_id, status, len(stops), datetime.now(UTC).isoformat()),
            )

    def is_feed_fresh(self, resource_id: int, max_age_seconds: float) -> bool:
        """True when the feed was indexed (or found unparseable) recently enough."""
        row = self.connection.execute(
            "SELECT status, indexed_at FROM feeds WHERE resource_id = ?", (resource_id,)
        ).fetchone()
        if row is None or row[0] not in (FEED_STATUS_INDEXED, FEED_STATUS_UNPARSEABLE):
            return False
        indexed_at = datetime.fromisoformat(row[1])
        return datetime.now(UTC) - indexed_at < timedelta(seconds=max_age_seconds)

    def stops_in_bounding_box(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
    ) -> list[GtfsStop]:
        cursor = self.connection.execute(
            "SELECT resource_id, stop_id, lat, lon FROM stops "
            "WHERE lat >= ? AND lat <= ? AND lon >= ? AND lon <= ?",
            (south, north, west, east),
        )
        return [
            GtfsStop(
                latitude=latitude, longitude=longitude, stop_id=stop_id, resource_id=resource_id
            )
            for resource_id, stop_id, latitude, longitude in cursor
        ]

    def feed_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM feeds").fetchone()
        return int(row[0])

    def stop_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM stops").fetchone()
        return int(row[0])
