# TrainRando

Train station-to-station hiking on French GR paths.

## Project Structure

- `pipeline/` -- Python data pipeline (loads curated routes; computes tracks, the France-wide POI grid, links between them, and the catalog)
- `pipeline/routes.yaml` -- curated GR route catalog (176 trails with relation IDs and descriptions)
- `tiles/` -- Tile pipelines: Protomaps extract (OSM base + world coverage) + GDAL/tippecanoe (contours) → PMTiles
- `website/` -- Astro static site (MapLibre GL JS map, route list with filters, elevation chart, suggest panel)
- `docs/` -- Project documentation
- Pipeline output: `~/.local/share/open-rando/data/` (shared across worktrees)
- Cache: `~/.cache/open-rando/` (Overpass, SNCF, GTFS, OSRM, SRTM caches, shared across worktrees)

## Stack

- **Pipeline**: Python 3.12+, Shapely, requests, gpxpy, pyyaml
- **Website**: Astro, MapLibre GL JS, Tailwind CSS
- **Tiles**: go-pmtiles (Protomaps extract), GDAL, tippecanoe, PMTiles, Cloudflare R2
- **Data sources**: OpenStreetMap (local Geofabrik extracts via osmium, Overpass API as fallback), SNCF open data, transport.data.gouv.fr GTFS feeds, OSRM, SRTM elevation tiles

## Development

```bash
# Native tools (macOS): uv, osmium-tool, gdal, tippecanoe, rclone, bun
brew bundle
```

```bash
# Pipeline
cd pipeline && uv sync --all-extras
uv run python -m open_rando pipeline

# Website
cd website && bun install && bun run dev
```

## Commands

- `python -m open_rando pipeline` -- run every stage (tracks, gtfs, pois, link, catalog) for all GR routes, outputs to `data/`
- `python -m open_rando pipeline --route "GR 13"` -- run every stage for a single route (builds only the POI squares it touches)
- `python -m open_rando pipeline --dry-run` -- list discovered routes without processing
- `python -m open_rando pipeline --retry-failed` -- reprocess only routes listed in `data/failed-routes.json` (routes that raised in earlier runs: timeouts, rate limits)
- `python -m open_rando pipeline --skip-gtfs` -- skip the GTFS download stage, reuse the stop index
- `python -m open_rando tracks [--route "GR 13"] [--retry-failed] [--dry-run]` -- compute tracks only (geometry, elevation, terrain), no POIs
- `python -m open_rando gtfs [--resource ID] [--refresh] [--status]` -- download every national GTFS feed once, build the local stop index
- `python -m open_rando pois [--square 8_3] [--skip-gtfs]` -- build the France-wide POI grid (`data/pois/<col>_<row>.json`); needs the OSM index and the `gtfs` stage
- `python -m open_rando link [--route "GR 13"] [--skip-walking-refinement]` -- join POIs to each computed track (`data/links/<id>.json`)
- `python -m open_rando catalog` -- assemble `data/catalog.json` from tracks + links (rebuilt from the tracks on disk)
- `python -m open_rando images` -- generate AI hero illustrations for every route in the catalog
- `python -m open_rando images --route "GR 13"` -- generate the image for a single route
- `python -m open_rando images --regenerate` -- force regeneration even when the prompt is unchanged
- `python -m open_rando images --dry-run` -- report cache hit/miss per route without loading the model
- `python -m open_rando osm-index` -- build the local OSM extract index from the per-layer PBFs (replaces Overpass queries)
- `python -m open_rando osm-index --status` -- report which layers the index holds
- `brew bundle` (repo root) -- install native tools (uv, osmium-tool, gdal, tippecanoe, rclone, bun)
- `make -f Makefile.osm check` (in pipeline/) -- verify osmium-tool + curl are installed
- `make -f Makefile.osm` (in pipeline/) -- download france-latest.osm.pbf (~5GB, once), filter per-layer extracts, build the index
- `make -f Makefile.osm extracts` (in pipeline/) -- re-filter the per-layer extracts only
- `make -f Makefile.osm clean` (in pipeline/) -- drop extracts + index, keep the downloaded planet file
- `make` (in tiles/) -- build contour tiles (requires GDAL + tippecanoe)
- `make install` (in tiles/) -- verify contour pipeline dependencies
- `./download.sh` (in tiles/) -- fetch go-pmtiles binary
- `make -f Makefile.protomaps` (in tiles/) -- extract france.pmtiles from Protomaps daily build (HTTP range requests)
- `make -f Makefile.protomaps world` (in tiles/) -- extract world-low.pmtiles (z0-5)
- `make -f Makefile.protomaps upload` (in tiles/) -- upload france.pmtiles to R2 (via rclone)
- `make -f Makefile.protomaps upload-world` (in tiles/) -- upload world-low.pmtiles to R2
- `make -f Makefile.protomaps upload-contours` (in tiles/) -- upload contours.pmtiles to R2
- `make -f Makefile.hillshade` (in tiles/) -- build hillshade.pmtiles (Mapbox RGB raster-dem from SRTM, z6-11, FR-clipped)
- `make -f Makefile.hillshade upload` (in tiles/) -- upload hillshade.pmtiles to R2
- `make -f Makefile.routes download-masters` (in tiles/) -- pull france/contours/hillshade master archives from R2 via rclone
- `make -f Makefile.routes` (in tiles/) -- build hybrid base + 12x8 grid PMTiles + per-route manifests for mobile offline (incremental; writes to data/grid.json + data/routes/)
- `make -f Makefile.routes build-grid SQUARE=<col>_<row>` (in tiles/) -- build a single grid square (skips base rebuild)
- `make -f Makefile.routes build-routes ROUTE=<id>` (in tiles/) -- rewrite one route's manifest
- `make -f Makefile.routes upload` (in tiles/) -- upload base/ + grid/ bundles to R2
- `bun run dev` (in website/) -- start dev server
- `bun run build` (in website/) -- build static site to `dist/`

