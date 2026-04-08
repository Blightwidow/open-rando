# Roadmap

> Hikes between French train stations along GR paths -- car-free hiking made easy.

## Overview

**Problem**: Finding hikes accessible by train in France requires cross-referencing trail maps with transit schedules. No tool computes station-to-station hiking segments automatically.

**Solution**: A Python pipeline fetches hiking routes and train station data from open sources, computes walkable multi-step hikes between stations, and exports a catalog. An Astro static website displays hikes on a map with filters and GPX download.

**Stack**: Python (pipeline) + Astro (website) + Leaflet (map)

See also: [Architecture](ARCHITECTURE.md) | [Data Sources](DATA_SOURCES.md)

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

### Phase 2 -- Elevation and Metadata ✓

- [x] SRTM .hgt tile downloader + reader
- [x] Elevation profile per segment (sample every 50m)
- [x] Duration estimation (Naismith's rule: replace flat 4.5km/h)
- [x] Difficulty classification
- [x] Elevation in GPX `<ele>` tags
- [x] Elevation chart on hike detail page

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
