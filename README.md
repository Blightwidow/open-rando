# open-rando

Train station-to-station hiking on French GR paths -- car-free hiking made easy.

A Python pipeline turns open data (OpenStreetMap, SNCF, GTFS feeds, SRTM) into per-route tracks, a France-wide grid of points of interest (train stations, bus stops, hotels, campings), and the links between them. A tile pipeline builds the map layers. An Astro static website shows the routes on a map with filters, elevation profiles, section selection, and GPX download.

## How it works

```
BUILD TIME                                        RUNTIME (static files)
+--------------------------------------------+    +-----------------------------+
| Python pipeline (pipeline/)                |    | Astro static site (website/)|
|                                            |    |                             |
| routes.yaml, OSM extract, SRTM -> tracks   |    |  MapLibre GL JS map         |
| GTFS feeds ----------------------> gtfs    |    |  Route list + filters       |
| OSM extract, SNCF, gtfs ---------> pois    |    |  Elevation chart, sections  |
| tracks + pois -------------------> link    |    |  Train departures, GPX, QR  |
| tracks + links ------------------> catalog |    |                             |
|                                            |    |  catalog.json               |
|    ~/.local/share/open-rando/data/         |    |  tracks/<id>/*              |
|      catalog.json, tracks/, pois/, links/  |    |  pois/*, links/<id>.json    |
+--------------------------------------------+    +-----------------------------+

+--------------------------------------------+    +-----------------------------+
| Tile pipelines (tiles/)                    |    | Cloudflare R2               |
|                                            |    |                             |
| Protomaps daily -> france, world-low       | -> |  france, world-low,         |
| SRTM -> contours, hillshade                |    |  contours, hillshade        |
| masters -> base/ + 12x8 grid/ (offline)    |    |  base/ + grid/ bundles      |
+--------------------------------------------+    +-----------------------------+
```

The pipeline is five stages, each reading what the previous one wrote ([docs/SPLIT_PIPELINE.md](docs/SPLIT_PIPELINE.md)):

1. **`tracks`**: loads the curated GR routes from `routes.yaml` (176 trails with OSM relation IDs), builds the trail geometry from the local OSM extract (Overpass API as fallback, super-relations resolved recursively), samples SRTM elevation every 50m, classifies geography (region, terrain, difficulty). Writes `tracks/<id>/{track.json, trail.geojson, trail.gpx, elevation.json}`, no POIs.
2. **`gtfs`**: downloads every national GTFS feed once and builds a local stop index plus a per-feed departures cache.
3. **`pois`**: builds the France-wide POI grid (12x8 squares, same grid as the mobile tiles): train stations filtered against SNCF data with departures per kind of day, bus stops with GTFS line names, hotels, campings. Writes `pois/<col>_<row>.json` and `pois/index.json`.
4. **`link`**: joins the POIs to each track (train stations within 5 km with a walking-distance junction, bus stops within 2 km, hotels and campings within 3 km). Writes `links/<id>.json`.
5. **`catalog`**: merges tracks and link counts into `catalog.json`, keeping tracks with at least 2 train stations, validates it against its JSON Schema, and writes `run-report.json` (what changed, regression warnings).

## Getting started

### Prerequisites

