# Architecture

## System Overview

```
BUILD TIME                                       RUNTIME (static files)
+--------------------------------------------+   +-----------------------------+
| Python pipeline (pipeline/)                |   | Astro static site           |
|                                            |   |                             |
| routes.yaml ---+                           |   |  MapLibre GL JS             |
| OSM extract ---+-> tracks                  |   |    Vector base tiles        |
| (Overpass      |   (geometry, SRTM         |   |    Contour overlay          |
|  fallback)     |    elevation, geography)  |   |    GeoJSON trails + POIs    |
| SRTM tiles ----+                           |   |  Route list + filters       |
|                                            |   |  Elevation chart (SVG)      |
| GTFS feeds ----> gtfs (stop index)         |   |  Section selector + QR      |
| OSM extract ---+                           |   |                             |
| SNCF stations -+-> pois (12x8 grid)        |   |    catalog.json             |
| gtfs index ----+                           |   |    tracks/<id>/*            |
|                                            |   |    pois/<col>_<row>.json    |
| tracks + pois --> link (OSRM refinement)   |   |    links/<id>.json          |
| tracks + links -> catalog + run-report     |   +-----------------------------+
|                                            |
|  ~/.local/share/open-rando/data/           |   +-----------------------------+
|    catalog.json, run-report.json           |   | Cloudflare R2               |
|    tracks/  pois/  links/                  |   |                             |
+--------------------------------------------+   |  france.pmtiles  (base)     |
                                                 |  world-low.pmtiles (z0-5)   |
+--------------------------------------------+   |  contours.pmtiles (SRTM)    |
| Tile pipelines (tiles/)                    |   |  hillshade.pmtiles (SRTM)   |
|                                            |   |  base/ + grid/{col}_{row}/  |
| Protomaps daily -> go-pmtiles extract      |   |    mobile offline bundles   |
| SRTM .hgt -> GDAL + tippecanoe             |   +-----------------------------+
| SRTM .hgt -> GDAL + encode_rgb_dem         |
| masters -> build-grid.py, build-routes.py  |
|   (grid.json + routes/<id>/pmtiles.json)   |
+--------------------------------------------+
```

Build flow: `cd pipeline && uv run python -m open_rando pipeline` produces data artifacts to `~/.local/share/open-rando/data/`, then `cd website && bun run build` (Astro) copies them to `public/data/` and outputs a deployable `dist/` folder. Data and cache are stored outside the repo to persist across git worktrees.

**CI/CD**: GitHub Actions deploys the website to GitHub Pages on push to `main`. See [Deployment](DEPLOYMENT.md) for the full workflow details.

---

## Pipeline Algorithm

The pipeline is five stages. Each one reads files the previous stage wrote and can run alone; `pipeline` chains them. See [Split pipeline](SPLIT_PIPELINE.md) for the file contracts.

1. **`tracks`**: for each curated route in `pipeline/routes.yaml` (with `--route`, `--retry-failed`):
   1. **Fetch** trail geometry (local OSM extract, border-crossing relations from Overpass; resolves super-relations recursively, fuses multiple relation IDs into a single LineString or MultiLineString)
   2. **Elevation** profiling via SRTM .hgt tiles: bilinear interpolation, sample every 50m, compute gain/loss/min/max with 5m noise threshold. A trail mapped in several segments is profiled segment by segment and stitched, so the straight jump across an unmapped gap costs no distance, climb or time; the gaps are reported as `trail_gap_km` and their positions as `segment_boundaries_km`
   3. **Geography**: département from the SNCF station nearest to the trail start, region from the département, terrain (coastal, mountain, hills, forest, plains from elevation, forest ratio, département) and difficulty (bands of ascent per km: <15 easy, <30 moderate, <50 difficult, else very difficult, with routes under 300m of total ascent always easy)
   4. **Landmarks** near the trail, for the AI hero image prompt
   5. **Export** `tracks/<id>/{track.json, trail.geojson, trail.gpx, elevation.json}`. A track knows nothing about POIs.
