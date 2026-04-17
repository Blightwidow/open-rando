# Vector Tile Map

Self-hosted vector tiles serving world coverage + France detail from a single PMTiles file, plus separate contour overlay. Replaces prior raster OSM base + contour overlay architecture.

## Status

| Stage | Status |
|-------|--------|
| A. Protomaps regional extract | Complete |
| B. Map style (Protomaps Flat schema) | Complete (light + dark) |
| C. R2 hosting | Complete |
| D. Website integration | Complete |
| E. Hillshade (Mapbox RGB raster-dem) | Complete |
| F. Grid-based extracts (mobile offline) | Complete |

## Architecture

```
Web client (MapLibre GL JS)
  ├── Vector base (world): world-low.pmtiles  (Protomaps planet, z0-5, ~15MB)
  │                        Active at zoom 0-5 for world coverage
  ├── Vector base (France): france.pmtiles    (Protomaps planet, France bbox, z6-13, ~2.4GB)
  │                        Active at zoom 6+ for France detail, Flat v4 schema
  ├── Vector overlay:      contours.pmtiles   (GDAL + tippecanoe from SRTM, FR-clipped)
  │                        25m + 100m elevation contour lines
  ├── Raster-DEM:          hillshade.pmtiles  (SRTM → encode_rgb_dem.py Mapbox RGB, z6-11, FR-clipped)
  │                        GPU-rendered hillshade via MapLibre `hillshade` layer
  └── Vector overlay:      GeoJSON trails + POI markers (static files, unchanged)
```

Four PMTiles sources (world + France detail + contours + hillshade). Split base ensures world context at low zoom without shipping full planet. Contours kept separate because the existing GDAL pipeline produces validated quality and updates on independent cycles. Hillshade is a `raster-dem` source; MapLibre computes shading on the GPU from Mapbox-encoded RGB elevation tiles.

### Style files

- `website/src/lib/styles/style-light.json` — Protomaps basemap fork, hiking-customized
- `website/src/lib/styles/style-dark.json` — dark palette variant

Both reference:
- `protomaps` → `pmtiles:///data/france.pmtiles`
- `contours` → `pmtiles:///data/contours.pmtiles`
- `hillshade` → `pmtiles:///data/hillshade.pmtiles` (raster-dem, Mapbox encoding)

### Hiking customizations on top of Protomaps basemap

- `roads_path` layer (new): brown `#9E7B5B`, wider + dashed at z10+, for `kind=path`
- `roads_other` narrowed to `kind=other` (removed `path` from that filter)
- Highways slightly muted (line-opacity 0.75)
- `landuse_park` forest opacity raised (0.5 at z7, 0.9 at z11)
- Regional boundaries stripped: `boundaries` layer deleted, only `boundaries_country` kept (`kind_detail <= 2`)
- Contour layers from `contours` source: 100m z8-15, 25m z13-15, labels z13+ (ele label `{elevation} m`)
- Hillshade layer between `landuse_aerodrome` and `contour-100m-line`: light (`exaggeration 0.4`, warm shadow `#5a4a3a`), dark (`exaggeration 0.3`, black shadow, cool accent)

### Glyphs + sprites

Served by Protomaps CDN:
- `https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf`
- `https://protomaps.github.io/basemaps-assets/sprites/v4/light` (and `/dark`)

---

## Stage A: Protomaps Regional Extract

### Files

- `tiles/download.sh` — fetches `go-pmtiles` binary (v1.30.1)
- `tiles/Makefile.protomaps` — extract + upload pipeline

### Dependencies

- `go-pmtiles` binary (auto-downloaded)
- No Java, no 80GB planet download — HTTP range requests only

### Usage

```bash
cd tiles
./download.sh                         # fetch go-pmtiles
make -f Makefile.protomaps            # build france.pmtiles (~500MB-1GB)
make -f Makefile.protomaps show       # inspect tile metadata
make -f Makefile.protomaps upload     # upload to R2
```

### Build Config

