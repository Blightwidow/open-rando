# Architecture

## System Overview

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| routes.yaml ---+                        |   |  Leaflet Map + POI markers |
| Overpass API --+-> fetch trail ->       |   |  Route list + filters      |
| SNCF stations -+   match stations ->    |   |  Elevation Chart (SVG)     |
| GTFS API ------+   fetch POIs ->        |   |  Suggest panel             |
| SRTM tiles ----+   elevation ->         |   |    catalog.json            |
| OSRM router ---+   geography ->         |   |    /gpx/{id}.gpx           |
|                     export              |   |    /geojson/{id}.json      |
|        ~/.local/share/open-rando/data/  |   |    /elevation/{id}.json    |
|               catalog.json              |   +----------------------------+
|               gpx/*.gpx                 |
|               geojson/*.json            |
|               elevation/*.json          |
+-----------------------------------------+
```

Build flow: `cd pipeline && uv run python -m open_rando` produces data artifacts to `~/.local/share/open-rando/data/`, then `cd website && bun run build` (Astro) copies them to `public/data/` and outputs a deployable `dist/` folder. Data and cache are stored outside the repo to persist across git worktrees.

**CI/CD**: GitHub Actions deploys the website to GitHub Pages on push to `main`. See [Deployment](DEPLOYMENT.md) for the full workflow details.

---

## Pipeline Algorithm

1. **Load** curated route catalog from `pipeline/routes.yaml` (GR trails with relation IDs, descriptions, and metadata)
2. **For each route** (with `--route` filter support):
   1. **Fetch** trail geometry from Overpass API (resolves super-relations recursively, fuses multiple relation IDs into a single LineString or MultiLineString)
   2. **Fetch** train and bus stations near the trail bounding box (OSM data)
   3. **Filter** train stations against SNCF reference data (UIC codes) to keep only real passenger stations
   4. **Match** train stations to trail via Shapely linear referencing, keep if < 5km from trail. Skip route if fewer than 2 matched train stations.
   5. **Match** bus stops to trail (< 2km threshold)
   6. **Enrich** bus stops with GTFS route names from transport.data.gouv.fr API (match OSM stops to GTFS feeds, extract transit line names)
   7. **Fetch** accommodation POIs (hotels, campings) within 2km of trail via Overpass
   8. **Elevation** profiling via SRTM .hgt tiles: bilinear interpolation, sample every 50m, compute gain/loss/min/max with 5m noise threshold
   9. **Geography**: resolve region/departement from SNCF INSEE codes, classify terrain (coastal, mountain, hills, forest, plains based on elevation, forest ratio, departement), classify difficulty
   10. **Export** GPX files with `<ele>` tags and POI waypoints, GeoJSON, and elevation profiles (per-route JSON)
3. **Merge** into `catalog.json`: new routes replace existing entries by relation ID, unprocessed routes from previous runs are preserved (use `--reset` to start fresh)

---

## Data Model

```python
@dataclass
class Accommodation:
    has_hotel: bool = False   # hotel, guest_house, hostel
    has_camping: bool = False # camp_site

@dataclass
class Station:
    name: str
    code: str                 # SNCF UIC code or OSM node ID
    lat: float
    lon: float
    distance_to_trail_meters: float = 0.0
    transit_lines: list[str]
    accommodation: Accommodation
    transport_type: str       # "train" or "bus"
    connected_route_ids: set[str]  # GTFS route IDs for bus stops

@dataclass
class PointOfInterest:
    """A point of interest near a trail — displayed on the map only."""
    name: str
    lat: float
    lon: float
    poi_type: str             # "hotel", "camping", "train_station", "bus_stop"
    url: str | None           # website URL (accommodation) or SNCF timetable link (train)
    transit_lines: list[str]  # GTFS route names for bus stops
    distance_km: float | None # distance along trail (train stations only)

@dataclass
class Route:
    identifier: str           # deterministic hash of path_ref + relation_id
    slug: str                 # "gr-13"
    path_ref: str             # "GR 13"
    path_name: str
    description: str          # flavor text from routes.yaml
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
    difficulty: str           # easy/moderate/difficult/very_difficult
    is_circular_trail: bool
    terrain: list[str]        # ["coastal", "mountain", "hills", "forest", "plains"]
    geojson_path: str
    gpx_path: str
    last_updated: str
```

---

## Project Structure

```
open-rando/
+-- pipeline/
|   +-- pyproject.toml
|   +-- uv.lock
|   +-- routes.yaml              # curated GR route catalog (relation IDs, descriptions)
|   +-- src/open_rando/
|       +-- __init__.py
|       +-- __main__.py
|       +-- cli.py               # entry point, multi-route orchestration, catalog merging
|       +-- config.py            # constants (API URLs, cache TTLs, thresholds)
|       +-- models.py            # Accommodation, Station, PointOfInterest, Route dataclasses
|       +-- data/
|       |   +-- gr-descriptions.yaml  # route flavor text
|       +-- fetchers/
|       |   +-- discovery.py     # load routes from routes.yaml
|       |   +-- overpass.py      # Overpass API client (cached, super-relation resolution)
|       |   +-- stations.py      # OSM station fetcher (bbox chunking for large trails)
|       |   +-- sncf.py          # SNCF reference station data (UIC codes, filtering)
|       |   +-- gtfs.py          # GTFS bus stops + route names from transport.data.gouv.fr
|       |   +-- pois.py          # accommodation POIs (hotels, campings via Overpass)
|       |   +-- routing.py       # OSRM pedestrian routing for station-trail connectors
|       |   +-- srtm.py          # SRTM .hgt tile downloader + bilinear interpolation
|       +-- processors/
|       |   +-- match.py         # station-to-trail matching (LineString + MultiLineString)
|       |   +-- slice.py         # trail substring extraction, distance computation
|       |   +-- elevation.py     # elevation profiling, duration, difficulty classification
|       |   +-- geography.py     # region/departement resolution, terrain classification, forest ratio
|       |   +-- connectors.py    # pedestrian walking paths between stations and trail
|       +-- exporters/
|           +-- gpx.py           # GPX writer (multi-segment tracks with elevation + POI waypoints)
|           +-- geojson.py       # GeoJSON FeatureCollection per route
|           +-- catalog.py       # catalog.json writer
|           +-- elevation.py     # per-route elevation profile JSON
+-- website/
|   +-- package.json
|   +-- bun.lock
|   +-- astro.config.mjs
|   +-- tailwind.config.mjs
|   +-- src/
|   |   +-- layouts/
|   |   |   +-- Landing.astro          # landing page layout (hero, features, CTA)
|   |   |   +-- Base.astro             # app layout (SEO meta, sticky nav, theme toggle, i18n)
|   |   +-- pages/
|   |   |   +-- index.astro            # landing page (FR)
|   |   |   +-- about.astro            # about page (FR)
|   |   |   +-- privacy.astro          # privacy policy (FR)
|   |   |   +-- legal.astro            # legal mentions (FR)
|   |   |   +-- app/index.astro        # route explorer with filters + suggest panel (FR)
|   |   |   +-- app/route/[slug].astro # route detail page (FR)
|   |   |   +-- en/index.astro         # landing page (EN)
|   |   |   +-- en/about.astro         # about page (EN)
|   |   |   +-- en/privacy.astro       # privacy policy (EN)
|   |   |   +-- en/legal.astro         # legal mentions (EN)
|   |   |   +-- en/app/index.astro     # route explorer (EN)
|   |   |   +-- en/app/route/[slug].astro # route detail page (EN)
|   |   +-- components/
|   |   |   +-- RouteCard.astro        # clickable card with difficulty/terrain/description
|   |   |   +-- RouteList.astro        # grid + empty state
|   |   |   +-- RouteFilters.astro     # region, terrain, difficulty, step filters + suggest panel
|   |   |   +-- ElevationChart.astro   # inline SVG elevation profile with map hover sync
|   |   +-- lib/
|   |       +-- catalog.ts             # types + data loading
|   |       +-- i18n.ts                # translation dictionary (FR/EN) + helpers
|   |       +-- format.ts              # formatting utilities
|   |       +-- elevation.ts           # elevation profile utilities
|   |       +-- route-filters.ts       # filter logic
|   +-- public/data/                   # copied from ~/.local/share/open-rando/data/ at build
+-- docs/
```

**Python deps**: `requests`, `shapely`, `gpxpy`, `geojson`, `pyyaml`
**JS deps**: `astro`, `@astrojs/sitemap`, `leaflet`, `tailwindcss`

---

## Caching

| Data | Cache location | TTL |
|------|---------------|-----|
| Overpass API responses (trails) | `~/.cache/open-rando/overpass/` | 60 days |
| Overpass API responses (stations, accommodation) | `~/.cache/open-rando/overpass/` | 30 days |
| SNCF station reference data | `~/.cache/open-rando/sncf/` | 30 days |
| GTFS stops + feeds | `~/.cache/open-rando/gtfs/` | 30 days |
| OSRM pedestrian routes | `~/.cache/open-rando/osrm/` | 90 days |
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
