from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("open_rando")

# A route losing more than this share of its length or climb is reported as a
# regression: OSM relations get vandalised, split, or partially deleted, and a
# silent shrink is indistinguishable from a successful run otherwise.
DISTANCE_DROP_WARNING_RATIO = 0.10
ELEVATION_DROP_WARNING_RATIO = 0.20
# A trail splitting into more pieces means ways went missing from the relation.
GAP_GROWTH_WARNING_KM = 1.0


@dataclass
class RouteDelta:
    """What changed for one route between two pipeline runs."""

    path_ref: str
    route_id: str
    distance_km_before: float
    distance_km_after: float
    train_stations_before: int
    train_stations_after: int
    bus_stops_before: int
    bus_stops_after: int
    accommodation_before: int
    accommodation_after: int
    elevation_gain_before: int
    elevation_gain_after: int
    rail_service_before: int
    rail_service_after: int
    trail_gap_km_before: float
    trail_gap_km_after: float
    warnings: list[str] = field(default_factory=list)

    def has_changes(self) -> bool:
        return (
            self.distance_km_before != self.distance_km_after
            or self.train_stations_before != self.train_stations_after
            or self.bus_stops_before != self.bus_stops_after
            or self.accommodation_before != self.accommodation_after
            or self.elevation_gain_before != self.elevation_gain_after
            or self.rail_service_before != self.rail_service_after
            or self.trail_gap_km_before != self.trail_gap_km_after
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_ref": self.path_ref,
            "route_id": self.route_id,
            "distance_km": {"before": self.distance_km_before, "after": self.distance_km_after},
            "train_stations": {
                "before": self.train_stations_before,
                "after": self.train_stations_after,
            },
            "bus_stops": {"before": self.bus_stops_before, "after": self.bus_stops_after},
            "accommodation": {
                "before": self.accommodation_before,
                "after": self.accommodation_after,
            },
            "elevation_gain_m": {
                "before": self.elevation_gain_before,
                "after": self.elevation_gain_after,
            },
            "stations_with_rail_service": {
                "before": self.rail_service_before,
                "after": self.rail_service_after,
            },
            "trail_gap_km": {
                "before": self.trail_gap_km_before,
                "after": self.trail_gap_km_after,
            },
            "warnings": self.warnings,
        }


def _count_pois(route: dict[str, Any], poi_type: str) -> int:
    return sum(1 for poi in route.get("pois", []) if poi.get("poi_type") == poi_type)


def _count_rail_service(route: dict[str, Any]) -> int:
    return sum(
        1
        for poi in route.get("pois", [])
        if poi.get("poi_type") == "train_station" and poi.get("rail_service")
    )


def _accommodation_count(route: dict[str, Any]) -> int:
    return _count_pois(route, "hotel") + _count_pois(route, "camping")


def _build_route_delta(before: dict[str, Any], after: dict[str, Any]) -> RouteDelta:
    delta = RouteDelta(
        path_ref=str(after.get("path_ref", "")),
        route_id=str(after.get("id", "")),
        distance_km_before=float(before.get("distance_km", 0.0)),
        distance_km_after=float(after.get("distance_km", 0.0)),
        train_stations_before=_count_pois(before, "train_station"),
        train_stations_after=_count_pois(after, "train_station"),
        bus_stops_before=_count_pois(before, "bus_stop"),
        bus_stops_after=_count_pois(after, "bus_stop"),
        accommodation_before=_accommodation_count(before),
        accommodation_after=_accommodation_count(after),
        elevation_gain_before=int(before.get("elevation_gain_m", 0)),
        elevation_gain_after=int(after.get("elevation_gain_m", 0)),
        rail_service_before=_count_rail_service(before),
        rail_service_after=_count_rail_service(after),
        trail_gap_km_before=float(before.get("trail_gap_km", 0.0)),
        trail_gap_km_after=float(after.get("trail_gap_km", 0.0)),
    )

    if delta.distance_km_before > 0:
        drop_ratio = (delta.distance_km_before - delta.distance_km_after) / (
            delta.distance_km_before
        )
        if drop_ratio > DISTANCE_DROP_WARNING_RATIO:
            delta.warnings.append(
                f"distance dropped {drop_ratio:.0%} "
                f"({delta.distance_km_before} -> {delta.distance_km_after} km)"
            )

    if delta.train_stations_after < delta.train_stations_before:
        delta.warnings.append(
            f"lost {delta.train_stations_before - delta.train_stations_after} train station(s) "
            f"({delta.train_stations_before} -> {delta.train_stations_after})"
        )

    if delta.rail_service_after < delta.rail_service_before:
        delta.warnings.append(
            f"{delta.rail_service_before - delta.rail_service_after} station(s) lost their "
            f"train departures ({delta.rail_service_before} -> {delta.rail_service_after})"
        )

    # Growing gaps mean the OSM relation lost ways, even when nothing else moved.
    if delta.trail_gap_km_after - delta.trail_gap_km_before > GAP_GROWTH_WARNING_KM:
        delta.warnings.append(
            f"unmapped gaps grew by {delta.trail_gap_km_after - delta.trail_gap_km_before:.1f} km "
            f"({delta.trail_gap_km_before:.1f} -> {delta.trail_gap_km_after:.1f} km)"
        )

    if delta.elevation_gain_before > 0:
        elevation_drop = (delta.elevation_gain_before - delta.elevation_gain_after) / (
            delta.elevation_gain_before
        )
        if elevation_drop > ELEVATION_DROP_WARNING_RATIO:
            delta.warnings.append(
                f"elevation gain dropped {elevation_drop:.0%} "
                f"({delta.elevation_gain_before} -> {delta.elevation_gain_after} m)"
            )

    return delta


