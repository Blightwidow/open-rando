# open-rando

Train station-to-station hiking on French GR paths.

## Project Structure

- `pipeline/` -- Python data pipeline (fetches OSM/SNCF data, computes hike segments, exports GPX/catalog)
- `website/` -- Astro static site (Leaflet map, hike list, GPX download)
- `docs/` -- Project documentation
- Pipeline output: `~/.local/share/open-rando/data/` (shared across worktrees)
- Cache: `~/.cache/open-rando/` (Overpass responses + SRTM tiles, shared across worktrees)

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

- `python -m open_rando` -- run pipeline for all GR routes, outputs to `data/`
- `python -m open_rando --route "GR 13"` -- run pipeline for a single route
- `python -m open_rando --dry-run` -- list discovered routes without processing
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

Pipeline flow: discover routes (Overpass `ref~^GR`) -> for each route: fetch trail (superroute recursion, cached) -> fetch stations (bbox splitting for large trails) -> match (stations to trail, MultiLineString support) -> build step graph (8-18km edges) -> longest-path DP per connected component -> elevation (SRTM sampling every 50m) -> duration (4km/h flat, 300m/h up, 450m/h down on >= 10% slopes) -> export (GPX with elevation + GeoJSON + elevation profiles) -> final catalog.json with all routes

Website consumes `data/catalog.json` and serves GPX/GeoJSON/elevation profiles as static files. Hikes have 1+ steps, each between two train stations. Detail pages show an interactive SVG elevation chart with timeline and a section selector (for multi-step hikes) that lets users pick a sub-range of steps with reactive stats, map highlighting, elevation overlay, and section GPX download.