- Source: `https://build.protomaps.com/<SNAPSHOT>.pmtiles` — daily planet build
- `SNAPSHOT := 20260417` pinned in Makefile; bump to refresh
- France bbox: `-5.5,41.0,10.0,51.5` (covers Corsica; overseas DOM excluded)
- `--maxzoom=13` → keeps extract under 2GB; MapLibre overzooms to z17 for hiking use

---

## Stage B: Map Style

Complete. Both styles forked from Protomaps basemap (Flat v4 schema).

Imported directly in `map.ts` via JSON import. `getStyle(isDark)` returns the appropriate style. `switchTheme()` calls `map.setStyle()` with the full style — contours included in the style.

---

## Stage C: Cloudflare R2 Hosting

### Setup (manual, one-time)

1. Create R2 bucket `open-rando-tiles` in Cloudflare dashboard
2. Enable public `.r2.dev` access → URL `https://pub-8869314668be498091e185b1a6fe798d.r2.dev`
3. Create **R2 API Token** (dashboard → R2 → Manage R2 API Tokens), scope **Object Read & Write** on `open-rando-tiles`. This yields S3-compatible Access Key ID + Secret Access Key (not a generic `cfat_…` token).
4. Configure rclone remote:
   ```
   [r2]
   type = s3
   provider = Cloudflare
   access_key_id = <from step 3>
   secret_access_key = <from step 3>
   region = auto
   endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   ```
5. CORS policy (bucket → Settings → CORS):
   ```json
   [{
     "AllowedOrigins": ["https://rando.dammaretz.fr", "http://localhost:4321", "http://localhost:4173"],
     "AllowedMethods": ["GET", "HEAD"],
     "AllowedHeaders": ["Range", "If-Match", "If-None-Match"],
     "ExposeHeaders": ["Content-Length", "Content-Range", "ETag"],
     "MaxAgeSeconds": 3600
   }]
   ```

### Upload

Wrangler's 300 MiB per-object ceiling blocks the multi-GB base tiles, so the Makefile uploads use `rclone` (multipart, resumable).

```bash
cd tiles
make -f Makefile.protomaps upload           # france.pmtiles
make -f Makefile.protomaps upload-world     # world-low.pmtiles
make -f Makefile.protomaps upload-contours  # contours.pmtiles
make -f Makefile.hillshade upload           # hillshade.pmtiles
```

Flags used: `--s3-chunk-size=64M` (multipart), `--s3-no-check-bucket` (skip HeadBucket/CreateBucket; scoped tokens reject both), header uploads set `Cache-Control: public, max-age=604800, immutable` + `Content-Type: application/octet-stream`. Cache TTL is safe because each PMTiles build is content-addressed by tile offset.

### Serving + URL rewriting

Style JSONs reference site-relative `pmtiles:///data/<file>.pmtiles`. `map.ts` rewrites these via `PUBLIC_PMTILES_BASE`:
- **Dev** (unset): Astro serves `website/public/data/<file>.pmtiles` (predev symlinks into `~/.local/share/open-rando/data/`)
- **Prod** (`website/.env.production` sets `PUBLIC_PMTILES_BASE=https://pub-8869314668be498091e185b1a6fe798d.r2.dev`): `getStyle()` rewrites each `pmtiles:///data/<file>.pmtiles` → `pmtiles://<base>/<file>.pmtiles`

This keeps local dev fast (no R2 round-trips) while the static Pages build points at R2 directly — no Worker proxy, no DNS-on-Cloudflare requirement.

---

## Stage D: Website Integration

Complete. No structural changes to `map.ts` — only the style JSONs changed.

### Fallback

If PMTiles fails to load, MapLibre fires `error` event. GeoJSON trail overlays still render (separate sources).

---

## Stage E: Hillshade

### Files

- `tiles/Makefile.hillshade` — SRTM → VRT → clipped EPSG:3857 → custom RGB encoder → PMTiles
- `tiles/encode_rgb_dem.py` — PEP 723 script; rasterio + mercantile + PIL. Replaces `rio-rgbify` which hit a PROJ error on our DEM (`densify_pts must be at least 2 if the output is geographic`).
- `tiles/build_france_mask.py` — outputs `france-boundary.geojson` (used as gdalwarp cutline) + `france-mask.geojson`