def build_run_report(
    previous_routes: list[dict[str, Any]],
    current_routes: list[dict[str, Any]],
    failed_route_refs: list[str],
    skipped_route_refs: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Compare the catalog before and after a run, and flag regressions.

    Routes are matched on their OSM relation id, so a renamed or re-slugged
    route still counts as the same route.
    """
    previous_by_relation = {
        int(route["osm_relation_id"]): route
        for route in previous_routes
        if route.get("osm_relation_id") is not None
    }
    current_by_relation = {
        int(route["osm_relation_id"]): route
        for route in current_routes
        if route.get("osm_relation_id") is not None
    }

    added = [
        str(route.get("path_ref", ""))
        for relation_id, route in current_by_relation.items()
        if relation_id not in previous_by_relation
    ]
    removed = [
        str(route.get("path_ref", ""))
        for relation_id, route in previous_by_relation.items()
        if relation_id not in current_by_relation
    ]

    deltas: list[RouteDelta] = []
    unchanged = 0
    for relation_id, current_route in current_by_relation.items():
        previous_route = previous_by_relation.get(relation_id)
        if previous_route is None:
            continue
        delta = _build_route_delta(previous_route, current_route)
        if delta.has_changes() or delta.warnings:
            deltas.append(delta)
        else:
            unchanged += 1

    warnings = [f"{delta.path_ref}: {warning}" for delta in deltas for warning in delta.warnings]
    warnings.extend(f"{path_ref}: disappeared from the catalog" for path_ref in sorted(removed))

    stations_with_rail_service = sum(_count_rail_service(route) for route in current_routes)
    train_stations = sum(_count_pois(route, "train_station") for route in current_routes)

    return {
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "routes_total": len(current_routes),
        "routes_added": sorted(added),
        "routes_removed": sorted(removed),
        "routes_unchanged": unchanged,
        "routes_changed": [delta.to_dict() for delta in deltas],
        "failed_routes": sorted(failed_route_refs),
        "skipped_routes": sorted(skipped_route_refs or []),
        "rail_service_coverage": {
            "train_stations": train_stations,
            "with_departures": stations_with_rail_service,
        },
        "warnings": warnings,
    }


def export_run_report(report: dict[str, Any], output_path: str) -> None:
    """Write the run report next to the catalog."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def log_run_report(report: dict[str, Any]) -> None:
    """Log the report so a run's effect on the data is visible without diffing."""
    logger.info("=== Run report ===")
    logger.info(
        "Routes: %d total, %d added, %d changed, %d unchanged, %d removed",
        report["routes_total"],
        len(report["routes_added"]),
        len(report["routes_changed"]),
        report["routes_unchanged"],
        len(report["routes_removed"]),
    )
    coverage = report["rail_service_coverage"]
    logger.info(
        "Rail service: %d/%d train stations have GTFS departures",
        coverage["with_departures"],
        coverage["train_stations"],
    )
    if report["failed_routes"]:
        logger.warning("Failed routes: %s", ", ".join(report["failed_routes"]))
    if report["skipped_routes"]:
        logger.warning("Skipped routes: %s", ", ".join(report["skipped_routes"]))
    for warning in report["warnings"]:
        logger.warning("Regression: %s", warning)
    if not report["warnings"]:
        logger.info("No regressions detected")
