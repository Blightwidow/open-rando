# Deployment

The website is deployed to [GitHub Pages](https://pages.github.com/) and served at **https://rando.dammaretz.fr**.

## How it works

```
Push to main (website/**)
        │
        ▼
GitHub Actions (deploy.yml)
        │
        ├── Download data.tar.gz from latest GitHub Release
        ├── Extract to website/public/data/
        ├── bun install --frozen-lockfile
        ├── bun run build (Astro static build)
        └── Upload dist/ to GitHub Pages
                │
                ▼
        https://rando.dammaretz.fr
```

## Trigger

The deployment workflow (`.github/workflows/deploy.yml`) runs on:

- **Push to `main`** when files under `website/` change
- **Manual trigger** via `workflow_dispatch` (Actions tab > "Deploy to GitHub Pages" > Run workflow)

Only one deployment runs at a time — the `pages` concurrency group cancels in-progress runs when a new one starts.

## Data release flow

The website needs pipeline output (`catalog.json`, GPX files, GeoJSON, elevation profiles) to build. This data is not committed to the repo. Instead:

1. Run the pipeline locally: `cd pipeline && uv run python -m open_rando`
2. Package the output: `tar -czf data.tar.gz -C ~/.local/share/open-rando/data .`
3. Upload as a GitHub Release tagged `latest`: `gh release upload latest data.tar.gz --clobber`

The CI workflow downloads `data.tar.gz` from the `latest` release before building. If no release exists, the build proceeds with empty data (the site will render but show no hikes).

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

If R2 is unreachable, MapLibre fires `error` but trail GeoJSON overlays still render.

See [VECTOR_TILES.md](VECTOR_TILES.md) for full implementation details.

## Custom domain

The site is served at `rando.dammaretz.fr` instead of the default `<user>.github.io/<repo>`:

- Astro's `site` field in `website/astro.config.mjs` is set to `https://rando.dammaretz.fr`
- A DNS CNAME record points `rando.dammaretz.fr` to the GitHub Pages domain
- GitHub Pages custom domain is configured in the repository settings

## Permissions

The workflow requires these GitHub token permissions:

| Permission | Reason |
|------------|--------|
| `contents: read` | Checkout repo and download releases |
| `pages: write` | Upload build artifacts to Pages |
| `id-token: write` | OIDC token for Pages deployment |
