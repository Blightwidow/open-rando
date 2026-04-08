# open-rando

Train station-to-station hiking on French GR paths -- car-free hiking made easy.

A Python pipeline fetches hiking routes and train station data from open sources, computes walkable multi-step hikes between stations, and exports a catalog. An Astro static website displays hikes on a map with filters and GPX download.

## How it works

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| Overpass API --+                        |   |  Leaflet Map + List/Filter |
| OSM stations --+-> fetch -> match ->    |   |         |                  |
| SRTM tiles ---+   step graph -> DFS ->  |   |    catalog.json            |
|                    export               |   |    /gpx/{id}.gpx           |
|               data/catalog.json         |   |    /geojson/{id}.json      |
|               data/gpx/*.gpx            |   +----------------------------+
|               data/geojson/*.json       |
+-----------------------------------------+
```

The pipeline:

1. Fetches a GR hiking relation from the Overpass API (resolves super-relations recursively)
2. Fetches active train stations near the route (filters out disused/abandoned)
3. Matches stations to the trail using Shapely (keeps those within 5km)
4. Builds a step graph with edges between station pairs 8-18km apart
5. Finds all maximal hike chains via DFS, deduplicates sub-paths
6. Fetches nearby accommodation (hotel, guest house, hostel, camping) for each station
7. Exports GPX files, GeoJSON, and a `catalog.json` consumed by the website

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

This fetches data from OpenStreetMap and writes output to `data/`.

### Run the website

```bash
cd website
bun install
bun run dev
```

The dev server copies `data/` into `public/data/` automatically.

To build for production:

```bash
bun run build
```

Static output goes to `website/dist/`.

## Features

- Interactive Leaflet map with trail visualization
- Filter hikes by distance, duration, step count, and max step length
- Filter by accommodation: show only hikes where every overnight stop has a hotel or camping
- Hike detail pages with step breakdown, station list, and dedicated map
- GPX download for each hike
- Only active train stations (disused/abandoned filtered out)
- Accommodation info (hotel/camping) displayed per station

## Project structure

```
open-rando/
  pipeline/           Python data pipeline
    src/open_rando/
      cli.py           Entry point
      config.py        Constants (step distances, API config, search radius)
      models.py        Station, Accommodation, HikeStep, Hike dataclasses
      fetchers/        Overpass API, station fetcher, accommodation fetcher
      processors/      Station-to-trail matching, step graph + DFS
      exporters/       GPX, GeoJSON, catalog.json writers
  website/            Astro static site
    src/
      pages/           Index (map + filters + list) and hike detail
      components/      HikeMap, HikeCard, HikeFilters, HikeList
      lib/catalog.ts   TypeScript types + data loading
  data/               Pipeline output (gitignored)
  docs/               Architecture, data sources, roadmap
```

## Stack

| Layer | Tech |
|-------|------|
| Pipeline | Python 3.13+, Shapely, requests, gpxpy |
| Website | Astro, Leaflet, Tailwind CSS |
| Data sources | OpenStreetMap Overpass API, SNCF open data, SRTM elevation tiles |

## Data sources

All data comes from open sources under the [ODbL license](https://opendatacommons.org/licenses/odbl/).

- **Hiking routes**: OpenStreetMap via Overpass API (`route=hiking`, `ref~"^GR"`)
- **Train stations**: OpenStreetMap (`railway=station` / `railway=halt`), filtered for active service
- **Accommodation**: OpenStreetMap (`tourism=hotel|guest_house|hostel|camp_site`) within 2km of each station
- **Elevation** (planned): SRTM `.hgt` tiles

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

Data: [ODbL](https://opendatacommons.org/licenses/odbl/) (OpenStreetMap)
