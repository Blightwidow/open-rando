# open-rando

Train station-to-station hiking on French GR paths.

## Project Structure

- `pipeline/` -- Python data pipeline (fetches OSM/SNCF data, computes hike segments, exports GPX/catalog)
- `website/` -- Astro static site (Leaflet map, hike list, GPX download)
- `data/` -- Pipeline output (gitignored)
- `docs/` -- Project documentation

## Stack

- **Pipeline**: Python 3.12+, Shapely, requests, gpxpy
- **Website**: Astro, Leaflet, Tailwind CSS
- **Data sources**: OpenStreetMap Overpass API, SNCF open data, SRTM elevation tiles

## Development

```bash
# Pipeline
cd pipeline && uv sync --all-extras
uv run python -m open_rando

# Website
cd website && bun install && bun run dev
```

## Commands

- `python -m open_rando` -- run pipeline, outputs to `data/`
- `bun run dev` (in website/) -- start dev server
- `bun run build` (in website/) -- build static site to `dist/`

## Code Conventions

- Python: ruff for formatting + linting, mypy for type checking
- TypeScript: Astro defaults (prettier, eslint)
- No abbreviated variable names
- Descriptive names even in loops
- Test behavior not implementation

## Architecture

See `docs/ROADMAP.md` for phased plan, `docs/ARCHITECTURE.md` for algorithm and data model, `docs/DATA_SOURCES.md` for sources and risks.

Pipeline flow: fetch (Overpass + OSM stations, cached) -> match (stations to trail) -> build step graph (8-18km edges) -> DFS maximal hikes -> elevation (SRTM sampling every 50m) -> duration (4km/h flat, 300m/h up, 450m/h down on >= 10% slopes) -> export (GPX with elevation + GeoJSON + elevation profiles + catalog.json)

Website consumes `data/catalog.json` and serves GPX/GeoJSON/elevation profiles as static files. Hikes have 1+ steps, each between two train stations. Detail pages show an interactive SVG elevation chart with timeline.
