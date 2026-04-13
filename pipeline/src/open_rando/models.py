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
        }


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

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "lat": self.lat,
            "lon": self.lon,
            "poi_type": self.poi_type,
        }
        if self.url:
            result["url"] = self.url
        if self.transit_lines:
            result["transit_lines"] = self.transit_lines
        if self.distance_km is not None:
            result["distance_km"] = self.distance_km
        return result


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
            "geojson_path": self.geojson_path,
            "gpx_path": self.gpx_path,
            "last_updated": self.last_updated,
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
