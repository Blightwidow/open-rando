# Mobile Offline Tiles — Implementation Plan

This doc is the contract between the backend tile pipeline (this repo) and the mobile app (`open-rando-mobile`). It describes what the mobile app needs to implement so a user can download a hiking route and use the map fully offline.

## TL;DR

For each route the user downloads, the app must:

1. Fetch a tiny per-route JSON manifest from the static site.
2. Fetch a global grid manifest (cacheable, reused across all routes).
3. Download **three shared base `.pmtiles` files** (once per device, ~526 MB total, covers low zooms for all of France).
4. Download **three grid `.pmtiles` files per intersecting grid square** (high zooms only, a few MB per square). Squares are shared across overlapping routes.
5. Build an offline MapLibre style JSON by cloning the online style and rewriting its three vector/raster sources into many local `pmtiles://file:///...` sources (one base + one per square × per layer-kind), duplicating each style layer once per source.
6. Render offline using that assembled style.

MapLibre GL Native's own `OfflineManager.createPack` rejects `pmtiles://` sources and only handles HTTPS XYZ, so we bypass it entirely. The app just downloads HTTPS files, stores them locally, and feeds them to MapLibre via the `pmtiles://file://` protocol (use the official [protomaps/swift-pmtiles](https://github.com/protomaps/swift-pmtiles) and [protomaps/pmtiles-android](https://github.com/protomaps/pmtiles-android) plugins).

## Why this shape

Earlier iterations tried:

1. **One pmtiles bundle per route** — total R2 footprint ballooned to 14 GB because long GR trails duplicated every shared tile.
2. **Pure 12×8 grid, no base** — dropped to ~6.7 GB but low-zoom tiles (z8-10) still duplicated across adjacent squares because each z8 contour tile (~1.4° wide) spans multiple 1.3° squares.

The current **hybrid base + grid** layout hoists low zooms into a single shared file per layer (~526 MB for all three), then keeps only high zooms per square (~4 GB across 96×3 square files). This eliminates the duplication without losing any zoom level and fits inside the 10 GB R2 free tier.

## Data contract

### Static-site endpoints (`https://rando.dammaretz.fr`)

| Path | What it is | Cacheable? |
|------|------------|------------|
| `/data/grid.json` | Global manifest: bbox, grid dims, **base URLs + sizes**, per-square URLs + sizes, version, snapshot. | Yes. Reuse until `source_snapshot` changes. ~73 KB. |
| `/data/routes/{routeId}/pmtiles.json` | Per-route manifest: route id, bbox, snapshot, list of grid `[col, row]` the route intersects. | Yes. Stable until snapshot bumps. ~300 B. |
| `/data/catalog.json` | Existing route catalog (already consumed). | — |

### R2 endpoints (`https://pub-8869314668be498091e185b1a6fe798d.r2.dev`)

Download these directly — URLs are stamped into `grid.json` under `base[layer].url` and `squares[col_row].files[layer].url`.

```
https://…r2.dev/base/france.pmtiles        (~220 MB, z6-10, whole France)
https://…r2.dev/base/contours.pmtiles      (~290 MB, z8-10)
https://…r2.dev/base/hillshade.pmtiles     (~17 MB,  z6-8)

https://…r2.dev/grid/{col}_{row}/france.pmtiles        (0.01–60 MB, z11-13)
https://…r2.dev/grid/{col}_{row}/contours.pmtiles      (0.01–60 MB, z11-13)
https://…r2.dev/grid/{col}_{row}/hillshade.pmtiles     (0.01–30 MB, z9-11)
```

All files are served with `Cache-Control: public, max-age=604800, immutable`. Safe to cache indefinitely; a new `source_snapshot` triggers a full rebuild and upload (and a new set of URLs under the same paths — so the app should re-verify sizes against `grid.json` after a snapshot bump).

### `grid.json` shape (version 2)

