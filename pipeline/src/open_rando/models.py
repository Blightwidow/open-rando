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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "lat": self.lat,
            "lon": self.lon,
            "distance_to_trail_m": self.distance_to_trail_meters,
            "transit_lines": self.transit_lines,
            "accommodation": self.accommodation.to_dict(),
        }


@dataclass
class HikeStep:
    start_station: Station
    end_station: Station
    distance_km: float
    estimated_duration_minutes: int
    elevation_gain_meters: int = 0
    elevation_loss_meters: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_station": self.start_station.to_dict(),
            "end_station": self.end_station.to_dict(),
            "distance_km": self.distance_km,
            "estimated_duration_min": self.estimated_duration_minutes,
            "elevation_gain_m": self.elevation_gain_meters,
            "elevation_loss_m": self.elevation_loss_meters,
        }


@dataclass
class Hike:
    identifier: str
    slug: str
    path_ref: str
    path_name: str
    osm_relation_id: int
    start_station: Station
    end_station: Station
    steps: list[HikeStep]
    distance_km: float
    estimated_duration_minutes: int
    elevation_gain_meters: int
    elevation_loss_meters: int
    max_elevation_meters: int
    min_elevation_meters: int
    difficulty: str
    bounding_box: tuple[float, float, float, float]
    region: str
    departement: str
    gpx_path: str
    geojson_path: str
    is_reversible: bool
    last_updated: str
    route_type: str = "gr"
    is_circular_trail: bool = False
    is_round_trip: bool = False

    @property
    def is_grp(self) -> bool:
        return self.route_type == "grp"

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.identifier,
            "slug": self.slug,
            "path_ref": self.path_ref,
            "path_name": self.path_name,
            "osm_relation_id": self.osm_relation_id,
            "start_station": self.start_station.to_dict(),
            "end_station": self.end_station.to_dict(),
            "steps": [step.to_dict() for step in self.steps],
            "step_count": self.step_count,
            "distance_km": self.distance_km,
            "estimated_duration_min": self.estimated_duration_minutes,
            "elevation_gain_m": self.elevation_gain_meters,
            "elevation_loss_m": self.elevation_loss_meters,
            "max_elevation_m": self.max_elevation_meters,
            "min_elevation_m": self.min_elevation_meters,
            "difficulty": self.difficulty,
            "bbox": list(self.bounding_box),
            "region": self.region,
            "departement": self.departement,
            "gpx_path": self.gpx_path,
            "geojson_path": self.geojson_path,
            "is_reversible": self.is_reversible,
            "route_type": self.route_type,
            "is_grp": self.is_grp,
            "is_circular_trail": self.is_circular_trail,
            "is_round_trip": self.is_round_trip,
            "last_updated": self.last_updated,
        }


def generate_hike_id(path_ref: str, start_name: str, end_name: str) -> str:
    key = f"{path_ref}:{start_name}:{end_name}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def determine_route_type(ref: str) -> str:
    upper = ref.upper()
    if upper.startswith("PR") and not upper.startswith("PRA"):
        return "pr"
    if "GRP" in upper or "PAYS" in upper:
        return "grp"
    return "gr"


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^\w\s-]", "", ascii_text.lower())
    return re.sub(r"[-\s]+", "-", cleaned).strip("-")