2. **`gtfs`**: download every national GTFS feed once (feed list from one transport.data.gouv.fr catalog call). One pass per feed fills the local stop index (`~/.cache/open-rando/gtfs/stops-index.sqlite`) and the per-feed departures cache (cached per ISO week).
3. **`pois`**: build the France-wide POI grid, 12x8 squares (same grid as the mobile tiles), from the local OSM extract index. Train stations are filtered against SNCF reference data (UIC codes) and get departures per kind of day (weekday / Saturday / Sunday); bus stops get GTFS line names (OSM-tagged lines when no GTFS stop is within 150 m); hotels and campings are kept as is; food shops (supermarket, convenience, bakery, butcher, greengrocer, general, farm, deli, cheese) and eateries (restaurant, cafe, bar) are kept when named, with their kind, raw `opening_hours` and phone when mapped. A place also tagged as lodging stays lodging. POIs carry stable OSM ids (`node/123`).
4. **`link`**: join the POI grid to each track, writing `links/<id>.json`. Train stations within 5 km (duplicate and never-closest filtering, then OSRM walking-distance junction refinement), bus stops within 2 km, hotels and campings within 3 km, shops and eateries within 1.5 km. Train stations get their position along the trail.
5. **`catalog`**: merge every `track.json` with its link counts into `catalog.json`, keeping tracks with at least 2 linked train stations. The catalog is rebuilt from the tracks on disk, so partial runs never drop other tracks. It is validated against `src/open_rando/data/catalog.schema.json` (nothing is written when validation fails), then `data/run-report.json` records what changed: routes added / changed / removed, per-route deltas (distance, stations, POIs, elevation gain), rail service coverage, failed and skipped routes, and regression warnings (route shrunk by more than 10%, train stations lost, stations that lost their train departures, elevation gain down by more than 20%), plus `inputs`: what each stage read, copied from `data/run-inputs.json`. Every stage records its inputs there when it finishes (last run of a stage wins): the git commit and whether tracked files were modified, the OSM extract file and index layers (and border-crossing relations fetched from Overpass), SRTM source, SNCF export file, the SHA-256 of every GTFS feed, the OSRM URL and graph file. A catalog diff can then be traced to new data or new code.

A companion app importing a custom GPX loads the POI squares that intersect it and applies the same link rules (see `processors/link.py`).

---

## Data Model

```python
@dataclass
class Accommodation:
    has_hotel: bool = False   # hotel, guest_house, hostel
    has_camping: bool = False # camp_site

@dataclass
class ServiceWindow:
    first_departure_minutes: int  # minutes after midnight; >1440 means after midnight
    last_departure_minutes: int
    departure_count: int

@dataclass
class RailService:
    weekday: ServiceWindow | None   # None = the GTFS feeds report no departure
    saturday: ServiceWindow | None
    sunday: ServiceWindow | None

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
    rail_service: RailService | None  # train stations only

@dataclass
class PointOfInterest:
    """A POI, independent of any track. Stored in the POI grid."""
    osm_id: str               # stable "node/123", "way/456"
    name: str
    lat: float
    lon: float
    poi_type: str             # "hotel", "camping", "shop", "eatery", "train_station", "bus_stop"
    url: str | None           # website URL (accommodation) or SNCF timetable link (train)
    transit_lines: list[str]  # GTFS route names for bus stops
    rail_service: RailService | None  # departures (train stations only)

@dataclass
class PoiLink:
    """How one POI relates to one track. Stored in links/<id>.json."""
    poi_id: str
    kind: str
    distance_to_trail_meters: float
    distance_km: float | None            # position along the trail (train stations only)
    junction: tuple[float, float] | None # (lon, lat) where the walk meets the trail

@dataclass
class Track:
    identifier: str           # deterministic hash of path_ref + relation_id
    slug: str                 # "gr-13"
    path_ref: str             # "GR 13"
    path_name: str
    description: str          # flavor text from routes.yaml
    osm_relation_id: int
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
    trail_segment_count: int # mapped segments; > 1 means the trail has gaps
    trail_gap_km: float      # straight-line length of those gaps, not walked
    geojson_path: str
    gpx_path: str
    elevation_path: str
    last_updated: str
    landmarks: list[Landmark]
```

