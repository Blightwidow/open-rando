# Decisions

Why the pipeline's thresholds and structural choices are what they are. Each entry names where the value lives, so a change updates both the code and this page. When a reason was never recorded, the entry says so: verify on real routes before changing it.

## Product thresholds

| Decision | Value | Where | Why |
|---|---|---|---|
| A route needs at least this many train stations to enter the catalog | 2 | `config.MIN_TRAIN_STATIONS_PER_ROUTE` | The product is station-to-station hiking: with fewer than two you cannot arrive and leave by train. |
| Train station linked to a trail | < 5 km | `config.MAX_STATION_DISTANCE_METERS` | Roughly one hour's walk to reach the trail. Walking distance is then refined with OSRM (`processors/match.py`). |
| Bus stop linked to a trail | < 2 km | `config.MAX_BUS_STOP_DISTANCE_METERS` | Bus stops are dense; a wider radius floods the map. Reason for the exact value not recorded. |
| Hotel / camping linked to a trail | < 3 km | `fetchers/pois.POI_ACCOMMODATION_RADIUS_METERS` | A detour a hiker accepts at the end of a day. Exact value not recorded. |
| Food shop / eatery linked to a trail | < 1.5 km | `fetchers/pois.POI_RESUPPLY_RADIUS_METERS` | A midday detour, shorter than an overnight one. Exact value not recorded. |
| GTFS stop matched to an OSM bus stop | 150 m | `config.GTFS_MATCH_RADIUS_METERS` | A pole and its GTFS stop are usually a few metres apart. |
| GTFS stop matched to an OSM train station | 500 m | `config.TRAIN_GTFS_MATCH_RADIUS_METERS` | Stations sprawl (several platforms, operators), so their GTFS stops sit further from the OSM node. |
| Days sampled per kind of day for departures | 4 | `fetchers/gtfs.CANDIDATE_DATES_PER_DAY_TYPE` | Timetables change with seasons and works; one sampled date reports "no service" for a line that resumes a fortnight later. |

## Elevation and difficulty

| Decision | Value | Where | Why |
|---|---|---|---|
| Elevation sample spacing | 50 m | `config.ELEVATION_SAMPLE_INTERVAL_METERS` | Close to SRTM resolution (30 m or 90 m tiles); finer sampling only adds interpolated points. |
| Ignored elevation run | ≤ 5 m before the direction reverses | `processors/elevation.ELEVATION_NOISE_THRESHOLD_METERS` | SRTM noise otherwise inflates total ascent on flat ground; real climbs still count in full. |
| Walking time | 4 km/h under 10 % slope; steeper stretches timed by height: 300 m/h up, 450 m/h down | `processors/elevation.py` | On steep ground vertical speed limits a hiker, not horizontal pace. Exact rates not recorded. |
| Difficulty bands | < 15 / < 30 / < 50 / ≥ 50 m of ascent per km; easy under 300 m total | `processors/elevation.py` | Steepness per km, with a floor so a short steep route is not "difficult". Band edges not recorded. |
| Forest terrain | ≥ 40 % of 20 sample points inside forest | `processors/geography.py` | Cheap point-in-polygon sampling instead of exact intersection. |

## Trail assembly

| Decision | Value | Where | Why |
|---|---|---|---|
| Gap that splits a trail into segments | ~5 km (0.05°) | `processors/trail_assembly.MAX_CHAIN_GAP_DEGREES` | Smaller gaps are bridged; larger ones are real breaks in the OSM relation and shown as gaps. |
| Spurious fragment dropped | < 10 km and < 5 % of the longest segment; or short (< 10 km or < 5 %) and > 25 km from it | `processors/trail_assembly.py` | Stubs and other trails' fragments collected by GR relations otherwise appear as extra segments. Fragments in between are kept as the trail continuing after a gap. |
| Branch detection | both ends within 1 km of the main line, < 50 % of the route | `processors/trail_assembly.py` | Testing the ends (not the closest approach) separates a branch from a coastal path that rounds a peninsula. |

## Regression warnings (run report)

| Decision | Value | Where | Why |
|---|---|---|---|
| Distance drop warning | > 10 % | `exporters/report.DISTANCE_DROP_WARNING_RATIO` | OSM relations get vandalised, split or partly deleted; a silent shrink looks like success otherwise. |
| Elevation drop warning | > 20 % | `exporters/report.ELEVATION_DROP_WARNING_RATIO` | Elevation is noisier than distance, so the bar is higher. |
| Gap growth warning | > 1 km | `exporters/report.GAP_GROWTH_WARNING_KM` | More gap length means ways went missing from the relation. |

## Structure

- **Local OSM extract is required.** Every OSM query reads `extract-index.sqlite` (`fetchers/osm_source.py`). Overpass replaces it only when no index exists and `OPEN_RANDO_ALLOW_OVERPASS=1` is set, for development: the public API answers 504 under load, and switching source per query made results depend on which layers happened to be built. One exception: trail relations that cross the border are incomplete in the France extract, so the local source fetches those relations (and only those) from Overpass and the run report lists them (`inputs.tracks.osm.border_fallback_relations`).
- **Walking distances come from a local OSRM.** The public demo server (`router.project-osrm.org`) is rate limited and not meant for bulk use. See `pipeline/Makefile.osrm`. When the router is down, `link` stops instead of keeping crow-fly junctions: a silently degraded route is worse than a failed run.
- **Grid of 12x8 squares over France** (`poi_grid.py`) is shared by POIs and mobile tiles, so one download serves both.
- **Tile scripts stay outside the `open_rando` package.** `tiles/*.py` are `uv run --script` files with inline dependencies: they drive GDAL, tippecanoe and go-pmtiles, which the pipeline does not need, and they run on a different cadence (once per OSM snapshot, not once per catalog run). `test_overlay_features.py` runs in the CI `tiles` job; `tile_manifests.py` is tested from `pipeline/tests/test_tile_manifests.py`.
- **Input versions are recorded, not pinned.** Caches expire (Overpass 30–60 days, GTFS and SNCF 30 days, OSRM 90 days), so two runs can differ without a code change. Each stage writes what it read to `run-inputs.json` and the catalog copies it into `run-report.json`, so a diff can be traced to its cause.
- **Data contract has one source.** The JSON Schemas in `pipeline/src/open_rando/data/` are the contract. TypeScript types for the website are generated from them (`website/scripts/generate-types.mjs`); CI fails when the generated file is stale.
