# Architecture

## System Overview

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| Overpass API --+                        |   |  Leaflet Map + List/Filter |
| OSM stations --+-> fetch -> match ->    |   |  Elevation Chart (SVG)     |
| SRTM tiles ---+   step graph -> DP ->   |   |  Section Hike Selector     |
|                    elevation -> export  |   |    catalog.json            |
|                      |                  |   |    /gpx/{id}.gpx           |
|        ~/.local/share/open-rando/data/  |   |    /geojson/{id}.json      |
|               catalog.json              |   |    /elevation/{id}.json   |
|               gpx/*.gpx                 |   +----------------------------+
|               geojson/*.json            |
|               elevation/*.json          |
+-----------------------------------------+
```

Build flow: `cd pipeline && uv run python -m open_rando` produces data artifacts to `~/.local/share/open-rando/data/`, then `cd website && bun run build` (Astro) copies them to `public/data/` and outputs a deployable `dist/` folder. Data and cache are stored outside the repo to persist across git worktrees.

**CI/CD**: GitHub Actions deploys the website to GitHub Pages on push to `main`. Data is downloaded from the latest GitHub Release artifact (uploaded manually after a local pipeline run). The prebuild script skips the local copy if `public/data/catalog.json` already exists (CI-friendly).

---

## Pipeline Algorithm

1. **Discover** all GR/GRP routes in France via Overpass (`ref~^GR`, area filter + superroute recursion)
2. **For each route**:
   1. **Fetch** the hiking relation from Overpass API (resolves super-relations recursively, returns LineString or MultiLineString for trails with >5km gaps)
   2. **Fetch** train stations near the route bounding box (OSM + SNCF data; bbox auto-splits into chunks for trails spanning >3°)
   3. **Match** stations to trail: find nearest point on trail with Shapely, keep if < 5km. For MultiLineString, compute global fractions across segments.
   4. **Order** matched stations by position along the trail (linear referencing)
   5. **Build step graph**: compute cumulative distances, create edges between station pairs 8-18km apart
   6. **Find hikes**: longest-path DP per connected component of the step graph (one optimal hike per trail section)
   7. **Elevation** via SRTM .hgt tiles: bilinear interpolation, sample every 50m, compute gain/loss/min/max with 5m noise threshold
   8. **Compute** duration per segment: 4 km/h flat, 300m/h ascent and 450m/h descent on slopes >= 10%
   9. **Classify** difficulty based on elevation gain per km and total gain (easy/moderate/difficult/very_difficult)
   10. **Export** GPX files with `<ele>` tags, GeoJSON, and elevation profiles (per-hike JSON)
3. **Export** `catalog.json` incrementally after each route (so interrupted runs still produce a usable catalog)

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
    elevation_gain_meters: int
    elevation_loss_meters: int

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
    elevation_gain_m: int  # from SRTM sampling
    elevation_loss_m: int
    max_elevation_m: int
    min_elevation_m: int
    difficulty: str        # easy/moderate/difficult/very_difficult
    bbox: tuple[float, float, float, float]
    region: str
    departement: str
    gpx_path: str
    geojson_path: str
    is_reversible: bool
    is_grp: bool           # True for GRP/GR de Pays routes
    is_circular_trail: bool # True if trail endpoints are < 1km apart
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
|       +-- cli.py              # entry point, multi-route orchestration
|       +-- config.py           # constants (step distances, API config, cache TTLs)
|       +-- models.py           # Station, HikeStep, Hike dataclasses
|       +-- fetchers/
|       |   +-- discovery.py   # GR route discovery via Overpass (all GR/GRP in France)
|       |   +-- overpass.py    # Overpass API client (cached, super-relation resolution)
|       |   +-- stations.py    # OSM station fetcher (bbox chunking for large trails)
|       |   +-- accommodation.py # hotel/camping near stations
|       |   +-- srtm.py        # SRTM .hgt tile downloader + bilinear interpolation
|       +-- processors/
|       |   +-- match.py       # station-to-trail matching (LineString + MultiLineString)
|       |   +-- slice.py       # step graph + longest-path DP hike finder
|       |   +-- elevation.py   # elevation profiling, duration, difficulty
|       +-- exporters/
|           +-- gpx.py         # GPX writer (multi-segment tracks with elevation)
|           +-- geojson.py     # GeoJSON FeatureCollection per hike
|           +-- catalog.py     # catalog.json writer
|           +-- elevation.py   # per-hike elevation profile JSON
+-- website/
|   +-- package.json
|   +-- bun.lock
|   +-- astro.config.mjs
|   +-- tailwind.config.mjs
|   +-- src/
|   |   +-- layouts/Base.astro           # SEO meta, sticky nav, theme toggle, i18n
|   |   +-- pages/
|   |   |   +-- index.astro             # map + filters + hike list (FR)
|   |   |   +-- hike/[slug].astro       # detail page (FR)
|   |   |   +-- en/index.astro          # map + filters + hike list (EN)
|   |   |   +-- en/hike/[slug].astro    # detail page (EN)
|   |   +-- components/
|   |   |   +-- HikeMap.astro           # Leaflet map (filter-aware)
|   |   |   +-- HikeList.astro          # grid + empty state
|   |   |   +-- HikeCard.astro          # clickable card with D+/difficulty
|   |   |   +-- HikeFilters.astro       # range sliders, URL sync, collapsible mobile
|   |   |   +-- ElevationChart.astro    # inline SVG elevation profile + timeline + section highlighting
|   |   +-- lib/
|   |       +-- catalog.ts              # types + data loading
|   |       +-- i18n.ts                 # translation dictionary (FR/EN) + helpers
|   +-- public/data/                    # copied from ~/.local/share/open-rando/data/ at build
+-- docs/
```

**Python deps**: `requests`, `shapely`, `gpxpy`, `geojson`
**JS deps**: `astro`, `@astrojs/sitemap`, `leaflet`, `tailwindcss`

---

## Caching

| Data | Cache location | TTL |
|------|---------------|-----|
| Route discovery | `~/.cache/open-rando/overpass/` | 60 days |
| Overpass API responses (trails) | `~/.cache/open-rando/overpass/` | 60 days |
| Overpass API responses (stations, accommodation) | `~/.cache/open-rando/overpass/` | 30 days |
| SRTM elevation tiles | `~/.cache/open-rando/srtm/` | Permanent |

Overpass responses are keyed by SHA256 of the query string. SRTM tiles are keyed by tile name (e.g., `N47E003.hgt`). Missing tiles are cached as sentinels to avoid re-downloading. All caches are in `~/.cache/open-rando/` (shared across worktrees).

When an Overpass query is served from cache, the pipeline skips the cooldown sleep before the next API call. This makes re-runs with warm caches significantly faster (seconds instead of minutes).

---

## Duration Estimation

Segment-by-segment calculation based on slope:

- **Flat** (slope < 10%): 4 km/h
- **Uphill** (slope >= 10%): 300m ascent per hour
- **Downhill** (slope >= 10%): 450m descent per hour

Slope is computed between consecutive 50m elevation samples. Cumulative time is stored in the elevation profile JSON for the website timeline.
