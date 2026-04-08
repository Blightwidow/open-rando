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

See `docs/ROADMAP.md` for full architecture, data model, and phased plan.

Pipeline flow: fetch (Overpass + SNCF) -> match (stations to trails) -> slice (segments) -> enrich (elevation) -> export (GPX + GeoJSON + catalog.json)

Website consumes `data/catalog.json` and serves GPX/GeoJSON as static files.