---

## Project Structure

```
open-rando/
+-- pipeline/
|   +-- pyproject.toml
|   +-- uv.lock
|   +-- Makefile.osm             # download France extract, filter per layer, build the index
|   +-- routes.yaml              # curated GR route catalog (relation IDs, descriptions)
|   +-- src/open_rando/
|   |   +-- __main__.py
|   |   +-- cli.py               # argument parsing, `pipeline` command chaining the stages
|   |   +-- config.py            # constants (paths, API URLs, cache TTLs, thresholds)
|   |   +-- models.py            # Station, PointOfInterest, PoiLink, Track, Landmark dataclasses
|   |   +-- osm_tags.py          # OSM tag values shared by Overpass queries and the local index
|   |   +-- poi_grid.py          # fixed 12x8 grid splitting France-wide POIs into files
|   |   +-- poi_store.py         # read the POI grid written by `pois`
|   |   +-- commands/            # one module per subcommand
|   |   |   +-- tracks.py        # `tracks`: compute each curated track
|   |   |   +-- gtfs.py          # `gtfs`: download feeds, build stop index
|   |   |   +-- pois.py          # `pois`: build the France-wide POI grid
|   |   |   +-- link.py          # `link`: join POIs to each track
|   |   |   +-- catalog.py       # `catalog`: assemble catalog.json + run report
|   |   |   +-- images.py        # `images`: AI hero illustrations per route
|   |   |   +-- osm_index.py     # `osm-index`: build/inspect the local OSM extract index
|   |   +-- data/                # JSON Schemas: catalog, poi-square, poi-index, links,
|   |   |                        #   tile-grid, route-tiles
|   |   +-- fetchers/
|   |   |   +-- discovery.py     # load routes from routes.yaml
|   |   |   +-- osm_source.py    # one OSM source per run: local extract (default) or Overpass (dev)
|   |   |   +-- osm_extract.py   # query the local OSM extract index
|   |   |   +-- overpass.py      # Overpass API HTTP client with disk cache
|   |   |   +-- stations.py      # OSM station fetcher (bbox chunking for large trails)
|   |   |   +-- sncf.py          # SNCF reference station data (UIC codes, filtering)
|   |   |   +-- gtfs.py          # GTFS feed download, departures, bus line names
|   |   |   +-- gtfs_stops_index.py  # local SQLite index of every boarding stop
|   |   |   +-- pois.py          # accommodation and resupply POIs (hotels, campings, shops, eateries)
|   |   |   +-- landmarks.py     # landmarks near a trail (AI image prompts)
|   |   |   +-- routing.py       # OSRM walking-distance matrix (local router, see Makefile.osrm)
|   |   |   +-- srtm.py          # SRTM .hgt tile downloader + bilinear interpolation
|   |   +-- processors/
|   |   |   +-- trail.py         # fetch + fuse trail relations, shared by `pipeline` and `tracks`
|   |   |   +-- trail_assembly.py  # OSM relation elements -> ordered trail geometry
|   |   |   +-- match.py         # station-to-trail matching (LineString + MultiLineString)
|   |   |   +-- slice.py         # trail substring extraction, distance and gap computation
|   |   |   +-- elevation.py     # elevation profiling, duration, difficulty classification
|   |   |   +-- geography.py     # region/departement resolution, terrain classification
|   |   |   +-- link.py          # which POIs are reachable from a track, and where along it
|   |   +-- exporters/
|   |       +-- track.py         # track.json writer
|   |       +-- gpx.py           # GPX writer (multi-segment tracks with elevation)
|   |       +-- geojson.py       # GeoJSON FeatureCollection per track
|   |       +-- elevation.py     # per-track elevation profile JSON
|   |       +-- pois.py          # POI grid squares + index
|   |       +-- links.py         # links/<id>.json writer
|   |       +-- catalog.py       # catalog.json builder + schema validation
|   |       +-- report.py        # run-report.json (catalog diff, regression warnings)
|   |       +-- run_inputs.py    # run-inputs.json: input versions each stage read
|   |       +-- failures.py      # failed-routes.json log
|   |       +-- image_generator.py  # local FLUX hero images
|   +-- tests/
+-- tiles/
|   +-- Makefile                 # SRTM -> GDAL -> tippecanoe -> contours.pmtiles
|   +-- Makefile.protomaps       # france.pmtiles + world-low.pmtiles, upload to R2
|   +-- Makefile.hillshade       # hillshade.pmtiles (Mapbox RGB raster-dem)
|   +-- Makefile.routes          # base/ + 12x8 grid/ bundles, per-route manifests, upload
|   +-- build-grid.py            # split master archives into base + grid squares, write grid.json
|   +-- build-routes.py          # per-route manifests listing intersecting squares
|   +-- tile_manifests.py        # validate grid.json and route manifests against their schemas
|   +-- build_france_mask.py     # French admin border for clipping
|   +-- encode_rgb_dem.py        # SRTM -> Mapbox RGB PNG tiles
|   +-- download.sh              # fetch the go-pmtiles binary
+-- website/
|   +-- package.json
|   +-- bun.lock
|   +-- astro.config.mjs
|   +-- tailwind.config.mjs
|   +-- deploy.sh                # build + push dist/ to gh-pages
|   +-- .env.production          # PUBLIC_PMTILES_BASE (public R2 URL)
|   +-- scripts/
|   |   +-- check-pmtiles-base.mjs  # fail the build when PUBLIC_PMTILES_BASE is missing
|   +-- src/
|   |   +-- layouts/
|   |   |   +-- Landing.astro          # landing page layout (hero, features, CTA)
|   |   |   +-- Base.astro             # app layout (SEO meta, sticky nav, theme toggle, i18n)
|   |   +-- pages/
|   |   |   +-- [...locale]/           # one template per page, built for fr (root) and en (/en)
|   |   |   |   +-- index.astro        # landing page
|   |   |   |   +-- app/index.astro    # route explorer with filters + suggest panel
|   |   |   |   +-- app/route/[slug].astro  # route detail page
|   |   |   +-- about.astro, privacy.astro, legal.astro        # FR long-form prose
|   |   |   +-- en/about.astro, en/privacy.astro, en/legal.astro  # EN long-form prose
|   |   +-- components/
|   |   |   +-- RouteCard.astro        # clickable card with difficulty/terrain/description
|   |   |   +-- RouteList.astro        # grid + empty state
|   |   |   +-- RouteFilters.astro     # region, terrain, difficulty filters + suggest panel
|   |   |   +-- SearchableSelect.astro # searchable dropdown used by the filters
|   |   |   +-- ElevationChart.astro   # inline SVG elevation profile with map hover sync
|   |   +-- lib/
|   |       +-- catalog.ts             # types + data loading (tracks, links, POIs)
|   |       +-- poi-grid.ts            # POI grid maths (same grid as the pipeline)
|   |       +-- route-pois.ts          # pure join of links/<id>.json with POI squares
|   |       +-- poi-popup.ts           # POI map popups
|   |       +-- rail.ts                # train departure formatting
|   |       +-- map.ts                 # shared MapLibre utilities (createMap, contours, POIs, theme)
|   |       +-- route-map.ts           # detail-page map: trail, POIs, hover marker, section highlight
|   |       +-- section-selector.ts    # detail-page section picker: stats, GPX, QR code, URL state
|   |       +-- section-gpx.ts         # GPX 1.1 for one section of a route
|   |       +-- trail-geometry.ts      # haversine, cumulative distances, section index ranges
|   |       +-- styles/                # style-light.json, style-dark.json
|   |       +-- i18n.ts                # translation dictionary (FR/EN), localePath, getLocaleStaticPaths
|   |       +-- format.ts              # formatting utilities
|   |       +-- elevation.ts           # elevation profile utilities
|   |       +-- route-filters.ts       # filter logic
|   +-- public/data/                   # copied from ~/.local/share/open-rando/data/ at build
+-- docs/
```