```json
{
  "version": 2,
  "source_snapshot": "20260417",
  "grid": {
    "bbox": [-5.5, 41.0, 10.0, 51.5],
    "cols": 12,
    "rows": 8,
    "pad_deg": 0.02
  },
  "layers": {
    "france":    { "base_minzoom": 6, "base_maxzoom": 10, "grid_minzoom": 11, "grid_maxzoom": 13 },
    "contours":  { "base_minzoom": 8, "base_maxzoom": 10, "grid_minzoom": 11, "grid_maxzoom": 13 },
    "hillshade": { "base_minzoom": 6, "base_maxzoom": 8,  "grid_minzoom": 9,  "grid_maxzoom": 11 }
  },
  "base": {
    "france":    { "url": "https://…/base/france.pmtiles",    "size": 230712575, "minzoom": 6, "maxzoom": 10 },
    "contours":  { "url": "https://…/base/contours.pmtiles",  "size": 303292892, "minzoom": 8, "maxzoom": 10 },
    "hillshade": { "url": "https://…/base/hillshade.pmtiles", "size": 17535963,  "minzoom": 6, "maxzoom": 8 }
  },
  "squares": {
    "6_5": {
      "bbox": [2.25, 47.875, 3.541666, 49.1875],
      "files": {
        "france":    { "url": "https://…/grid/6_5/france.pmtiles",    "size": 5421312, "minzoom": 11, "maxzoom": 13 },
        "contours":  { "url": "https://…/grid/6_5/contours.pmtiles",  "size": 8430211, "minzoom": 11, "maxzoom": 13 },
        "hillshade": { "url": "https://…/grid/6_5/hillshade.pmtiles", "size": 2341255, "minzoom": 9,  "maxzoom": 11 }
      }
    }
  }
}
```

**Layer kinds**: `france` (vector basemap, Protomaps Flat v4 schema), `contours` (vector line geometry), `hillshade` (raster-dem, Mapbox RGB encoding).

### Per-route manifest shape

```json
{
  "route_id": "0fbbaf4616b4",
  "source_snapshot": "20260417",
  "bbox": [1.7160437, 48.2921791, 2.9390362, 49.1628759],
  "squares": [[5, 5], [5, 6], [6, 5], [6, 6]]
}
```

The `squares` array lists `[col, row]` pairs intersecting the route's padded bbox. Each entry points into `grid.json.squares["{col}_{row}"]` for the URLs + sizes.

## Download flow

Given a `routeId` the user wants offline:

```
1. GET  /data/routes/{routeId}/pmtiles.json                 → route manifest
2. GET  /data/grid.json  (or reuse cached, keyed on source_snapshot)
3. totalSize = sum(grid.json.base[*].size)
             + sum over manifest.squares of sum over layers of grid.json.squares[k].files[layer].size
   (subtract files already on disk — see dedup below)
4. Show totalSize to user; ask for confirmation if large.
5. In parallel (suggest 3–4 concurrent downloads):
   - For each of base.{france,contours,hillshade}: if not on disk at expected size, download to `{doc}/base/{layer}.pmtiles.part`, atomic-rename to `.pmtiles`.
   - For each [col,row] × layer in manifest.squares: same — download to `{doc}/grid/{col}_{row}/{layer}.pmtiles.part`, atomic-rename.
6. Persist a local record: `routes/{routeId}.json` with
     { snapshot, squares: [[col,row], …] }
   This is the reference-count input for GC.
7. Generate the offline style (see next section) and cache it at
   `styles/{routeId}/{light|dark}.json`.
8. Mark route as "available offline" in the UI.
```

**Dedup across routes**: base files are always shared. Grid squares are shared whenever two routes intersect the same `[col,row]`. Before downloading a square file, check `size` matches — if it does, skip. If mismatched (snapshot rolled), re-download.

**Partial downloads**: use `.part` suffix + atomic rename on completion so a killed app never leaves half-written `.pmtiles` that MapLibre would reject.

**Retry**: transient failures should retry with exponential backoff. After 3 failures on any file, fail the whole download and clean up `.part` files; do not mark the route available offline.

## MapLibre style assembly

This is the main piece of mobile work. The online style (`/website/src/lib/styles/style-{light|dark}.json`) has 4 sources and ~80 layers. Offline we replace 3 of those sources with many local PMTiles sources and leave the rest intact.

