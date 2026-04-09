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
