# TrainRando

Train station-to-station hiking on French GR paths.

## Project Structure

- `pipeline/` -- Python data pipeline (loads curated routes, fetches trail/station/POI data, exports GPX/catalog)
- `pipeline/routes.yaml` -- curated GR route catalog (176 trails with relation IDs and descriptions)
- `website/` -- Astro static site (Leaflet POI map, route list with filters, elevation chart, suggest panel)
- `docs/` -- Project documentation
- Pipeline output: `~/.local/share/open-rando/data/` (shared across worktrees)
- Cache: `~/.cache/open-rando/` (Overpass, SNCF, GTFS, OSRM, SRTM caches, shared across worktrees)

## Stack

- **Pipeline**: Python 3.12+, Shapely, requests, gpxpy, pyyaml
- **Website**: Astro, Leaflet, Tailwind CSS
- **Data sources**: OpenStreetMap Overpass API, SNCF open data, transport.data.gouv.fr GTFS API, OSRM, SRTM elevation tiles

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
- `python -m open_rando --reset` -- clear catalog before processing (default: merge with existing)
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

Website consumes `data/catalog.json` and serves GPX/GeoJSON/elevation profiles as static files. Routes are displayed on a Leaflet map with POI markers (train stations, bus stops, hotels, campings). The explore page has filters (region, terrain, difficulty) and a suggest panel to find hikes from a departure station by time budget. Detail pages show an interactive SVG elevation chart with hover-synced map markers and POI overlays.