### Dependencies

- GDAL (`gdalbuildvrt`, `gdalwarp`)
- `uv` (runs the PEP 723 scripts)
- `rclone` (uploads)
- `./pmtiles` binary (same as Stage A)

### Usage

```bash
cd tiles
make -f Makefile.hillshade install          # verify deps
make -f Makefile.hillshade                  # build hillshade.pmtiles (z6-11)
make -f Makefile.hillshade upload           # upload to R2
```

### Build Config

- Input: `~/.cache/open-rando/srtm/*.hgt` (cached by pipeline)
- `gdalwarp` pipeline: reproject to EPSG:3857, clip to France bbox + admin border via `-cutline france-boundary.geojson -cblend 5`, encode as Int16 with DEFLATE+PREDICTOR=2 (keeps intermediate DEM ~1-2GB instead of 88GB Float32)
- Encoding: Mapbox RGB (`height = -10000 + (R*65536 + G*256 + B) * 0.1`)
- Zoom range: z6-11 (lower resolution than contours; hillshade overzooms smoothly). z5 dropped to reduce tile count at global scale.
- Output: `hillshade.pmtiles` in `~/.local/share/open-rando/data/`

MapLibre source config: `type: raster-dem`, `encoding: "mapbox"`, `tileSize: 512`. Light style: `exaggeration 0.4`, warm shadow `#5a4a3a`. Dark: `exaggeration 0.3`, black shadow.

---

## Stage F: Hybrid base + grid PMTiles for mobile offline

MapLibre native `OfflineManager.createPack` on iOS/Android rejects `pmtiles://` sources — it downloads only HTTPS XYZ. To support offline, each layer (france, contours, hillshade) is split into two pieces: a shared **base** file (low zooms, whole France, one file per layer) plus per-square **grid** files (high zooms, 12×8 grid over France). Routes reference the squares that intersect their padded bbox; base is always fetched.

This replaces two earlier attempts:
1. **Per-route extract** (~14 GB total) — overlapping routes duplicated tiles.
2. **Pure grid** (~6.7 GB) — low-zoom tiles (z8-10) were bigger than a 1.3° square and got included in several adjacent squares, driving grid contours alone to 2.95 GB.

Hoisting z8-10 into a shared 633 MB base file collapses that duplication. Final footprint fits inside the ~10 GB R2 free tier with headroom.

### Files

- `tiles/build-grid.py` — PEP 723 script; writes `base/<layer>.pmtiles` once + `grid/{col}_{row}/<layer>.pmtiles` for each of 96 squares, plus `grid.json`
- `tiles/build-routes.py` — PEP 723 script; for each route in `catalog.json` emits `routes/{id}/pmtiles.json` listing intersecting grid squares (no pmtiles extraction, trivially fast)
- `tiles/Makefile.routes` — `download-masters` / `build-grid` / `build-routes` / `build` / `force` / `upload` / `show` / `clean`

### Layers: base vs grid split

| Layer | Source | Master zoom | Base zoom | Grid zoom |
|-------|--------|-------------|-----------|-----------|
| `france`    | `tiles/france.pmtiles`                             | 6-13 | 6-10 | 11-13 |
| `contours`  | `~/.local/share/open-rando/data/contours.pmtiles`  | 8-15 | 8-10 | 11-13 |
| `hillshade` | `~/.local/share/open-rando/data/hillshade.pmtiles` | 6-11 | 6-8  | 9-11  |

Contours capped at z13 (master z15) because trail overlay renders on top — sub-z13 contour detail is not load-bearing for offline hiking UX. France + hillshade match master zoom for full parity. Base split at roughly half the master zoom range for each layer, where low-zoom tiles would duplicate most across grid squares.

Approximate footprints:
- Base (all layers): ~633 MB (one-time download shared by every route)
- Grid (96 squares × 3 layers): ~5 GB projected (down from 6.7 GB pure-grid)
- Total new artifacts: ~5.6 GB; total R2 with masters ~10 GB.

`world-low` is intentionally omitted — offline viewport stays inside the route bbox. The mobile offline style drops the `protomaps_world` source.

