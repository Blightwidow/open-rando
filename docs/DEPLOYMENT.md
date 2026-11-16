# Deployment

The website is deployed to [GitHub Pages](https://pages.github.com/) and served at **https://rando.dammaretz.fr**.

## How it works

The site is published from a local machine by `website/deploy.sh` (`bun run deploy` in `website/`). No CI workflow deploys it: `.github/workflows/ci.yml` only checks and tests.

```
bun run deploy  (website/)
        │
        ├── refuse unless on a clean main equal to origin/main
        ├── bun run build  (prebuild copies ~/.local/share/open-rando/data/ into public/data/)
        ├── check dist/data/ for grid.json and route manifests
        ├── write dist/CNAME, git init dist/, commit
        └── force-push dist/ to the gh-pages branch
                │
                ▼
        https://rando.dammaretz.fr  (GitHub Pages serves gh-pages)
```

## Guards

`deploy.sh` refuses to publish unless:

- the checkout is on `main`
- tracked files have no uncommitted changes
- local `HEAD` equals `origin/main` (after a fetch)

so a published site always matches a reviewed commit. The `gh-pages` commit message carries that short commit hash. `ALLOW_UNREVIEWED_DEPLOY=1 bun run deploy` skips these checks on purpose (hotfix, branch preview).

## Data

The website needs pipeline output (`catalog.json`, GPX files, GeoJSON, elevation profiles, links, POI squares) to build. It is not committed to the repo. The build reads the local data dir `~/.local/share/open-rando/data/`:

1. Run the pipeline locally: `cd pipeline && uv run python -m open_rando pipeline`
2. Build the tile manifests (next section)
3. Deploy: `cd website && bun run deploy`

Whoever deploys needs the full data dir on their machine; nothing downloads it.

## Tile manifests (`grid.json`, `routes/{id}/pmtiles.json`)

The mobile app reads these two manifests from the site (`/data/grid.json`, `/data/routes/{id}/pmtiles.json`). The data pipeline does not write them: `tiles/build-grid.py` and `tiles/build-routes.py` do, into the same data dir, and the website build copies them like any other data file. A data dir without them publishes a site where both answer 404.

Without the master archives (the bundles are already on R2), rebuild them from R2 and the catalog:

```bash
cd tiles
make -f Makefile.routes grid-manifest-from-r2   # sizes from HEAD requests on R2
make -f Makefile.routes build-routes            # per-route manifests, checked against grid.json
```

Rerun `build-routes` whenever `catalog.json` changes (route bboxes decide the squares).

`website/deploy.sh` runs `scripts/check-tile-manifests.mjs` on the built `dist/data/` and refuses to publish when `grid.json` is missing, a catalog route has no manifest, or a manifest lists a square that is not in `grid.json`. `ALLOW_MISSING_TILE_MANIFESTS=1 bun run deploy` skips it on purpose; `bun run check:manifests` runs it by hand.

## Vector tiles

The map uses four PMTiles sources hosted on Cloudflare R2 (`open-rando-tiles`):

- `france.pmtiles` — Protomaps Flat v4 extract (France bbox, z6-13)
- `world-low.pmtiles` — Protomaps Flat v4 world coverage (z0-5, ~15MB)
- `contours.pmtiles` — 25m + 100m elevation contours (GDAL + tippecanoe from SRTM, clipped to FR admin border)
- `hillshade.pmtiles` — Mapbox RGB raster-dem (SRTM, z6-11, clipped to FR admin border)

### Building tiles

```bash
cd tiles
./download.sh                           # fetch go-pmtiles binary

# Base map (Protomaps daily planet → regional extract via HTTP range)
make -f Makefile.protomaps              # build france.pmtiles
make -f Makefile.protomaps world        # build world-low.pmtiles

# Contours (GDAL + tippecanoe)
make                                    # build contours.pmtiles

# Hillshade (GDAL + custom RGB encoder)
make -f Makefile.hillshade              # build hillshade.pmtiles
```

### Uploading to R2

Uploads use `rclone` against the R2 S3 endpoint — `wrangler` caps at 300 MiB and the base tiles are multi-GB. One-time rclone setup: create an **R2 API Token** (Cloudflare dashboard → R2 → Manage R2 API Tokens, **Object Read & Write**), then `rclone config` a remote named `r2` with provider `Cloudflare`, `region: auto`, endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

```bash
cd tiles
make -f Makefile.protomaps upload           # france.pmtiles → R2
make -f Makefile.protomaps upload-world     # world-low.pmtiles → R2
make -f Makefile.protomaps upload-contours  # contours.pmtiles → R2
make -f Makefile.hillshade upload           # hillshade.pmtiles → R2
```

Upload sets `Cache-Control: public, max-age=604800, immutable` — safe because PMTiles content-addresses tiles by offset within a build.

### Public serving

R2 bucket has public `.r2.dev` access enabled at `https://pub-8869314668be498091e185b1a6fe798d.r2.dev`. CORS policy allows `https://rando.dammaretz.fr` + `http://localhost:4321/4173` for dev, methods `GET, HEAD`, header `Range`.

### URL rewriting (dev vs prod)

Style JSONs reference `pmtiles:///data/<file>.pmtiles` (site-relative). At runtime, `map.ts` rewrites those URLs using the `PUBLIC_PMTILES_BASE` env var:

- **Dev**: `PUBLIC_PMTILES_BASE` unset → URLs stay `pmtiles:///data/<file>.pmtiles`, resolved by Astro from `website/public/data/` (predev symlinks from `~/.local/share/open-rando/data/`)
- **Prod**: `PUBLIC_PMTILES_BASE=https://pub-8869314668be498091e185b1a6fe798d.r2.dev` (set in `website/.env.production`) → URLs become `pmtiles://https://<pub>.r2.dev/<file>.pmtiles`

`website/.env.production` is committed (the value is a public `r2.dev` URL, not a secret), so a fresh clone or worktree builds with the right base tiles. `.gitignore` whitelists it through `!website/.env.production`.

Without it the styles keep their site-relative `pmtiles:///data/` URLs while `prebuild` excludes `*.pmtiles` from `public/data/`, so every base tile 404s and the map loses its background while trail and POI overlays keep working. `bun run build` now fails with that message instead of shipping such a build; `ALLOW_MISSING_PMTILES_BASE=1` skips the check on purpose.


If R2 is unreachable, MapLibre fires `error` but trail GeoJSON overlays still render.

See [VECTOR_TILES.md](VECTOR_TILES.md) for full implementation details.

## Custom domain

The site is served at `rando.dammaretz.fr` instead of the default `<user>.github.io/<repo>`:

- Astro's `site` field in `website/astro.config.mjs` is set to `https://rando.dammaretz.fr`
- A DNS CNAME record points `rando.dammaretz.fr` to the GitHub Pages domain
- GitHub Pages custom domain is configured in the repository settings
