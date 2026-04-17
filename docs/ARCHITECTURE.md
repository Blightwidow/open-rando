# Architecture

## System Overview

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| routes.yaml ---+                        |   |  MapLibre GL JS            |
| Overpass API --+-> fetch trail ->       |   |    Vector base tiles       |
| SNCF stations -+   match stations ->    |   |    Contour overlay         |
| GTFS API ------+   fetch POIs ->        |   |    GeoJSON trails + POIs   |
| SRTM tiles ----+   elevation ->         |   |  Route list + filters      |
| OSRM router ---+   geography ->         |   |  Elevation Chart (SVG)     |
|                     export              |   |  Suggest panel             |
|        ~/.local/share/open-rando/data/  |   |    catalog.json            |
|               catalog.json              |   |    /gpx/{id}.gpx           |
|               gpx/*.gpx                 |   |    /geojson/{id}.json      |
|               geojson/*.json            |   |    /elevation/{id}.json    |
|               elevation/*.json          |   +----------------------------+
+-----------------------------------------+
                                              +----------------------------+
+-----------------------------------------+  | Cloudflare R2              |
| Tile Pipeline                           |  |                            |
|                                         |  |  france.pmtiles  (base)    |
| Protomaps daily -> go-pmtiles extract ->|  |  world-low.pmtiles (z0-5)  |
| SRTM .hgt -> GDAL + tippecanoe ------>  |  |  contours.pmtiles (SRTM)   |
| SRTM .hgt -> GDAL + encode_rgb_dem ->   |  |  hillshade.pmtiles (SRTM)  |
|               france.pmtiles            |  +----------------------------+
|               world-low.pmtiles         |
|               contours.pmtiles          |
|               hillshade.pmtiles         |
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
+-- tiles/
|   +-- Makefile                  # SRTM → GDAL → tippecanoe → contours.pmtiles
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
|   |       +-- map.ts                 # shared MapLibre utilities (createMap, contours, POIs, theme)
|   |       +-- i18n.ts                # translation dictionary (FR/EN) + helpers
|   |       +-- format.ts              # formatting utilities
|   |       +-- elevation.ts           # elevation profile utilities
|   |       +-- route-filters.ts       # filter logic
|   +-- public/data/                   # copied from ~/.local/share/open-rando/data/ at build
+-- docs/
```

**Python deps**: `requests`, `shapely`, `gpxpy`, `geojson`, `pyyaml`
**JS deps**: `astro`, `@astrojs/sitemap`, `maplibre-gl`, `pmtiles`, `tailwindcss`

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

## Tile Pipelines

Three independent build chains in `tiles/`, all feeding Cloudflare R2 (`open-rando-tiles`):

**1. Protomaps base** (`Makefile.protomaps`) — `go-pmtiles` extracts regional subsets from Protomaps' daily planet build via HTTP range requests (no full planet download).
- `france.pmtiles` — France bbox `-5.5,41.0,10.0,51.5`, z6-13, Flat v4 schema
- `world-low.pmtiles` — worldwide, z0-5 (~15MB), for zoomed-out context

**2. Contours** (`Makefile`) — GDAL + tippecanoe from SRTM tiles, clipped to French admin border:
```
~/.cache/open-rando/srtm/*.hgt
    → gdal_contour -i 25  → per-tile contours_25m/*.fgb
    → gdal_contour -i 100 → per-tile contours_100m/*.fgb
    → ogrmerge.py → contours_{25m,100m}.fgb
    → ogr2ogr -clipsrc france-boundary.geojson → *_clipped.fgb
    → tippecanoe → contours.pmtiles
```
- **25m minor contours**: z13-15
- **100m major contours**: z8-15, elevation labels at z13+

**3. Hillshade** (`Makefile.hillshade`) — GDAL + custom `encode_rgb_dem.py` (rasterio/mercantile/PIL):
```
~/.cache/open-rando/srtm/*.hgt
    → gdalbuildvrt → dem.vrt
    → gdalwarp (EPSG:3857, cutline france-boundary.geojson, Int16+DEFLATE) → dem_3857.tif
    → encode_rgb_dem.py (Mapbox RGB PNG tiles) → hillshade.mbtiles
    → pmtiles convert → hillshade.pmtiles  (z6-11)
```
Replaces `rio-rgbify` which failed with a PROJ error on our DEM. Int16 + DEFLATE compression keeps the intermediate DEM ~1-2GB instead of 88GB Float32.

All four PMTiles live on R2 under the public `.r2.dev` URL. Upload via `rclone` (wrangler's 300 MiB per-object ceiling blocks the multi-GB files). MapLibre GL JS reads PMTiles natively via the `pmtiles://` protocol. See [VECTOR_TILES.md](VECTOR_TILES.md) for style integration + R2 setup.

Prerequisites: `gdal` (gdal_contour, gdalbuildvrt, gdalwarp, ogrmerge.py, ogr2ogr), `tippecanoe`, `uv`, `rclone`, `go-pmtiles`.

---

## Duration Estimation

Segment-by-segment calculation based on slope:

- **Flat** (slope < 10%): 4 km/h
- **Uphill** (slope >= 10%): 300m ascent per hour
- **Downhill** (slope >= 10%): 450m descent per hour

Slope is computed between consecutive 50m elevation samples. Cumulative time is stored in the elevation profile JSON for the website timeline.
