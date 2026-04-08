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

1. **Fetch** a GR hiking relation from Overpass API as GeoJSON geometry
2. **Fetch** train stations near the route bounding box (OSM + SNCF data)
3. **Match** stations to trail: find nearest point on trail with Shapely, keep if < 2km
4. **Order** matched stations by position along the trail (linear referencing)
5. **Slice** segments between station pairs (consecutive + skip-1 where distance < 40km)
6. **Enrich** with SRTM elevation: sample every 50m, compute gain/loss/min/max
7. **Compute** duration (Naismith's rule: 5km/h + 1min per 10m ascent) and difficulty
8. **Export** GPX files, simplified GeoJSON for rendering, and `catalog.json`

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

Build flow: `python -m open_rando` produces data artifacts, then `npm run build` (Astro) consumes them and outputs a deployable `dist/` folder.

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
class Hike:
    id: str                # deterministic hash
    slug: str              # "gr13-fontainebleau-to-bois-le-roi"
    path_ref: str          # "GR 13"
    path_name: str
    osm_relation_id: int
    start_station: Station
    end_station: Station
    distance_km: float
    estimated_duration_min: int
    elevation_gain_m: int
    elevation_loss_m: int
    max_elevation_m: int
    min_elevation_m: int
    difficulty: str        # easy | moderate | hard
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
|   +-- src/open_rando/
|       +-- cli.py              # entry point
|       +-- config.py           # constants (max distance, bbox)
|       +-- models.py           # dataclasses above
|       +-- fetchers/
|       |   +-- overpass.py     # Overpass API client
|       |   +-- stations.py    # SNCF + OSM station fetcher
|       +-- processors/
|       |   +-- match.py       # station-to-trail matching (Shapely)
|       |   +-- slice.py       # segment extraction
|       |   +-- elevation.py   # SRTM .hgt reader
|       |   +-- metadata.py    # duration, difficulty computation
|       +-- exporters/
|           +-- gpx.py         # GPX XML writer
|           +-- geojson.py     # simplified GeoJSON for web
|           +-- catalog.py     # catalog.json writer
+-- website/
|   +-- package.json
|   +-- astro.config.mjs
|   +-- src/
|   |   +-- layouts/Base.astro
|   |   +-- pages/
|   |   |   +-- index.astro        # map + search
|   |   |   +-- hike/[slug].astro  # detail page
|   |   +-- components/
|   |   |   +-- HikeMap.astro
|   |   |   +-- HikeList.astro
|   |   |   +-- HikeCard.astro
|   |   |   +-- ElevationProfile.astro
|   |   |   +-- Filters.astro
|   |   +-- lib/
|   |       +-- catalog.ts
|   |       +-- map.ts
|   +-- public/data/               # copied from pipeline output
+-- data/                          # gitignored
+-- docs/
+-- .github/workflows/build-deploy.yml
```

**Python deps**: `requests`, `shapely`, `geojson`, `gpxpy`, `srtm`
**JS deps**: `astro`, `leaflet`, `tailwindcss`

---

## Phases

### Phase 1 -- Proof of Concept (single GR path)

Scope: GR 13 near Fontainebleau (well-served by Transilien R)

- [ ] Project scaffolding (pyproject.toml, package.json, .gitignore)
- [ ] Overpass fetcher: fetch GR 13 relation, convert to LineString
- [ ] Station fetcher: OSM stations in route bounding box
- [ ] Station-to-trail matching with Shapely
- [ ] Segment slicing between consecutive stations
- [ ] GPX export (no elevation yet)
- [ ] catalog.json export
- [ ] Bare Astro page with Leaflet map showing segments
- [ ] GPX download links

### Phase 2 -- Elevation and Metadata

- [ ] SRTM .hgt tile downloader + reader
- [ ] Elevation profile per segment (sample every 50m)
- [ ] Duration estimation (Naismith's rule)
- [ ] Difficulty classification
- [ ] Elevation in GPX `<ele>` tags
- [ ] Non-consecutive station pairs (A->C, up to 40km)

### Phase 3 -- All GR Paths in France

- [ ] Fetch all `ref=GR*` relations (~300-500)
- [ ] Super-relation resolution (parent with child stages)
- [ ] MultiLineString gap handling
- [ ] Station deduplication (SNCF vs OSM)
- [ ] Overpass response caching + incremental reruns
- [ ] Regional bounding box splitting for large queries

### Phase 4 -- Polished Website

- [ ] Filterable hike list (distance, duration, difficulty, region)
- [ ] Hike detail page with elevation chart
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
| Segment count explosion (N^2 pairs) | Cap at 40km; consecutive + skip-1 only |
| Large static site (many GPX/GeoJSON) | GPX on-demand download; simplify GeoJSON; gzip on CDN |

---

## Open Questions

1. Include RER/metro stations or only mainline SNCF + Transilien?
2. Max walkable distance from station to trail -- 2km default, adjust?
3. Visual style / branding preferences?