On macOS, `brew bundle` at the repo root installs every native tool (uv, osmium-tool, gdal, tippecanoe, rclone, bun). Otherwise:

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) (or Node.js)
- [osmium-tool](https://osmcode.org/osmium-tool/) to build the local OSM extracts (required by the `pois` stage; tracks fall back to the Overpass API)

### Run the pipeline

```bash
cd pipeline
uv sync --all-extras
uv run python -m open_rando pipeline
```

The `pois` stage reads the local OSM extract index, so build it first (`make -f Makefile.osm` in `pipeline/`, downloads the ~5 GB France extract once). Each stage also runs alone, see [docs/SPLIT_PIPELINE.md](docs/SPLIT_PIPELINE.md).

Options:

```bash
uv run python -m open_rando pipeline --route "GR 13"   # single route
uv run python -m open_rando pipeline --dry-run          # list routes without processing
uv run python -m open_rando pipeline --retry-failed     # only routes that failed before
uv run python -m open_rando pipeline --skip-gtfs        # reuse the GTFS stop index
```

Other subcommands: `tracks`, `gtfs`, `pois`, `link`, `catalog` (the stages), `osm-index` (build or inspect the local OSM index), `images` (AI hero illustrations per route).

Pipeline output goes to `~/.local/share/open-rando/data/`, cache to `~/.cache/open-rando/`.

### Run the website

```bash
cd website
bun install
bun run dev
```

The dev server copies pipeline data into `public/data/` automatically. Base map tiles come from Cloudflare R2 through `PUBLIC_PMTILES_BASE` (committed in `website/.env.production`); see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

To build for production:

```bash
bun run build
```

Static output goes to `website/dist/`.

### Build the map tiles

The map layers live in `tiles/` (go-pmtiles, GDAL, tippecanoe, rclone). See [docs/VECTOR_TILES.md](docs/VECTOR_TILES.md) for the pipelines and [docs/MOBILE_OFFLINE.md](docs/MOBILE_OFFLINE.md) for the offline grid (`make -f Makefile.routes`).

## Features

- Interactive MapLibre GL JS map with vector tiles, contours, and trail and POI overlays, light and dark themes
- Filter routes by region, terrain and difficulty
- Route detail pages with elevation profile (slope-colored), train stations, and map
- Section selector: pick start and end train stations, view section stats (distance, elevation, duration)
- QR code sharing for selected sections (downloadable or scannable with the companion app)
- GPX download for full routes and selected sections
- Train departures per kind of day (weekday, Saturday, Sunday) at each station
- Bus stops with GTFS line names, hotels and campings along the route
- Bilingual: French (default) and English

## Project structure

```
open-rando/
  pipeline/              Python data pipeline
    src/open_rando/
      cli.py             Entry point
      commands/          One module per subcommand (tracks, gtfs, pois, link, catalog, images, osm-index)
      fetchers/          OSM extract + Overpass, SNCF, GTFS, SRTM, OSRM, POI fetchers
      processors/        Trail assembly, station matching, elevation, geography, linking
      exporters/         Track, GPX, GeoJSON, elevation, POI, link, catalog and report writers
      data/              JSON Schemas for every published file
    routes.yaml          Curated GR route catalog (176 trails)
    Makefile.osm         Local OSM extract download and index
  tiles/                 Tile pipelines (Protomaps extract, contours, hillshade, mobile grid)
  website/               Astro static site
    src/
      pages/             Landing, app (list + map), route detail (FR + EN)
      components/        ElevationChart, RouteCard, RouteFilters, RouteList, SearchableSelect
      layouts/           Base, Landing
      lib/               catalog, POI grid and join, rail service, i18n, map, map styles
  docs/                  Architecture, data sources, deployment, vector tiles, mobile offline
```

## Stack

| Layer | Tech |
|-------|------|
| Pipeline | Python 3.13+, Shapely, requests, gpxpy, pyyaml, jsonschema |
| Website | Astro, MapLibre GL JS, PMTiles, Tailwind CSS, qrcode-generator |
| Tiles | go-pmtiles, GDAL, tippecanoe, PMTiles, Cloudflare R2 |
| Data sources | OpenStreetMap (Geofabrik extracts via osmium, Overpass API fallback), SNCF open data, transport.data.gouv.fr GTFS, OSRM, SRTM elevation tiles, Protomaps |

## Data sources

All data comes from open sources. OpenStreetMap data is under the [ODbL license](https://opendatacommons.org/licenses/odbl/). See [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) for details and risks.

- **Hiking routes**: OpenStreetMap (`route=hiking`, `ref~"^GR"`), from the local extract, Overpass API as fallback
- **Train stations**: OpenStreetMap (`railway=station` / `railway=halt`), filtered for active service via SNCF data
- **Train departures and bus stops**: GTFS feeds from transport.data.gouv.fr
- **Accommodation**: OpenStreetMap (`tourism=hotel|guest_house|hostel|camp_site`)
- **Elevation**: SRTM `.hgt` tiles, sampled every 50m along the trail
- **Base map**: Protomaps daily planet build

## Development

```bash
# Python: format, lint, types, tests
cd pipeline
uv run ruff format .
uv run ruff check .
uv run mypy src/
uv run pytest

# Website: tests, type check
cd website
bun test
bun run astro check
```

Known work not yet done is tracked in [TODOS.md](TODOS.md).

## License

Code and website: [GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)

Data: [ODbL](https://opendatacommons.org/licenses/odbl/) (OpenStreetMap)
