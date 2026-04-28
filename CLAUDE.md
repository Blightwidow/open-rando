# TrainRando

Train station-to-station hiking on French GR paths.

## Project Structure

- `pipeline/` -- Python data pipeline (loads curated routes, fetches trail/station/POI data, exports GPX/catalog)
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
- **Data sources**: OpenStreetMap Overpass API, SNCF open data, transport.data.gouv.fr GTFS API, OSRM, SRTM elevation tiles

## Development

```bash
# Pipeline
cd pipeline && uv sync --all-extras
uv run python -m open_rando pipeline

# Website
cd website && bun install && bun run dev
```

## Commands

- `python -m open_rando pipeline` -- run data pipeline for all GR routes, outputs to `data/`
- `python -m open_rando pipeline --route "GR 13"` -- run pipeline for a single route
- `python -m open_rando pipeline --dry-run` -- list discovered routes without processing
- `python -m open_rando pipeline --reset` -- clear catalog before processing (default: merge with existing)
- `python -m open_rando images` -- generate AI hero illustrations for every route in the catalog
- `python -m open_rando images --route "GR 13"` -- generate the image for a single route
- `python -m open_rando images --regenerate` -- force regeneration even when the prompt is unchanged
- `python -m open_rando images --dry-run` -- report cache hit/miss per route without loading the model
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

Pipeline flow: load routes from `routes.yaml` -> for each route: fetch trail geometry (Overpass, superroute recursion) -> fetch train stations (OSM + SNCF filtering) -> match stations to trail -> fetch bus stops + GTFS enrichment (route names from transport.data.gouv.fr) -> fetch accommodation POIs (hotels, campings via Overpass) -> elevation profiling (SRTM sampling every 50m) -> geography classification (region, terrain, difficulty) -> export (GPX with POI waypoints + GeoJSON + elevation profiles) -> merge into catalog.json

Tile pipelines: (1) go-pmtiles extracts france.pmtiles (France bbox, z6-13 Flat v4 schema: roads, landcover, landuse, water, buildings, pois, places, boundaries) + world-low.pmtiles (world z0-5) from the Protomaps daily planet build. (2) GDAL + tippecanoe builds contours.pmtiles from SRTM .hgt tiles (25m + 100m intervals, clipped to FR admin border). (3) GDAL + encode_rgb_dem.py builds hillshade.pmtiles (Mapbox RGB raster-dem, z6-11, clipped to FR admin border) from the same SRTM tiles. (4) `build-grid.py` splits each master archive into a shared low-zoom `base/<layer>.pmtiles` + a 12x8 grid of high-zoom `grid/{col}_{row}/<layer>.pmtiles` for mobile offline (base shared across all routes, grid squares shared across overlapping routes), and `build-routes.py` emits `routes/{id}/pmtiles.json` listing intersecting square coords; `grid.json` + per-route manifests ship with the static site. All hosted on Cloudflare R2 (uploaded via rclone). See `docs/VECTOR_TILES.md` for details.

Website consumes `data/catalog.json` and serves GPX/GeoJSON/elevation profiles as static files. Routes displayed on MapLibre GL JS map with vector tile base (Protomaps-based hiking style, light+dark themes), contour overlay, and GeoJSON trail/POI markers (train stations, bus stops, hotels, campings). Map styles in `website/src/lib/styles/`. The explore page has filters (region, terrain, difficulty) and a suggest panel to find hikes from a departure station by time budget. Detail pages show an interactive SVG elevation chart with hover-synced map markers and POI overlays.