### Source replacement

The online style's sources block:

```json
{
  "protomaps":       { "type": "vector",     "url": "pmtiles:///data/france.pmtiles" },
  "contours":        { "type": "vector",     "url": "pmtiles:///data/contours.pmtiles" },
  "hillshade":       { "type": "raster-dem", "url": "pmtiles:///data/hillshade.pmtiles", "encoding": "mapbox", "tileSize": 512 },
  "protomaps_world": { "type": "vector",     "url": "pmtiles:///data/world-low.pmtiles" }
}
```

Offline assembly:

1. **Drop** `protomaps_world` source and every style layer that references it. Offline viewport stays inside the route bbox so the world fallback is unused.
2. **Rename + replace** the other three sources. For each layer kind in `{france→protomaps, contours→contours, hillshade→hillshade}`:
   - Add **one base source** covering all of France, at low zoom:
     ```json
     "protomaps__base": {
       "type": "vector",
       "url": "pmtiles://file:///.../base/france.pmtiles",
       "bounds": [-5.5, 41.0, 10.0, 51.5],
       "minzoom": 6,
       "maxzoom": 10
     }
     ```
     For `hillshade__base`: same pattern with `"type": "raster-dem", "encoding": "mapbox", "tileSize": 512`.
   - Add **one source per downloaded square**, at high zoom:
     ```json
     "protomaps__6_5": {
       "type": "vector",
       "url": "pmtiles://file:///.../grid/6_5/france.pmtiles",
       "bounds": [2.25, 47.875, 3.54, 49.19],
       "minzoom": 11,
       "maxzoom": 13
     }
     ```
   - Use the `bounds` field so MapLibre skips queries for tiles outside the source's region — this is what keeps render perf usable when you have 200+ sources.

(Source name convention is illustrative; any unique id works. `{kind}__{col}_{row}` and `{kind}__base` are recommended for debuggability.)

### Layer duplication

Each online-style layer references one of the three kinds via its `source` field. For each such layer, emit `(1 + squareCount)` copies in the offline style:

