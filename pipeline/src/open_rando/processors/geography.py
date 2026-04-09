"""Region and terrain classification for hikes."""

from __future__ import annotations

import logging
from typing import Any

from shapely.geometry import LineString, MultiLineString
from shapely.geometry.polygon import Polygon
from shapely.ops import unary_union
from shapely.prepared import prep

from open_rando.fetchers.overpass import query_overpass

logger = logging.getLogger("open_rando")

FOREST_SAMPLE_POINTS = 20
FOREST_RATIO_THRESHOLD = 0.4

# French départements that border the sea or ocean.
COASTAL_DEPARTEMENTS: set[str] = {
    "06",  # Alpes-Maritimes
    "11",  # Aude
    "13",  # Bouches-du-Rhône
    "14",  # Calvados
    "17",  # Charente-Maritime
    "2A",  # Corse-du-Sud
    "2B",  # Haute-Corse
    "22",  # Côtes-d'Armor
    "29",  # Finistère
    "30",  # Gard
    "33",  # Gironde
    "34",  # Hérault
    "35",  # Ille-et-Vilaine
    "40",  # Landes
    "44",  # Loire-Atlantique
    "50",  # Manche
    "56",  # Morbihan
    "59",  # Nord
    "62",  # Pas-de-Calais
    "64",  # Pyrénées-Atlantiques
    "66",  # Pyrénées-Orientales
    "76",  # Seine-Maritime
    "80",  # Somme
    "83",  # Var
    "85",  # Vendée
}

# Mapping from 2-digit département code to région name.
DEPARTEMENT_TO_REGION: dict[str, str] = {
    # Auvergne-Rhône-Alpes
    "01": "Auvergne-Rhône-Alpes",
    "03": "Auvergne-Rhône-Alpes",
    "07": "Auvergne-Rhône-Alpes",
    "15": "Auvergne-Rhône-Alpes",
    "26": "Auvergne-Rhône-Alpes",
    "38": "Auvergne-Rhône-Alpes",
    "42": "Auvergne-Rhône-Alpes",
    "43": "Auvergne-Rhône-Alpes",
    "63": "Auvergne-Rhône-Alpes",
    "69": "Auvergne-Rhône-Alpes",
    "73": "Auvergne-Rhône-Alpes",
    "74": "Auvergne-Rhône-Alpes",
    # Bourgogne-Franche-Comté
    "21": "Bourgogne-Franche-Comté",
    "25": "Bourgogne-Franche-Comté",
    "39": "Bourgogne-Franche-Comté",
    "58": "Bourgogne-Franche-Comté",
    "70": "Bourgogne-Franche-Comté",
    "71": "Bourgogne-Franche-Comté",
    "89": "Bourgogne-Franche-Comté",
    "90": "Bourgogne-Franche-Comté",
    # Bretagne
    "22": "Bretagne",
    "29": "Bretagne",
    "35": "Bretagne",
    "56": "Bretagne",
    # Centre-Val de Loire
    "18": "Centre-Val de Loire",
    "28": "Centre-Val de Loire",
    "36": "Centre-Val de Loire",
    "37": "Centre-Val de Loire",
    "41": "Centre-Val de Loire",
    "45": "Centre-Val de Loire",
    # Corse
    "2A": "Corse",
    "2B": "Corse",
    # Grand Est
    "08": "Grand Est",
    "10": "Grand Est",
    "51": "Grand Est",
    "52": "Grand Est",
    "54": "Grand Est",
    "55": "Grand Est",
    "57": "Grand Est",
    "67": "Grand Est",
    "68": "Grand Est",
    "88": "Grand Est",
    # Hauts-de-France
    "02": "Hauts-de-France",
    "59": "Hauts-de-France",
    "60": "Hauts-de-France",
    "62": "Hauts-de-France",
    "80": "Hauts-de-France",
    # Île-de-France
    "75": "Île-de-France",
    "77": "Île-de-France",
    "78": "Île-de-France",
    "91": "Île-de-France",
    "92": "Île-de-France",
    "93": "Île-de-France",
    "94": "Île-de-France",
    "95": "Île-de-France",
    # Normandie
    "14": "Normandie",
    "27": "Normandie",
    "50": "Normandie",
    "61": "Normandie",
    "76": "Normandie",
    # Nouvelle-Aquitaine
    "16": "Nouvelle-Aquitaine",
    "17": "Nouvelle-Aquitaine",
    "19": "Nouvelle-Aquitaine",
    "23": "Nouvelle-Aquitaine",
    "24": "Nouvelle-Aquitaine",
    "33": "Nouvelle-Aquitaine",
    "40": "Nouvelle-Aquitaine",
    "47": "Nouvelle-Aquitaine",
    "64": "Nouvelle-Aquitaine",
    "79": "Nouvelle-Aquitaine",
    "86": "Nouvelle-Aquitaine",
    "87": "Nouvelle-Aquitaine",
    # Occitanie
    "09": "Occitanie",
    "11": "Occitanie",
    "12": "Occitanie",
    "30": "Occitanie",
    "31": "Occitanie",
    "32": "Occitanie",
    "34": "Occitanie",
    "46": "Occitanie",
    "48": "Occitanie",
    "65": "Occitanie",
    "66": "Occitanie",
    "81": "Occitanie",
    "82": "Occitanie",
    # Pays de la Loire
    "44": "Pays de la Loire",
    "49": "Pays de la Loire",
    "53": "Pays de la Loire",
    "72": "Pays de la Loire",
    "85": "Pays de la Loire",
    # Provence-Alpes-Côte d'Azur
    "04": "Provence-Alpes-Côte d'Azur",
    "05": "Provence-Alpes-Côte d'Azur",
    "06": "Provence-Alpes-Côte d'Azur",
    "13": "Provence-Alpes-Côte d'Azur",
    "83": "Provence-Alpes-Côte d'Azur",
    "84": "Provence-Alpes-Côte d'Azur",
}


