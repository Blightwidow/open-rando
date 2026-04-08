# Architecture

## System Overview

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| Overpass API --+                        |   |  Leaflet Map + List/Filter |
| OSM stations --+-> fetch -> match ->    |   |         |                  |
| SRTM tiles ---+   step graph -> DFS ->  |   |    catalog.json            |
|                    export               |   |    /gpx/{id}.gpx           |
|                      |                  |   |    /geojson/{id}.json      |
|               data/catalog.json         |   +----------------------------+
|               data/gpx/*.gpx            |
|               data/geojson/*.json       |
+-----------------------------------------+
```

Build flow: `cd pipeline && uv run python -m open_rando` produces data artifacts, then `cd website && bun run build` (Astro) consumes them and outputs a deployable `dist/` folder.

---

## Pipeline Algorithm

1. **Fetch** a GR hiking relation from Overpass API (resolves super-relations recursively)
2. **Fetch** train stations near the route bounding box (OSM + SNCF data)
3. **Match** stations to trail: find nearest point on trail with Shapely, keep if < 5km
4. **Order** matched stations by position along the trail (linear referencing)
5. **Build step graph**: compute cumulative distances, create edges between station pairs 8-18km apart
6. **Find hikes**: DFS for all maximal chains through the step graph, deduplicate sub-paths
7. **Enrich** (planned) with SRTM elevation: sample every 50m, compute gain/loss/min/max
8. **Compute** duration estimate (4.5 km/h flat walking speed) per step and total
9. **Export** GPX files (one track per hike, one segment per step), GeoJSON, and `catalog.json`

---

## Data Model

```python
@dataclass
class Station:
    name: str              # "Fontainebleau-Avon"
    code: str              # SNCF UIC code or OSM node ID
    lat: float
    lon: float
    distance_to_trail_m: float
    transit_lines: list[str]

@dataclass
class HikeStep:
    start_station: Station
    end_station: Station
    distance_km: float
    estimated_duration_minutes: int

@dataclass
class Hike:
    id: str                # deterministic hash
    slug: str              # "gr-13-auxerre-saint-gervais-to-sermizelles-vezelay"
    path_ref: str          # "GR 13"
    path_name: str
    osm_relation_id: int
    start_station: Station # first step's start
    end_station: Station   # last step's end
    steps: list[HikeStep]  # 1+ steps, each 8-18km
    distance_km: float     # sum of step distances
    estimated_duration_min: int
    elevation_gain_m: int  # planned
    elevation_loss_m: int  # planned
    max_elevation_m: int   # planned
    min_elevation_m: int   # planned
    difficulty: str        # planned
    bbox: tuple[float, float, float, float]
    region: str
    departement: str
    gpx_path: str
    geojson_path: str
    is_reversible: bool
    last_updated: str
```

---

## Project Structure

```
open-rando/
+-- pipeline/
|   +-- pyproject.toml
|   +-- uv.lock
|   +-- src/open_rando/
|       +-- __init__.py
|       +-- __main__.py
|       +-- cli.py              # entry point
|       +-- config.py           # constants (step distances, API config)
|       +-- models.py           # Station, HikeStep, Hike dataclasses
|       +-- fetchers/
|       |   +-- overpass.py     # Overpass API client (super-relation resolution)
|       |   +-- stations.py    # OSM station fetcher
|       +-- processors/
|       |   +-- match.py       # station-to-trail matching (Shapely)
|       |   +-- slice.py       # step graph + DFS hike finder
|       +-- exporters/
|           +-- gpx.py         # GPX writer (multi-segment tracks)
|           +-- geojson.py     # GeoJSON FeatureCollection per hike
|           +-- catalog.py     # catalog.json writer
+-- website/
|   +-- package.json
|   +-- bun.lock
|   +-- astro.config.mjs
|   +-- tailwind.config.mjs
|   +-- src/
|   |   +-- layouts/Base.astro
|   |   +-- pages/
|   |   |   +-- index.astro             # map + filters + hike list
|   |   |   +-- hike/[slug].astro       # detail page
|   |   +-- components/
|   |   |   +-- HikeMap.astro           # Leaflet map (filter-aware)
|   |   |   +-- HikeList.astro
|   |   |   +-- HikeCard.astro          # clickable card linking to detail
|   |   |   +-- HikeFilters.astro       # range sliders
|   |   +-- lib/
|   |       +-- catalog.ts              # types + data loading
|   +-- public/data/                    # copied from pipeline output at build
+-- data/                               # gitignored pipeline output
+-- docs/
```

**Python deps**: `requests`, `shapely`, `gpxpy`
**JS deps**: `astro`, `leaflet`, `tailwindcss`