**Python deps**: `requests`, `shapely`, `gpxpy`, `geojson`, `pyyaml`, `ruamel.yaml`, `jsonschema` (extras: `osmium` for the OSM index, `diffusers`/`torch` for `images`)
**JS deps**: `astro`, `@astrojs/sitemap`, `@astrojs/tailwind`, `maplibre-gl`, `pmtiles`, `qrcode-generator`, `tailwindcss`

---

## Caching

| Data | Cache location | TTL |
|------|---------------|-----|
| Local OSM extract index (trails, stations, accommodation, landmarks, forest) | `~/.cache/open-rando/osm/extract-index.sqlite` | Rebuilt by hand (`make -f Makefile.osm`) |
| Overpass API responses (trails) | `~/.cache/open-rando/overpass/` | 60 days |
| Overpass API responses (stations, accommodation) | `~/.cache/open-rando/overpass/` | 30 days |
| SNCF station reference data | `~/.cache/open-rando/sncf/` | 30 days |
| GTFS stop index, feeds and departures | `~/.cache/open-rando/gtfs/` | Feeds 30 days; departures per ISO week |
| OSRM walking-distance tables | `~/.cache/open-rando/osrm/` | 90 days |
| OSRM foot graph (built by `Makefile.osrm`) | `~/.cache/open-rando/osrm-graph/` | until rebuilt |
| SRTM elevation tiles | `~/.cache/open-rando/srtm/` | Permanent |

