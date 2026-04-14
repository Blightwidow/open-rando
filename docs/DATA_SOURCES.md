# Data Sources

## Sources

| Source | What | Access | Caching |
|--------|------|--------|---------|
| OpenStreetMap via Overpass API | Trail geometry (fetched by relation ID from `routes.yaml`), stations, accommodation POIs | Free, rate-limited | Disk cache, 30-60 day TTL |
| SNCF gares-de-voyageurs | Train station reference data (UIC codes, names, coordinates) for filtering | Free, no auth | Disk cache, 30-day TTL |
| transport.data.gouv.fr GTFS API | Bus stop locations, route names, timetable feed URLs | Free, public API | Disk cache, 30-day TTL |
| OSRM public router | Pedestrian routing for station-to-trail walking connectors | Free, rate-limited | Disk cache, 90-day TTL |
| SRTM `.hgt` tiles via AWS Skadi | Elevation data (1 or 3 arc-second resolution) | Free, no auth | Permanent disk cache |

### SRTM Details

Tiles are downloaded from `https://elevation-tiles-prod.s3.amazonaws.com/skadi/` (AWS open data mirror, gzip-compressed). Each tile covers 1°x1°, named by SW corner (e.g., `N47E003.hgt`). File size determines resolution: SRTM1 (3601x3601, ~25MB) or SRTM3 (1201x1201, ~2.8MB). Elevation is read via bilinear interpolation of the 4 surrounding grid points. Void values (-32768) are treated as missing data.

---

## Legal Notes

"GR" is a FFRP trademark. We use ODbL-licensed OSM data and frame the product as "hiking between train stations," not as a GR guide. No FFRP logos or blaze reproductions.

---

## Key Risks

| Risk | Mitigation |
|------|------------|
| OSM data gaps in GR relations | Geometry repair; skip broken segments with warnings |
| Overpass API rate limits / timeouts | Disk-cached responses (30-60 day TTL); retry with exponential backoff; regional bbox splitting for station queries >3° |
| FFRP trademark on "GR" | Frame as "hiking between stations"; no logo reproduction; disclaimer |
| GTFS feed availability | Some bus networks may not publish GTFS data; bus stops without GTFS enrichment show raw OSM names |
| OSRM public server rate limits | 1s cooldown between requests; disk cache (90-day TTL); fallback to straight-line distance |
| Large static site (many GPX/GeoJSON) | GPX on-demand download; simplify GeoJSON; gzip on CDN |

---

## Open Questions

1. Include RER/metro stations or only mainline SNCF + Transilien?
2. Max walkable distance from station to trail -- currently 5km, adjust?