def build_sncf_insee_index(records: list[dict[str, Any]]) -> dict[str, str]:
    """Build a mapping from SNCF trigramme to INSEE commune code."""
    index: dict[str, str] = {}
    for record in records:
        trigramme = record.get("libellecourt")
        insee_code = record.get("codeinsee")
        if trigramme and insee_code:
            index[str(trigramme).strip()] = str(insee_code).strip()
    return index


def resolve_departement(station_code: str, sncf_insee: dict[str, str]) -> str:
    """Derive département code from a station's SNCF trigramme via INSEE code.

    Returns the 2-character département code (e.g. "64"), or "" if unknown.
    """
    insee_code = sncf_insee.get(station_code, "")
    if not insee_code:
        return ""
    # Corse uses 2A/2B prefixes
    if insee_code.startswith("2A") or insee_code.startswith("2B"):
        return insee_code[:2]
    # DOM-TOM use 3-digit codes (97x), but unlikely for GR trails
    if insee_code.startswith("97") and len(insee_code) >= 3:
        return insee_code[:3]
    # Standard: first 2 digits
    if len(insee_code) >= 2:
        return insee_code[:2]
    return ""


def resolve_region(departement: str) -> str:
    """Map a département code to its région name. Returns "" if unknown."""
    return DEPARTEMENT_TO_REGION.get(departement, "")


def classify_terrain(
    max_elevation_meters: int,
    elevation_gain_meters: int,
    distance_km: float,
    departement: str,
    forest_ratio: float,
) -> list[str]:
    """Classify terrain tags for a hike based on elevation and geography.

    Returns a list of non-mutually-exclusive terrain tags.
    """
    tags: list[str] = []

    gain_per_km = elevation_gain_meters / distance_km if distance_km > 0 else 0

    # Coastal: low elevation in a coastal département
    if max_elevation_meters < 200 and departement in COASTAL_DEPARTEMENTS:
        tags.append("coastal")

    # Mountain: high elevation
    if max_elevation_meters >= 1000:
        tags.append("mountain")

    # Forest: significant forest coverage along trail
    if forest_ratio >= FOREST_RATIO_THRESHOLD:
        tags.append("forest")

    # Hills: moderate elevation or steep gain
    if 300 <= max_elevation_meters < 1000 or (max_elevation_meters < 1000 and gain_per_km >= 25):
        tags.append("hills")

    # Plains: low, flat, not coastal
    if max_elevation_meters < 300 and gain_per_km < 25 and "coastal" not in tags:
        tags.append("plains")

    return tags


def fetch_forest_areas(
    bbox: tuple[float, float, float, float],
) -> list[Polygon]:
    """Fetch forest/wood polygons from Overpass within a bounding box.

    bbox is (min_lon, min_lat, max_lon, max_lat) — Shapely bounds order.
    Returns a list of Shapely Polygons.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    query = f"""
[out:json][timeout:120];
(
  way["landuse"="forest"]({min_lat},{min_lon},{max_lat},{max_lon});
  way["natural"="wood"]({min_lat},{min_lon},{max_lat},{max_lon});
  rel["landuse"="forest"]({min_lat},{min_lon},{max_lat},{max_lon});
  rel["natural"="wood"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out geom;
"""
    data, _cache_hit = query_overpass(query)
    polygons: list[Polygon] = []

    for element in data.get("elements", []):
        geometry = element.get("geometry", [])
        if not geometry:
            # Relations may have members instead of direct geometry
            members = element.get("members", [])
            for member in members:
                member_geometry = member.get("geometry", [])
                if member_geometry and len(member_geometry) >= 4:
                    coords = [(point["lon"], point["lat"]) for point in member_geometry]
                    try:
                        polygons.append(Polygon(coords))
                    except Exception:
                        continue
            continue

        if len(geometry) >= 4:
            coords = [(point["lon"], point["lat"]) for point in geometry]
            try:
                polygons.append(Polygon(coords))
            except Exception:
                continue

    logger.info("Fetched %d forest polygons in bbox", len(polygons))
    return polygons


def compute_forest_ratio(
    trail: LineString | MultiLineString,
    forest_polygons: list[Polygon],
) -> float:
    """Compute the fraction of trail sample points that fall within forest areas.

    Samples FOREST_SAMPLE_POINTS evenly-spaced points along the trail and checks
    how many are inside forest polygons.
    """
    if not forest_polygons:
        return 0.0

    # Merge all forest polygons into one prepared geometry for fast queries
    try:
        merged_forest = prep(unary_union(forest_polygons))
    except Exception:
        logger.warning("Failed to merge forest polygons")
        return 0.0

    # Sample points along the trail
    combined = unary_union(trail) if isinstance(trail, MultiLineString) else trail

    total_length = combined.length
    if total_length == 0:
        return 0.0

    in_forest = 0
    for index in range(FOREST_SAMPLE_POINTS):
        fraction = index / (FOREST_SAMPLE_POINTS - 1) if FOREST_SAMPLE_POINTS > 1 else 0.5
        point = combined.interpolate(fraction, normalized=True)
        if merged_forest.contains(point):
            in_forest += 1

    ratio = in_forest / FOREST_SAMPLE_POINTS
    logger.info("Forest ratio: %.0f%% (%d/%d points)", ratio * 100, in_forest, FOREST_SAMPLE_POINTS)
    return ratio