## Code Conventions

- Python: ruff for formatting + linting, mypy for type checking
- TypeScript: Astro defaults (prettier, eslint)
- No abbreviated variable names
- Descriptive names even in loops
- Test behavior not implementation

## Architecture

See `docs/ARCHITECTURE.md` for algorithm and data model, `docs/DATA_SOURCES.md` for sources and risks, `docs/DEPLOYMENT.md` for GitHub Pages deployment.

OSM access: every OSM query (trail geometry, stations, accommodation, landmarks, forest) reads the local extract index at `~/.cache/open-rando/osm/extract-index.sqlite` when the matching layer is built, and falls back to the Overpass API otherwise. Build it with `make -f Makefile.osm` (needs `osmium-tool`); the public Overpass API returns 504s under load.

Pipeline flow (five stages, each reads files the previous one wrote, see `docs/SPLIT_PIPELINE.md`): `tracks` (routes.yaml -> trail geometry from local extract or Overpass with superroute recursion -> SRTM elevation profile every 50m -> geography: region, terrain, difficulty -> `data/tracks/<id>/{track.json, trail.geojson, trail.gpx, elevation.json}`, no POIs) -> `gtfs` (download all national GTFS feeds once, build the stop index + per-feed departures cache) -> `pois` (France-wide, fixed 12x8 grid like the mobile tiles: train stations SNCF-filtered with departures per kind of day, bus stops with GTFS line names, hotels, campings; stable OSM ids; `data/pois/<col>_<row>.json` + `index.json`) -> `link` (join POIs to each track: stations <5km with walking-distance junction, bus stops <2km, hotels/campings <3km; `data/links/<id>.json`) -> `catalog` (merge tracks + link counts into `data/catalog.json`, keep tracks with >=2 train stations, validate against `src/open_rando/data/catalog.schema.json`, write `data/run-report.json` with catalog diff + regression warnings). Other schemas: `poi-square`, `poi-index`, `links` in `src/open_rando/data/`. Routes that raise are logged with traceback to `data/failed-routes.json` (cleared once they succeed)

Tile pipelines: (1) go-pmtiles extracts france.pmtiles (France bbox, z6-13 Flat v4 schema: roads, landcover, landuse, water, buildings, pois, places, boundaries) + world-low.pmtiles (world z0-5) from the Protomaps daily planet build. (2) GDAL + tippecanoe builds contours.pmtiles from SRTM .hgt tiles (25m + 100m intervals, clipped to FR admin border). (3) GDAL + encode_rgb_dem.py builds hillshade.pmtiles (Mapbox RGB raster-dem, z6-11, clipped to FR admin border) from the same SRTM tiles. (4) `build-grid.py` splits each master archive into a shared low-zoom `base/<layer>.pmtiles` + a 12x8 grid of high-zoom `grid/{col}_{row}/<layer>.pmtiles` for mobile offline (base shared across all routes, grid squares shared across overlapping routes), and `build-routes.py` emits `routes/{id}/pmtiles.json` listing intersecting square coords; `grid.json` + per-route manifests ship with the static site. All hosted on Cloudflare R2 (uploaded via rclone). See `docs/VECTOR_TILES.md` for details.

Website consumes `data/catalog.json` (tracks only) and serves `tracks/<id>/{trail.gpx, trail.geojson, elevation.json}` as static files. Route detail pages join `links/<id>.json` with the POI grid squares at build time (`getRoutePois` in `website/src/lib/catalog.ts`). Routes displayed on MapLibre GL JS map with vector tile base (Protomaps-based hiking style, light+dark themes), contour overlay, and GeoJSON trail/POI markers (train stations, bus stops, hotels, campings). Map styles in `website/src/lib/styles/`. The explore page has filters (region, terrain, difficulty) and a list/map tab switcher. Detail pages show an interactive SVG elevation chart with hover-synced map markers and POI overlays.
