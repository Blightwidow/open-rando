# open-rando Roadmap

> Hikes between French train stations along GR paths -- car-free hiking made easy.

## Overview

**Problem**: Finding hikes accessible by train in France requires cross-referencing trail maps with transit schedules. No tool computes station-to-station hiking segments automatically.

**Solution**: A Python pipeline fetches hiking routes and train station data from open sources, computes walkable segments between stations, enriches them with elevation/metadata, and exports a catalog. An Astro static website displays hikes on a map with GPX download.

**Stack**: Python (pipeline) + Astro (website) + Leaflet (map)

---

## Data Sources

| Source | What | Access |
|--------|------|--------|
| OpenStreetMap via Overpass API | Hiking route relations (`route=hiking`, `ref~"^GR"`) | Free, rate-limited |
| OSM + SNCF open data | Train stations with names, coordinates, transit lines | Free |
| SRTM `.hgt` tiles | Elevation data (3 arc-second / ~90m resolution) | Free download |

**Legal note**: "GR" is a FFRP trademark. We use ODbL-licensed OSM data and frame the product as "hiking between train stations," not as a GR guide. No FFRP logos or blaze reproductions.

---

## Core Algorithm

1. **Fetch** a GR hiking relation from Overpass API (resolves super-relations recursively)
2. **Fetch** train stations near the route bounding box (OSM + SNCF data)
3. **Match** stations to trail: find nearest point on trail with Shapely, keep if < 5km
4. **Order** matched stations by position along the trail (linear referencing)
5. **Build step graph**: compute cumulative distances, create edges between station pairs 8-18km apart
6. **Find hikes**: DFS for all maximal chains through the step graph, deduplicate sub-paths
7. **Enrich** (planned) with SRTM elevation: sample every 50m, compute gain/loss/min/max
8. **Compute** duration estimate (4.5 km/h flat walking speed) per step and total
9. **Export** GPX files (one track per hike, one segment per step), GeoJSON, and `catalog.json`

---

## Architecture

```
BUILD TIME                                    RUNTIME (static files)
+-----------------------------------------+   +----------------------------+
| Python Pipeline                         |   | Astro Static Site          |
|                                         |   |                            |
| Overpass API --+                        |   |  Leaflet Map + List/Filter |
| SNCF data ----+-> fetch -> match ->     |   |         |                  |
| SRTM tiles ---+   slice -> enrich ->    |   |    catalog.json            |
|                    export               |   |    /gpx/{id}.gpx           |
|                      |                  |   |    /geojson/{id}.json      |
|               data/catalog.json         |   +----------------------------+
|               data/gpx/*.gpx            |
|               data/geojson/*.json       |
+-----------------------------------------+
```

Build flow: `cd pipeline && uv run python -m open_rando` produces data artifacts, then `cd website && bun run build` (Astro) consumes them and outputs a deployable `dist/` folder.

---

## Data Model

```python
@dataclass
class Station:
    name: str              # "Fontainebleau-Avon"
    code: str              # SNCF UIC code or OSM node ID
    lat: float
    lon: float
    distance_to_trail_m: float
    transit_lines: list[str]

@dataclass
class HikeStep:
    start_station: Station
    end_station: Station
    distance_km: float
    estimated_duration_minutes: int

@dataclass
class Hike:
    id: str                # deterministic hash
    slug: str              # "gr-13-auxerre-saint-gervais-to-sermizelles-vezelay"
    path_ref: str          # "GR 13"
    path_name: str
    osm_relation_id: int
    start_station: Station # first step's start
    end_station: Station   # last step's end
    steps: list[HikeStep]  # 1+ steps, each 8-18km
    distance_km: float     # sum of step distances
    estimated_duration_min: int
    elevation_gain_m: int  # planned
    elevation_loss_m: int  # planned
    max_elevation_m: int   # planned
    min_elevation_m: int   # planned
    difficulty: str        # planned
    bbox: tuple[float, float, float, float]
    region: str
    departement: str
    gpx_path: str
    geojson_path: str
    is_reversible: bool
    last_updated: str
```

---

## Project Structure

