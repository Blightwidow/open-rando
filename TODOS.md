# TODOs

Known work not yet done. Each entry says what is wrong, why it matters, and what "done" looks like. Last audited against the code after the split-pipeline refactor (`8bae50f`).

## Debt

### 1. Higher-resolution DEM (IGN RGE ALTI 5m instead of SRTM 30m)

Contours and hillshade come from SRTM 30m, coarse in the Alps and Pyrenees.

Done when `contours.pmtiles` and `hillshade.pmtiles` build from RGE ALTI 5m (open licence), the SRTM path stays as fallback outside coverage, and the size delta on R2 is recorded in `docs/VECTOR_TILES.md`. Mind the 10 GB R2 free tier; `build-grid.py` already caps contours at z13 for that reason.

### 2. LiDAR HD hillshade, corridor pilot

IGN LiDAR HD (1m, open) shows old tracks, terraces and drainage under tree cover. Full France would exceed 10 GB on R2, so scope by corridor.

Done when a ~2 km buffer around a few pilot routes (Alps + Pyrenees GRs) renders to raster hillshade at z13-15, the measured size per route is documented, and a go/no-go for the 176-route rollout is decided from that number. Opt-in layer, off by default.

### 3. MBTiles export for offline apps

Mobile offline ships PMTiles grid squares. Avenza and OsmAnd need MBTiles.

Done when a route page can export its corridor as `.mbtiles` (built client-side from range reads, or prebuilt per route on R2), in both locales. GeoPDF and Garmin are out of scope (server-side tooling).

### 4. Mobile app screenshots on the landing page

The landing page now links the app's latest release (`landing.mobile.*` in `src/lib/i18n.ts`, section in `pages/[...locale]/index.astro`), but shows no visuals: `Blightwidow/open-rando-mobile` has no product screenshots yet, only a banner and icons.

Done when the mobile README carries product screenshots, they are copied into `website/public/` (not hotlinked, so the page stays self-hosted) and shown in the mobile section with localized alt text, in both locales.
