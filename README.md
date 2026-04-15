# open-rando

Train station-to-station hiking on French GR paths -- car-free hiking made easy.

A Python pipeline fetches hiking routes, train stations, bus stops, and elevation data from open sources, then exports a catalog. An Astro static website displays routes on a map with filters, elevation profiles, section selection, and GPX download.

## How it works

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| Overpass API --+                        |   |  Leaflet Map + List/Filter |
| SNCF stations -+-> fetch -> match ->   |   |  Elevation chart           |
| GTFS bus data --+   geography ->        |   |  Section selector + QR     |
| SRTM tiles ----+    elevation ->        |   |         |                  |
|                      export             |   |    catalog.json            |
|               data/catalog.json         |   |    /gpx/{id}.gpx           |
|               data/gpx/*.gpx            |   |    /geojson/{id}.json      |
|               data/geojson/*.json       |   |    /elevation/{id}.json    |
|               data/elevation/*.json     |   +----------------------------+
+-----------------------------------------+
```

The pipeline:

1. Loads curated GR routes from `routes.yaml` (176 trails with OSM relation IDs)
2. Fetches trail geometry from the Overpass API (resolves super-relations recursively)
3. Fetches active train stations near the route (OSM + SNCF filtering)
4. Matches stations to the trail using Shapely
5. Fetches bus stops with GTFS enrichment (route names from transport.data.gouv.fr)
6. Fetches nearby accommodation (hotel, guest house, hostel, camping) for each station
7. Samples elevation from SRTM tiles every 50m, classifies geography (region, terrain, difficulty)
8. Exports GPX files, GeoJSON, elevation profiles, and a `catalog.json` consumed by the website

## Getting started

### Prerequisites

- Python 3.13+ with [uv](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/) (or Node.js)

### Run the pipeline

```bash
cd pipeline
uv sync --all-extras
uv run python -m open_rando
```

Options:

```bash
uv run python -m open_rando --route "GR 13"   # single route
uv run python -m open_rando --dry-run          # list routes without processing
uv run python -m open_rando --reset            # clear catalog before processing
```

Pipeline output goes to `~/.local/share/open-rando/data/`, cache to `~/.cache/open-rando/`.

### Run the website

```bash
cd website
bun install
bun run dev
```

The dev server copies pipeline data into `public/data/` automatically.

To build for production:

```bash
bun run build
```

Static output goes to `website/dist/`.

## Features

- Interactive Leaflet map with trail visualization and POI overlays
- Filter routes by region and terrain type
- Route detail pages with elevation profile (slope-colored), station list, and map
- Section selector: pick start/end train stations, view section stats (distance, elevation, duration)
- QR code sharing for selected sections (downloadable or scannable with companion app)
- GPX download for full routes and selected sections
- Bus stop display with GTFS route names
- Accommodation info (hotel/camping) per station
- Bilingual: French (default) and English

## Project structure

```
open-rando/
  pipeline/              Python data pipeline
    src/open_rando/
      cli.py             Entry point
      config.py          Constants (API config, search radius)
      fetchers/          Overpass, SNCF, GTFS, SRTM, POI fetchers
      processors/        Station matching, elevation, geography, slicing
      exporters/         GPX, GeoJSON, elevation, catalog writers
    routes.yaml          Curated GR route catalog (176 trails)
  website/               Astro static site
    src/
      pages/             Landing, app (list + map), route detail (FR + EN)
      components/        ElevationChart, RouteCard, RouteFilters, RouteList, SearchableSelect
      lib/               catalog.ts, i18n.ts, elevation.ts, route-filters.ts
  docs/                  Architecture, data sources, deployment
```

## Stack

| Layer | Tech |
|-------|------|
| Pipeline | Python 3.13+, Shapely, requests, gpxpy, pyyaml |
| Website | Astro, Leaflet, Tailwind CSS, qrcode-generator |
| Data sources | OpenStreetMap Overpass API, SNCF open data, transport.data.gouv.fr GTFS, OSRM, SRTM elevation tiles |

## Data sources

All data comes from open sources under the [ODbL license](https://opendatacommons.org/licenses/odbl/).

- **Hiking routes**: OpenStreetMap via Overpass API (`route=hiking`, `ref~"^GR"`)
- **Train stations**: OpenStreetMap (`railway=station` / `railway=halt`), filtered for active service via SNCF data
- **Bus stops**: OpenStreetMap, enriched with route names from GTFS feeds (transport.data.gouv.fr)
- **Accommodation**: OpenStreetMap (`tourism=hotel|guest_house|hostel|camp_site`) near the trail
- **Elevation**: SRTM `.hgt` tiles, sampled every 50m along the trail

## Development

```bash
# Lint and format (Python)
cd pipeline
uv run ruff check src/
uv run ruff format src/

# Type check
uv run mypy src/
```

## License

Code and website: [GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)

Data: [ODbL](https://opendatacommons.org/licenses/odbl/) (OpenStreetMap)
