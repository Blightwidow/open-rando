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
