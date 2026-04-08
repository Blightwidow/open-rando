# Data Sources

## Sources

| Source | What | Access |
|--------|------|--------|
| OpenStreetMap via Overpass API | Hiking route relations (`route=hiking`, `ref~"^GR"`) | Free, rate-limited |
| OSM + SNCF open data | Train stations with names, coordinates, transit lines | Free |
| SRTM `.hgt` tiles | Elevation data (3 arc-second / ~90m resolution) | Free download |

---

## Legal Notes

"GR" is a FFRP trademark. We use ODbL-licensed OSM data and frame the product as "hiking between train stations," not as a GR guide. No FFRP logos or blaze reproductions.

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
2. Max walkable distance from station to trail -- currently 5km, adjust?
3. Visual style / branding preferences?