Overpass responses are keyed by SHA256 of the query string. SRTM tiles are keyed by tile name (e.g., `N47E003.hgt`). Missing tiles are cached as sentinels to avoid re-downloading. All caches are in `~/.cache/open-rando/` (shared across worktrees).

When an Overpass query is served from cache, the pipeline skips the cooldown sleep before the next API call. This makes re-runs with warm caches significantly faster (seconds instead of minutes).

---

## Tile Pipelines

Four build chains in `tiles/`, all feeding Cloudflare R2 (`open-rando-tiles`):

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

**4. Mobile offline grid** (`Makefile.routes`) — `build-grid.py` splits each master archive into a shared low-zoom `base/<layer>.pmtiles` plus a 12x8 grid of high-zoom `grid/{col}_{row}/<layer>.pmtiles`; `build-routes.py` writes `routes/<id>/pmtiles.json` listing the squares a route touches. Both manifests (`grid.json`, `pmtiles.json`) are validated against their JSON Schemas by `tile_manifests.py` before they are written. See [MOBILE_OFFLINE.md](MOBILE_OFFLINE.md).

The master PMTiles and the grid bundles live on R2 under the public `.r2.dev` URL. Upload via `rclone` (wrangler's 300 MiB per-object ceiling blocks the multi-GB files). MapLibre GL JS reads PMTiles natively via the `pmtiles://` protocol. See [VECTOR_TILES.md](VECTOR_TILES.md) for style integration + R2 setup.

Prerequisites: `gdal` (gdal_contour, gdalbuildvrt, gdalwarp, ogrmerge.py, ogr2ogr), `tippecanoe`, `uv`, `rclone`, `go-pmtiles`.

---

## Duration Estimation

Segment-by-segment calculation based on slope:

- **Flat** (slope < 10%): 4 km/h
- **Uphill** (slope >= 10%): 300m ascent per hour
- **Downhill** (slope >= 10%): 450m descent per hour

Slope is computed between consecutive 50m elevation samples. Cumulative time is stored in the elevation profile JSON for the website timeline.