### Grid layout

- Grid bbox tracks `BBOX` in `Makefile.protomaps` (`-5.5, 41.0, 10.0, 51.5`) — `build-grid.py` parses it alongside `SNAPSHOT`, so the grid stays in sync with the master extract.
- 12 cols × 8 rows = 96 squares → ~1.29° × 1.31° each (~100 × 145 km).
- Each square bbox is padded by `PAD_DEG = 0.02` (~2 km) so MapLibre has edge tiles when the viewport straddles two squares.

### R2 + website layout

```
R2 (open-rando-tiles):
  base/france.pmtiles                     ← z6-10 whole France, shared
  base/contours.pmtiles                   ← z8-10
  base/hillshade.pmtiles                  ← z6-8
  grid/{col}_{row}/france.pmtiles         ← z11-13 per square
  grid/{col}_{row}/contours.pmtiles       ← z11-13
  grid/{col}_{row}/hillshade.pmtiles      ← z9-11

Website (rando.dammaretz.fr):
  /data/grid.json                         ← base URLs + per-square URLs + sizes
  /data/routes/{routeId}/pmtiles.json     ← per-route square list
```

`grid.json` shape (`version: 2`):

```json
{
  "version": 2,
  "source_snapshot": "20260417",
  "grid": { "bbox": [-5.5, 41.0, 10.0, 51.5], "cols": 12, "rows": 8, "pad_deg": 0.02 },
  "layers": {
    "france":    { "base_minzoom": 6, "base_maxzoom": 10, "grid_minzoom": 11, "grid_maxzoom": 13 },
    "contours":  { "base_minzoom": 8, "base_maxzoom": 10, "grid_minzoom": 11, "grid_maxzoom": 13 },
    "hillshade": { "base_minzoom": 6, "base_maxzoom": 8,  "grid_minzoom": 9,  "grid_maxzoom": 11 }
  },
  "base": {
    "france":    { "url": "https://pub-…/base/france.pmtiles",    "size": 231696524, "minzoom": 6, "maxzoom": 10 },
    "contours":  { "url": "https://pub-…/base/contours.pmtiles",  "size": 383806119, "minzoom": 8, "maxzoom": 10 },
    "hillshade": { "url": "https://pub-…/base/hillshade.pmtiles", "size":  17535963, "minzoom": 6, "maxzoom": 8 }
  },
  "squares": {
    "6_5": {
      "bbox": [2.25, 47.875, 3.54, 49.19],
      "files": {
        "france":    { "url": "https://pub-…/grid/6_5/france.pmtiles",    "size": 5421312, "minzoom": 11, "maxzoom": 13 },
        "contours":  { "url": "https://pub-…/grid/6_5/contours.pmtiles",  "size": 8430211, "minzoom": 11, "maxzoom": 13 },
        "hillshade": { "url": "https://pub-…/grid/6_5/hillshade.pmtiles", "size": 2341255, "minzoom": 9,  "maxzoom": 11 }
      }
    }
  }
}
```

Per-route manifest shape:

```json
{
  "route_id": "0fbbaf4616b4",
  "source_snapshot": "20260417",
  "bbox": [1.7160437, 48.2921791, 2.9390362, 49.1628759],
  "squares": [[5, 5], [5, 6], [6, 5], [6, 6]]
}
```

### Usage

```bash
cd tiles
# Master archives — either rebuild locally:
make -f Makefile.protomaps                   # france.pmtiles
make                                         # contours.pmtiles
make -f Makefile.hillshade                   # hillshade.pmtiles
# …or pull them from R2 (much faster):
make -f Makefile.routes download-masters

make -f Makefile.routes                      # build base + grid + route manifests (incremental)
make -f Makefile.routes build-grid           # only base + grid (slow step)
make -f Makefile.routes build-routes         # only the per-route manifests (fast)
make -f Makefile.routes build-grid SQUARE=6_5   # one square (skips base rebuild)
make -f Makefile.routes build-routes ROUTE=0fbbaf4616b4
make -f Makefile.routes force                # rebuild base + all squares
make -f Makefile.routes upload               # rclone base/ + grid/ to R2
make -f Makefile.routes show SQUARE=6_5
```