```
open-rando/
+-- pipeline/
|   +-- pyproject.toml
|   +-- uv.lock
|   +-- src/open_rando/
|       +-- __init__.py
|       +-- __main__.py
|       +-- cli.py              # entry point
|       +-- config.py           # constants (step distances, API config)
|       +-- models.py           # Station, HikeStep, Hike dataclasses
|       +-- fetchers/
|       |   +-- overpass.py     # Overpass API client (super-relation resolution)
|       |   +-- stations.py    # OSM station fetcher
|       +-- processors/
|       |   +-- match.py       # station-to-trail matching (Shapely)
|       |   +-- slice.py       # step graph + DFS hike finder
|       +-- exporters/
|           +-- gpx.py         # GPX writer (multi-segment tracks)
|           +-- geojson.py     # GeoJSON FeatureCollection per hike
|           +-- catalog.py     # catalog.json writer
+-- website/
|   +-- package.json
|   +-- bun.lock
|   +-- astro.config.mjs
|   +-- tailwind.config.mjs
|   +-- src/
|   |   +-- layouts/Base.astro
|   |   +-- pages/
|   |   |   +-- index.astro             # map + filters + hike list
|   |   |   +-- hike/[slug].astro       # detail page
|   |   +-- components/
|   |   |   +-- HikeMap.astro           # Leaflet map (filter-aware)
|   |   |   +-- HikeList.astro
|   |   |   +-- HikeCard.astro          # clickable card linking to detail
|   |   |   +-- HikeFilters.astro       # range sliders
|   |   +-- lib/
|   |       +-- catalog.ts              # types + data loading
|   +-- public/data/                    # copied from pipeline output at build
+-- data/                               # gitignored pipeline output
+-- docs/
```

**Python deps**: `requests`, `shapely`, `gpxpy`
**JS deps**: `astro`, `leaflet`, `tailwindcss`

---

## Phases

### Phase 1 -- Proof of Concept (single GR path) ✓

Scope: GR 13 (Fontainebleau to Morvan)

- [x] Project scaffolding (pyproject.toml, package.json, .gitignore)
- [x] Overpass fetcher: fetch GR 13 super-relation, resolve child relations into LineString
- [x] Station fetcher: OSM stations in route bounding box
- [x] Station-to-trail matching with Shapely (< 5km threshold)
- [x] Multi-step hike generation: step graph (8-18km per step) + DFS maximal path finder
- [x] GPX export (multi-segment tracks, no elevation yet)
- [x] GeoJSON export (one feature per step)
- [x] catalog.json export with step metadata
- [x] Astro site: Leaflet map + hike cards on index page
- [x] Filter sliders (distance, duration, max step length, step count) synced with map
- [x] Hike detail page with step breakdown, station list, and dedicated map
- [x] GPX download links

### Phase 2 -- Elevation and Metadata

- [ ] SRTM .hgt tile downloader + reader
- [ ] Elevation profile per segment (sample every 50m)
- [ ] Duration estimation (Naismith's rule: replace flat 4.5km/h)
- [ ] Difficulty classification
- [ ] Elevation in GPX `<ele>` tags
- [ ] Elevation chart on hike detail page

### Phase 3 -- All GR Paths in France

- [ ] Fetch all `ref=GR*` relations (~300-500)
- [ ] MultiLineString gap handling
- [ ] Station deduplication (SNCF vs OSM)
- [ ] Overpass response caching + incremental reruns
- [ ] Regional bounding box splitting for large queries

### Phase 4 -- Polished Website

- [ ] Responsive mobile layout
- [ ] URL-based filter state (shareable links)
- [ ] CI/CD: GitHub Actions -> GitHub Pages
- [ ] SEO meta tags

### Phase 5 -- Stretch Goals

- [ ] "Suggest a hike" from departure station + available time
- [ ] Round-trip hikes (loop trails)
- [ ] SNCF timetable links per station
- [ ] GRP and PR paths
- [ ] PWA / offline GPX
- [ ] i18n (FR primary, EN secondary)

---

## Key Risks

| Risk | Mitigation |
|------|------------|
| OSM data gaps in GR relations | Geometry repair; skip broken segments with warnings |
| Overpass API rate limits / timeouts | Regional bbox splitting; cache responses; fallback to Geofabrik PBF |
| FFRP trademark on "GR" | Frame as "hiking between stations"; no logo reproduction; disclaimer |
| Hike count explosion from DFS | Sub-path deduplication; step distance range (8-18km) limits branching |
| Large static site (many GPX/GeoJSON) | GPX on-demand download; simplify GeoJSON; gzip on CDN |

---

## Open Questions

1. Include RER/metro stations or only mainline SNCF + Transilien?
2. Max walkable distance from station to trail -- 2km default, adjust?
3. Visual style / branding preferences?
