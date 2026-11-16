# TODOs

Known work not yet done. Each entry says what is wrong, why it matters, and what "done" looks like. Last audited against the code after the split-pipeline refactor (`8bae50f`).

## Debt

### 1. Dead i18n keys from the removed step planner

`website/src/lib/i18n.ts` carries keys no page or script reads: `filters.maxStep`, `filters.steps`, `filters.difficulty`, `filters.accommodation`, `filters.hotel`, `filters.camping`, `steps.label`, `detail.stepCount`, `detail.steps`, `detail.stations`, `detail.difficulty`, `hike.loop`, `hike.loopFrom`, `map.steps`. `getClientTranslations()` is used only by its own test, and its key list still includes three of the dead keys.

Done when every key is referenced by a page, component or script, and `getClientTranslations` is either used or removed. A test that fails on an unreferenced key would keep it that way.

### 2. Unused packaged data file

`pipeline/src/open_rando/data/gr-descriptions.yaml` (13.7KB) is read by no Python or website file; route descriptions come from `routes.yaml`. Only `docs/ARCHITECTURE.md` mentions it.

Done when the file is either wired in or deleted, and its line removed from the ARCHITECTURE tree.

### 3. Trail gaps are recorded but never shown

`trail_gap_km`, `trail_segment_count` and the profile's `segment_boundaries_km` ship in the catalog (typed in `website/src/lib/catalog.ts`) and nothing renders them. A hiker planning GR 4 cannot see that it has a 19 km unmapped stretch until they are standing in it.

Done when the elevation chart marks the breaks and the route page states the gap, in both locales.

### 4. Constants duplicated across the tile scripts

`PAD_DEG`, `DEFAULT_COLS`, `DEFAULT_ROWS`, `read_makefile_var` and `read_grid_bbox` are copied in `tiles/build-grid.py` and `tiles/build-routes.py`. `grid.json` already carries `grid.bbox`, `cols`, `rows` and `pad_deg`. If the copies drift, route manifests list the wrong squares; the route-vs-grid check catches squares that do not exist, not squares that are wrong.

Done when both scripts take these values from one place: either `tiles/tile_manifests.py` (shared module) or `build-routes.py` reading them from `grid.json` (which then has to be built first).

## Features

### 5. Hiking overlay tiles (water, huts, peaks, power lines)

The Protomaps base lacks features a GR hiker needs: `drinking_water`, `spring`, `shelter`, `alpine_hut`, `viewpoint`, `peak` with elevation, `guidepost`, power lines and towers, `leaf_type` (evergreen vs deciduous), river flow direction. None are drawn today.

Done when `tiles/` builds a France-wide `overlay.pmtiles` with tippecanoe, uploaded to R2, styled in light and dark in `website/src/lib/styles/`, with per-layer toggles and a legend. First check which of these tags the existing extract layers (`Makefile.osm`: trail, stations, accommodation, landmarks, forest) already cover; the rest needs new osmium filters. The manifest schemas already accept extra layers.

### 6. Higher-resolution DEM (IGN RGE ALTI 5m instead of SRTM 30m)

Contours and hillshade come from SRTM 30m, coarse in the Alps and Pyrenees.

Done when `contours.pmtiles` and `hillshade.pmtiles` build from RGE ALTI 5m (open licence), the SRTM path stays as fallback outside coverage, and the size delta on R2 is recorded in `docs/VECTOR_TILES.md`. Mind the 10 GB R2 free tier; `build-grid.py` already caps contours at z13 for that reason.

### 7. LiDAR HD hillshade, corridor pilot

IGN LiDAR HD (1m, open) shows old tracks, terraces and drainage under tree cover. Full France would exceed 10 GB on R2, so scope by corridor.

Done when a ~2 km buffer around a few pilot routes (Alps + Pyrenees GRs) renders to raster hillshade at z13-15, the measured size per route is documented, and a go/no-go for the 176-route rollout is decided from that number. Opt-in layer, off by default.

### 8. MBTiles export for offline apps

Mobile offline ships PMTiles grid squares. Avenza and OsmAnd need MBTiles.

Done when a route page can export its corridor as `.mbtiles` (built client-side from range reads, or prebuilt per route on R2), in both locales. GeoPDF and Garmin are out of scope (server-side tooling).

### 9. Mobile app screenshots on the landing page

The landing page now links the app's latest release (`landing.mobile.*` in `src/lib/i18n.ts`, section in `pages/[...locale]/index.astro`), but shows no visuals: `Blightwidow/open-rando-mobile` has no product screenshots yet, only a banner and icons.

Done when the mobile README carries product screenshots, they are copied into `website/public/` (not hotlinked, so the page stays self-hosted) and shown in the mobile section with localized alt text, in both locales.

### 10. `docs/DEPLOYMENT.md` describes a deploy workflow that does not exist

The doc says GitHub Actions (`.github/workflows/deploy.yml`) deploys on push to `main` from a `data.tar.gz` release. Only `ci.yml` exists; the site is published by `website/deploy.sh` from a local data dir (build, then force-push `dist/` to `gh-pages`). Nothing ties a published site to a reviewed commit, and a data dir missing `grid.json` silently ships a site where the mobile manifests 404.

Done when the doc matches how the site is really published, and either a CI check or the deploy script refuses a build whose `dist/data/` lacks `grid.json` or the per-route manifests.