`grid.json` and every `routes/{id}/pmtiles.json` are written into `~/.local/share/open-rando/data/` — the website `prebuild` step copies that whole dir into `public/data/`, so they ship on the static site. Only the `.pmtiles` bundles go to R2.

### Incremental rebuild

The `base/` directory and each square directory hold a `.build-state.json` keyed by layer: `{layer: state_hash}` where `state_hash` covers `{bbox, snapshot, minzoom, maxzoom}`. A layer is skipped when the hash matches and its `.pmtiles` is on disk. Bump `SNAPSHOT` in `Makefile.protomaps` to force-invalidate; it is the single source of truth.

### Size budget

Projected R2 storage for this stage: ~633 MB base + ~5 GB grid = ~5.6 GB (vs ~6.7 GB pure-grid and ~14 GB per-route). Plus ~4.4 GB masters already on R2 = ~10 GB total, at the edge of the free tier. Route downloads range from ~650 MB (base + 1 square) to ~1.5 GB (base + 30+ squares for GR 5/GR 10).

### Mobile-side contract

Full implementation plan for the mobile team: [`MOBILE_OFFLINE.md`](./MOBILE_OFFLINE.md).

Summary — on "download route" the mobile app:

1. Fetch `https://rando.dammaretz.fr/data/routes/{id}/pmtiles.json`.
2. Fetch (or reuse cached) `https://rando.dammaretz.fr/data/grid.json`.
3. Download `base/<layer>.pmtiles` (once per device, reused across every route) into `Paths.document/base/`.
4. For each `[col, row]` in the manifest's `squares`, download the three grid layers from R2 into `Paths.document/grid/{col}_{row}/`. Squares already on disk from a prior route are skipped.
5. Build an offline MapLibre style:
   - Clone the online style (light or dark).
   - Drop the `protomaps_world` source + its layers.
   - Add one source per layer-kind for `base` (URL: `pmtiles://file:///.../base/<kind>.pmtiles`) covering the full France bbox, then one source per `(square, kind)` pair (URL: `pmtiles://file:///.../grid/{col}_{row}/<kind>.pmtiles`, `bounds` matching the square bbox).
   - Duplicate every online-style layer referencing a given source kind: one copy targeting the base source (with max zoom range `base_maxzoom`) and one copy per square (with zoom range `grid_minzoom`-`grid_maxzoom`), rewriting the `source` field.
   - Cache the assembled style JSON per route on disk.
5. On "remove download", delete the route's cached style + manifest entry. Keep squares on disk (shared); a separate GC pass removes squares no longer referenced by any downloaded route.

Paths are contract: `grid/{col}_{row}/{layer}.pmtiles`. Bump `grid.json` `version` if the scheme changes.

### Open items

- Bumping master france maxzoom 13 → 14 for better mobile fidelity (costs ~40% on master size). Current z12 grid + overzoom is acceptable.
- Sprite/glyph offline bundle — currently served by `protomaps.github.io`. Mobile needs a local cache; a one-shot `assets.zip` on R2 is the likely path.
- Atomic grid publish: during R2 upload the files briefly lag the shipped `grid.json`. If it matters, publish `grid.json` (via the website deploy) after the R2 upload completes, or gate consumption on matching `source_snapshot`.

---

## V2 Deferred

### 3D terrain

Same `hillshade.pmtiles` can feed MapLibre `terrain` via `setTerrain({ source: 'hillshade', exaggeration: 1.5 })`. Requires pitch-enabled map interaction.

### GR-marked path dashing

Requires verifying Protomaps Flat schema exposes OSM `network=gr` tag. If not, either drop distinction or run a custom Planetiler profile producing Protomaps-compatible layers.

---

## Resolved Questions

- Base data: Protomaps daily planet extract (world coverage included at low zoom)
- Schema: Protomaps Flat v4
- DNS: not on Cloudflare; `.r2.dev` public URL or Worker proxy
- Contours: kept separate from base tiles (proven GDAL pipeline)
