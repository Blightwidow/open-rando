from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Accommodation:
    has_hotel: bool = False  # hotel, guest_house, hostel
    has_camping: bool = False  # camp_site

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_hotel": self.has_hotel,
            "has_camping": self.has_camping,
        }


@dataclass
class ServiceWindow:
    """Rail service on one kind of day, as minutes after midnight.

    Values above 1440 mean the train runs after midnight (GTFS allows
    departure times such as "25:10:00" for a service that belongs to the
    previous service day).
    """

    first_departure_minutes: int
    last_departure_minutes: int
    departure_count: int
    # The calendar date these figures were counted on, when known.
    sample_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "first_departure_minutes": self.first_departure_minutes,
            "last_departure_minutes": self.last_departure_minutes,
            "departure_count": self.departure_count,
            "sample_date": self.sample_date,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceWindow:
        return cls(
            first_departure_minutes=int(data["first_departure_minutes"]),
            last_departure_minutes=int(data["last_departure_minutes"]),
            departure_count=int(data["departure_count"]),
            sample_date=data.get("sample_date"),
        )


@dataclass
class RailService:
    """Departures from a train station, per kind of day.

    A missing window means the GTFS feeds report no departure on that kind of
    day (station closed on Sundays, seasonal service, and so on).
    """

    weekday: ServiceWindow | None = None
    saturday: ServiceWindow | None = None
    sunday: ServiceWindow | None = None

    def has_service(self) -> bool:
        return any(window is not None for window in (self.weekday, self.saturday, self.sunday))

    def to_dict(self) -> dict[str, Any]:
        return {
            "weekday": self.weekday.to_dict() if self.weekday else None,
            "saturday": self.saturday.to_dict() if self.saturday else None,
            "sunday": self.sunday.to_dict() if self.sunday else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RailService:
        def window(key: str) -> ServiceWindow | None:
            raw = data.get(key)
            return ServiceWindow.from_dict(raw) if raw else None

        return cls(weekday=window("weekday"), saturday=window("saturday"), sunday=window("sunday"))


@dataclass
class Station:
    name: str
    code: str
    lat: float
    lon: float
    distance_to_trail_meters: float = 0.0
    transit_lines: list[str] = field(default_factory=list)
    accommodation: Accommodation = field(default_factory=Accommodation)
    transport_type: str = "train"
    connected_route_ids: set[str] = field(default_factory=set)
    rail_service: RailService | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "lat": self.lat,
            "lon": self.lon,
            "distance_to_trail_m": self.distance_to_trail_meters,
            "transit_lines": self.transit_lines,
            "accommodation": self.accommodation.to_dict(),
            "transport_type": self.transport_type,
            "rail_service": self.rail_service.to_dict() if self.rail_service else None,
        }


@dataclass
class Landmark:
    """A scenic or historical feature near the trail.

    Used to enrich the AI image prompt for a route. Persisted to the catalog
    so the `images` subcommand can rebuild prompts without rerunning the
    pipeline.
    """

    name: str
    kind: str
    lat: float
    lon: float
    elevation_m: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "lat": self.lat,
            "lon": self.lon,
            "elevation_m": self.elevation_m,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Landmark:
        return cls(
            name=str(data.get("name", "")),
            kind=str(data.get("kind", "")),
            lat=float(data["lat"]),
            lon=float(data["lon"]),
            elevation_m=data.get("elevation_m"),
        )


@dataclass
class PointOfInterest:
    """A point of interest near a trail — displayed on the map only."""

    name: str
    lat: float
    lon: float
    poi_type: str  # "hotel", "camping", "train_station", "bus_stop"
    url: str | None = None
    transit_lines: list[str] = field(default_factory=list)
    distance_km: float | None = None
    rail_service: RailService | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "poi_type": self.poi_type,
            "url": self.url or "",
            "transit_lines": self.transit_lines,
            "distance_km": self.distance_km if self.distance_km is not None else 0.0,
            "rail_service": self.rail_service.to_dict() if self.rail_service else None,
        }


@dataclass
class Route:
    """A GR route with its trail geometry and nearby points of interest."""

    identifier: str
    slug: str
    path_ref: str
    path_name: str
    description: str
    osm_relation_id: int
    pois: list[PointOfInterest]
    distance_km: float
    elevation_gain_meters: int
    elevation_loss_meters: int
    max_elevation_meters: int
    min_elevation_meters: int
    bounding_box: tuple[float, float, float, float]
    region: str
    departement: str
    difficulty: str
    is_circular_trail: bool
    terrain: list[str]
    geojson_path: str
    gpx_path: str
    last_updated: str
    landmarks: list[Landmark] = field(default_factory=list)
    image_path: str | None = None
    # A trail mapped in several pieces has gaps between them. The gaps are not
    # walked, so they are excluded from distance_km and reported separately.
    trail_segment_count: int = 1
    trail_gap_km: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "slug": self.slug,
            "path_ref": self.path_ref,
            "path_name": self.path_name,
            "description": self.description,
            "osm_relation_id": self.osm_relation_id,
            "pois": [poi.to_dict() for poi in self.pois],
            "distance_km": self.distance_km,
            "elevation_gain_m": self.elevation_gain_meters,
            "elevation_loss_m": self.elevation_loss_meters,
            "max_elevation_m": self.max_elevation_meters,
            "min_elevation_m": self.min_elevation_meters,
            "bbox": list(self.bounding_box),
            "region": self.region,
            "departement": self.departement,
            "difficulty": self.difficulty,
            "is_circular_trail": self.is_circular_trail,
            "terrain": self.terrain,
            "trail_segment_count": self.trail_segment_count,
            "trail_gap_km": self.trail_gap_km,
            "geojson_path": self.geojson_path,
            "gpx_path": self.gpx_path,
            "last_updated": self.last_updated,
            "image_path": self.image_path,
            "landmarks": [landmark.to_dict() for landmark in self.landmarks],
        }


def generate_route_id(path_ref: str, osm_relation_id: int) -> str:
    key = f"{path_ref}:{osm_relation_id}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", ascii_text.lower())
    return re.sub(r"[-\s]+", "-", cleaned).strip("-")


def slugify_sncf(station_name: str) -> str:
    """Slugify a station name for garesetconnexions.sncf URLs.

    Strips accents, lowercases, splits on non-alphanumeric chars,
    drops single-character fragments (e.g. "l" from "l'Amaury").
    """
    normalized = unicodedata.normalize("NFKD", station_name)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    words = re.split(r"[^a-z0-9]+", ascii_text)
    words = [word for word in words if len(word) > 1]
    return "-".join(words)
