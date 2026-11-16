# TODOs

Known work not yet done. Each entry says what is wrong, why it matters, and what "done" looks like. Last audited against the code after the split-pipeline refactor (`8bae50f`).

## Debt

### 1. Stop maintaining the site twice (FR/EN page forks)

Every page exists twice, with only hardcoded strings differing: `app/route/[slug].astro` vs `en/app/route/[slug].astro` (835/834 lines, 51 differing lines), `app/index.astro` vs `en/app/index.astro` (342/340, 26), `index.astro` vs `en/index.astro` (161/155, 16), plus `about`, `legal` and `privacy`. Every feature has to be written twice and the copies drift.

Done when Astro i18n routing (already declared in `astro.config.mjs`, `prefixDefaultLocale: false`) serves both locales from one template per page, with all copy from `src/lib/i18n.ts`, and the 835-line detail page's inline scripts are split into modules (map setup, section selector, QR code, elevation sync). Blocks TODOs 7, 10 and 11 in practice, since each adds UI.

### 2. README and ARCHITECTURE project tree are out of date

`README.md` was partly fixed (prerequisites, `pipeline` subcommand and flags are current) but still says:

- Leaflet in the diagram, the feature list and the stack table; the site uses `maplibre-gl` + `pmtiles`.
- The diagram and the numbered pipeline steps describe the old single-pass flow with `data/gpx|geojson|elevation/` output; the real flow is `tracks` -> `gtfs` -> `pois` -> `link` -> `catalog` writing `data/tracks/<id>/`, `data/pois/`, `data/links/`.
- No mention of `tiles/`, the `images` subcommand, mobile offline PMTiles, the run report or `osm-index`.

`docs/ARCHITECTURE.md` "Project Structure" lists a pre-split tree: no `commands/`, `processors/link.py`, `processors/trail.py`, `poi_grid.py`, `poi_store.py`, `osm_tags.py`, `fetchers/osm_extract.py`, `fetchers/gtfs_stops_index.py`, `fetchers/landmarks.py`, or the new exporters (`track`, `links`, `pois`, `failures`, `report`, `image_generator`); `cli.py` is described as orchestration; `tiles/` shows only a Makefile.

Done when the README matches current commands, stack and layout and stops duplicating `docs/`, and the ARCHITECTURE tree matches `find pipeline/src tiles website/src`.

### 3. Dead i18n keys from the removed step planner

`website/src/lib/i18n.ts` carries keys no page or script reads: `filters.maxStep`, `filters.steps`, `filters.difficulty`, `filters.accommodation`, `filters.hotel`, `filters.camping`, `steps.label`, `detail.stepCount`, `detail.steps`, `detail.stations`, `detail.difficulty`, `hike.loop`, `hike.loopFrom`, `map.steps`. `getClientTranslations()` is used only by its own test, and its key list still includes three of the dead keys.

Done when every key is referenced by a page, component or script, and `getClientTranslations` is either used or removed. A test that fails on an unreferenced key would keep it that way. Best done together with TODO 1, which rewrites the call sites.

### 4. Unused packaged data file

`pipeline/src/open_rando/data/gr-descriptions.yaml` (13.7KB) is read by no Python or website file; route descriptions come from `routes.yaml`. Only `docs/ARCHITECTURE.md` mentions it.

Done when the file is either wired in or deleted, and its line removed from the ARCHITECTURE tree.

### 5. Trail gaps are recorded but never shown

`trail_gap_km`, `trail_segment_count` and the profile's `segment_boundaries_km` ship in the catalog (typed in `website/src/lib/catalog.ts`) and nothing renders them. A hiker planning GR 4 cannot see that it has a 19 km unmapped stretch until they are standing in it.

Done when the elevation chart marks the breaks and the route page states the gap, in both locales.

### 6. Constants duplicated across the tile scripts

`PAD_DEG`, `DEFAULT_COLS`, `DEFAULT_ROWS`, `read_makefile_var` and `read_grid_bbox` are copied in `tiles/build-grid.py` and `tiles/build-routes.py`. `grid.json` already carries `grid.bbox`, `cols`, `rows` and `pad_deg`. If the copies drift, route manifests list the wrong squares; the route-vs-grid check catches squares that do not exist, not squares that are wrong.

Done when both scripts take these values from one place: either `tiles/tile_manifests.py` (shared module) or `build-routes.py` reading them from `grid.json` (which then has to be built first).

## Features

### 7. Hiking overlay tiles (water, huts, peaks, power lines)

The Protomaps base lacks features a GR hiker needs: `drinking_water`, `spring`, `shelter`, `alpine_hut`, `viewpoint`, `peak` with elevation, `guidepost`, power lines and towers, `leaf_type` (evergreen vs deciduous), river flow direction. None are drawn today.

Done when `tiles/` builds a France-wide `overlay.pmtiles` with tippecanoe, uploaded to R2, styled in light and dark in `website/src/lib/styles/`, with per-layer toggles and a legend. First check which of these tags the existing extract layers (`Makefile.osm`: trail, stations, accommodation, landmarks, forest) already cover; the rest needs new osmium filters. Depends on TODO 1 (toggles written once). The manifest schemas already accept extra layers.

### 8. Higher-resolution DEM (IGN RGE ALTI 5m instead of SRTM 30m)

Contours and hillshade come from SRTM 30m, coarse in the Alps and Pyrenees.

Done when `contours.pmtiles` and `hillshade.pmtiles` build from RGE ALTI 5m (open licence), the SRTM path stays as fallback outside coverage, and the size delta on R2 is recorded in `docs/VECTOR_TILES.md`. Mind the 10 GB R2 free tier; `build-grid.py` already caps contours at z13 for that reason.

### 9. LiDAR HD hillshade, corridor pilot

IGN LiDAR HD (1m, open) shows old tracks, terraces and drainage under tree cover. Full France would exceed 10 GB on R2, so scope by corridor.

Done when a ~2 km buffer around a few pilot routes (Alps + Pyrenees GRs) renders to raster hillshade at z13-15, the measured size per route is documented, and a go/no-go for the 176-route rollout is decided from that number. Opt-in layer, off by default.

### 10. MBTiles export for offline apps

Mobile offline ships PMTiles grid squares. Avenza and OsmAnd need MBTiles.

Done when a route page can export its corridor as `.mbtiles` (built client-side from range reads, or prebuilt per route on R2), in both locales. GeoPDF and Garmin are out of scope (server-side tooling).

### 11. Mobile app download on the landing page

The mobile app ships from `https://github.com/Blightwidow/open-rando-mobile/releases/latest`, but `index.astro` and `en/index.astro` never mention it. The mobile README will soon carry product screenshots.

Done when the landing page has a download section in both locales: screenshots from the mobile README copied into `website/public/` (not hotlinked, so the page stays self-hosted) and a button to the latest release. Copy from `src/lib/i18n.ts`. Depends on TODO 1 and on the screenshots landing in the mobile README first.
