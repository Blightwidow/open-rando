# Data Sources

## Sources

| Source | What | Access | Caching |
|--------|------|--------|---------|
| OpenStreetMap Geofabrik extract (`france-latest.osm.pbf`) | Trail geometry, stations, bus stops, accommodation, landmarks, forest areas | Free, one ~5GB download | Local SQLite index, rebuilt on demand |
| OpenStreetMap via Overpass API | Same data, used only for layers absent from the local index | Free, rate-limited | Disk cache, 30-60 day TTL |
| SNCF gares-de-voyageurs | Train station reference data (UIC codes, names, coordinates) for filtering | Free, no auth | Disk cache, 30-day TTL |
| transport.data.gouv.fr GTFS API | Bus stop locations, route names, timetable feed URLs, train departures (first/last train and train count per kind of day) | Free, public API | Disk cache, 30-day TTL, keyed per reference month |
| OSRM public router | Pedestrian routing for station-to-trail walking connectors | Free, rate-limited | Disk cache, 90-day TTL |
| SRTM `.hgt` tiles via AWS Skadi | Elevation data (1 or 3 arc-second resolution) | Free, no auth | Permanent disk cache |

### Local OSM Extracts

The public Overpass API answers with 429/504 under load, and every OSM query the pipeline makes is a plain tag filter over France. `pipeline/Makefile.osm` downloads `france-latest.osm.pbf` from Geofabrik once, splits it into five per-layer extracts with `osmium tags-filter`, and `python -m open_rando osm-index` turns those into `~/.cache/open-rando/osm/extract-index.sqlite`:

| Layer | Extract | Read by |
|-------|---------|---------|
| `stations` | `n/railway=station,halt`, `n/highway=bus_stop`, `n/public_transport=platform` | `fetchers/stations.py` |
| `accommodation` | `nw/tourism=hotel,guest_house,hostel,camp_site` | `fetchers/pois.py` |
| `landmarks` | `nw/historic`, `nw/tourism`, `nw/natural`, `nw/man_made` (kinds in `osm_tags.py`) | `fetchers/landmarks.py` |
| `forest` | `w/landuse=forest`, `w/natural=wood`, plus multipolygon members | `processors/geography.py` |
| `trails` | `r/route=hiking,foot --add-referenced` | `fetchers/overpass.py` |

Queries return Overpass-shaped JSON, so the parsers are shared by both paths and the tag vocabulary lives in `open_rando/osm_tags.py` to keep the selectors identical. Each layer is optional: a fetcher whose layer is missing (or a relation absent from the index) calls Overpass as before. `python -m open_rando osm-index --status` reports the feature count, source file and build time per layer.

Each layer records the bounding box declared in its PBF header. A bbox query reaching outside that box would silently return too few features, so those queries fall back to Overpass instead — a regional extract (`PBF_URL=.../bourgogne-latest.osm.pbf`) therefore serves its own region and leaves the rest to the API. Extracts with no header bbox are trusted for any query.

Requires `osmium-tool` and the `osm` extra (`uv sync --extra osm`) for pyosmium. `brew bundle` at the repo root installs every native tool.

### GTFS Departure Details

Train station departures come from the GTFS feeds published on transport.data.gouv.fr, not from a journey planner. For each train station the pipeline matches nearby GTFS stops (within 500m, since a station spans several platforms and operators), then walks `stop_times.txt` once per feed to aggregate, per kind of day (weekday, Saturday, Sunday): the earliest departure, the latest departure, and how many departures run.

Two rules keep the numbers meaningful:

- Only rail routes count (`route_type` 2, or 100-117 in the extended set), so a city bus stop within 500m of the station cannot inflate its train count.
- Each kind of day is sampled on real calendar dates — the next four Wednesdays, Saturdays and Sundays from the start of the current week — with `calendar.txt` validity ranges and weekly flags plus `calendar_dates.txt` additions and cancellations applied per date. The busiest sampled date wins, and its date is kept in `sample_date`. A trip is therefore counted once per kind of day, even when a feed spreads its timetable over many overlapping calendars, and a line closed this week for works or a seasonal gap still reports its normal timetable.

Known approximations:

- Only the next four weeks are sampled: a station whose service resumes later than that reports no departures.
- The busiest sampled date can be an atypically busy one (an event day, or the first day of a new timetable).
- Feeds are parsed and cached per week, so departures refresh weekly rather than daily.
- Times past midnight keep GTFS hours above 24 (a `25:10` departure belongs to the previous service day) and are wrapped only for display.
- These are indicative figures for planning, not a live timetable. The site links to the SNCF timetable page of each station for the schedule of the day.

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
| GTFS feed availability | Some bus networks may not publish GTFS data; bus stops without GTFS enrichment show raw OSM names. Train stations with no GTFS match carry no departure data and simply show no times. |
| GTFS feed size | National rail feeds hold millions of `stop_times.txt` rows; they are streamed row by row, aggregated per stop, and cached per feed and reference month so a run parses each feed at most once |
| Silent data regressions | Every run writes `data/run-report.json` comparing the catalog before and after, and warns when a route shrinks, loses train stations, or loses elevation gain |
| Contract drift with the mobile client | `catalog.json` is validated against `src/open_rando/data/catalog.schema.json` before it is written; new fields must be added as optional |
| Local extracts going stale | The index is a snapshot: rebuild it (`make -f Makefile.osm extracts index`) when route or station data looks out of date; `osm-index --status` shows each layer's build time and coverage |
| Partial extract used by mistake | Layer coverage comes from the PBF header bbox; queries outside it fall back to Overpass rather than returning half the stations |
| `osmium-tool` not installed | `make -f Makefile.osm check` fails fast with the install command; without an index the pipeline falls back to Overpass |
| OSRM public server rate limits | 1s cooldown between requests; disk cache (90-day TTL); fallback to straight-line distance |
| Large static site (many GPX/GeoJSON) | GPX on-demand download; simplify GeoJSON; gzip on CDN |

---

## Open Questions

1. Include RER/metro stations or only mainline SNCF + Transilien?
2. Max walkable distance from station to trail -- currently 5km, adjust?