- **Base copy** — set `source: "{kind}__base"`, keep the original `filter` / `paint` / `layout`, and ensure the layer has `maxzoom: base_maxzoom + 1` (MapLibre's `maxzoom` is exclusive). This renders at zooms ≤ 10 using the base source.
- **Per-square copies** — one per downloaded `[col,row]`, set `source: "{kind}__{col}_{row}"` and scope `minzoom: grid_minzoom`, `maxzoom: grid_maxzoom + 1`. These render at zooms ≥ 11 using the matching grid source.

Preserve ordering: iterate the original layer list and for each original layer output its base copy followed by its per-square copies. This keeps draw order stable (roads stay above landcover, etc.).

Give each emitted copy a unique `id`; e.g. `{originalId}__base` and `{originalId}__{col}_{row}`.

**Sizing expectation**: ~74 source-bound layers × (1 + squares). For a 4-square suburban route that's ~370 layers; for GR 5 / GR 10 spanning 30+ squares that's ~2300. Benchmark on a mid-range Android device (Pixel 5 class) and fail fast if style load time exceeds 500 ms so we catch perf regressions early.

### Layers to keep verbatim

The online style also has non-offline style layers (e.g. the `background` fill, possibly future sprite-based POIs). Keep them untouched — they have no `source` field or reference nothing we replaced.

### Sprites + glyphs

The online style references `sprite` and `glyphs` URLs pointing at `protomaps.github.io`. **Offline will break** without a local cache of these. Current scope of this plan does not include bundling sprites/glyphs; a follow-up asset pack is tracked in `docs/VECTOR_TILES.md § Stage F / Open items`. Until then, offline map renders without icons + labels in areas without network, which is acceptable for a first iteration where the trail overlay is the primary guidance.

### Style caching

Store the assembled style JSON at `styles/{routeId}/{light|dark}.json`. Regenerate if:

- The user toggles theme (keep both cached if storage budget allows).
- `grid.json.source_snapshot` differs from the snapshot saved with the route.
- Any referenced `.pmtiles` file is missing on disk.

## Local filesystem layout

Anchor everything under the app's documents directory (iOS: `FileManager.documentDirectory`; Android: `context.filesDir`). Suggested structure:

```
{doc}/
  base/
    france.pmtiles
    contours.pmtiles
    hillshade.pmtiles
  grid/
    6_5/
      france.pmtiles
      contours.pmtiles
      hillshade.pmtiles
    …
  routes/
    {routeId}.json             ← reference record: snapshot + squares list
    {routeId}.pmtiles.json     ← cached copy of per-route manifest (optional)
  styles/
    {routeId}/
      light.json
      dark.json
  grid.json                    ← cached global manifest
```

**Do not** store offline data in the app's cache directory — iOS and Android both reserve the right to evict it. Documents / files dir is durable.

## Deletion + GC

When the user "removes download" for a route:

1. Delete `routes/{routeId}.json` + `routes/{routeId}.pmtiles.json` + `styles/{routeId}/…`.
2. **Do not** delete any `.pmtiles` files yet — they may still be referenced by other downloaded routes.
3. Run a GC pass (can be lazy, e.g. on app background):
   - Union the `squares` arrays from every remaining `routes/*.json` → the set of still-referenced grid squares.
   - Delete any `grid/{col}_{row}/` dir not in the union.
   - Base files are deleted only if no routes remain downloaded at all.

Surface the per-route size in the UI as "space that will be freed" ≈ size of tiles unique to this route. Compute via `routeBytes − sharedBytes` where shared = tiles in other downloaded routes' manifests.

## Snapshot handling

`grid.json.source_snapshot` is a monotonically increasing date string (e.g. `20260417`). When it changes:

- Every already-downloaded route becomes "stale" — its tiles still work (immutable URLs), but an update is available.
- Show a "Refresh offline data" affordance per route that re-runs the download flow. Expect mostly-cached downloads since unchanged squares will match the new `grid.json` by size.
- At minimum, cache `grid.json` keyed on snapshot so a quick app relaunch doesn't re-fetch 73 KB.

## Edge cases

- **Route bbox outside the France grid**: shouldn't happen (pipeline rejects these), but `manifest.squares` may be `[]`. Refuse to mark the route offline and log.
- **Disk full**: check free space against `totalSize` before starting; abort cleanly and surface the shortfall.
- **User downloads a second route while first is mid-download**: queue or parallelize — both are fine. The dedup check by file size prevents double-downloading shared squares.
- **PMTiles plugin failures**: if MapLibre refuses to load a source (corrupt file, truncation), fall back to online tiles for that source rather than crashing; let the next GC pass re-verify and redownload.
- **Very small squares**: many empty-France squares (ocean, foreign land) have files as small as 1 KB. Don't skip them — they're still required by the offline style for MapLibre's tile-querying logic to succeed (an absent source ID causes load errors).

## Verification checklist

Before shipping to TestFlight / internal track:

- [ ] Airplane-mode test: download a known route (`0fbbaf4616b4`, Île-de-France loop), kill network, relaunch, render map at zooms 6/10/13.
- [ ] Base sharing test: download a second route that intersects the first. Verify no duplicate downloads for shared squares (check network logs) and that base files are not re-downloaded.
- [ ] Removal test: delete the first route. Confirm shared squares survive; confirm squares unique to the removed route are gone.
- [ ] Snapshot bump test: manually edit the cached `grid.json` to a fake snapshot, verify the app surfaces "update available" and re-downloads only changed files.
- [ ] Perf: on a mid-range device, GR 5 (30+ squares) style load under 500 ms, 60 fps pan at zoom 12.
- [ ] Disk-full test: fill storage to < totalSize, attempt download, verify clean abort + surfaced error.

## Open items

- **Sprites/glyphs offline bundle**: pipeline-side task, not mobile. Tracked in `docs/VECTOR_TILES.md` Stage F.
- **Background download**: iOS `URLSessionConfiguration.background`, Android `WorkManager`. Scope depends on UX target.
- **Progress UI**: byte-accurate progress is easy (sum of downloaded bytes / totalSize). Per-file progress optional.
