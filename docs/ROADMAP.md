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

### Phase 3 -- All GR Paths in France ✓

- [x] Route discovery: Overpass query for all `ref~^GR` relations (GR + GRP)
- [x] MultiLineString gap handling (split at >5km gaps between child relations)
- [x] Cross-route station deduplication (accommodation registry by station code)
- [x] Overpass response caching (already done in phase 2, reused with 60-day TTL)
- [x] Regional bounding box splitting for large station queries (>3° bbox)
- [x] Multi-route CLI orchestration (`--route`, `--dry-run` flags)
- [x] Circular trail detection
- [x] `is_grp` and `is_circular_trail` metadata fields

### Phase 4 -- Polished Website

- [ ] Responsive mobile layout
- [ ] URL-based filter state (shareable links)
- [ ] CI/CD: GitHub Actions -> GitHub Pages
- [ ] SEO meta tags

### Phase 5 -- Stretch Goals

- [ ] "Suggest a hike" from departure station + available time
- [ ] Round-trip hikes (loop trails)
- [ ] SNCF timetable links per station
- [ ] PR (Promenade et Randonnée) paths
- [ ] PWA / offline GPX
- [ ] i18n (FR primary, EN secondary)
