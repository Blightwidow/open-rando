# TODOs

Known work not yet done. Each entry says what is wrong, why it matters, and what "done" looks like.

## 1. Dead step-planner code in `slice.py`

`find_hikes`, `find_round_trip_hikes`, `_build_step_graph`, `_build_constrained_step_graph`, `_find_constrained_paths` and `_find_connected_components` — roughly 350 of `processors/slice.py`'s 500 lines — are referenced only by `tests/test_constrained_paths.py` and `tests/test_round_trip.py`. Nothing in the pipeline calls them; they are what remains of the step planner replaced in `66614d1`. `_compute_cumulative_distances` had the same gap-measuring bug as the trail profile and was fixed blind, because no live code exercises it.

Done when either the planner is wired back into a feature or the functions and their tests are deleted. Keeping ~350 lines of tested-but-unused graph search costs every future reader of that module.

## 2. Stop maintaining the site twice (FR/EN page forks)

`website/src/pages/app/route/[slug].astro` and `website/src/pages/en/app/route/[slug].astro` are 820-line near-copies (66 diff lines, almost all hardcoded strings). Same for `pages/app/index.astro` vs `pages/en/app/index.astro`. Every feature has to be written twice, and the rail-service work in this change had to be patched into both files separately — the EN copy silently used a different relative import depth.

Done when Astro i18n routing (already declared in `astro.config.mjs`) serves both locales from one template per page, with all copy from `src/lib/i18n.ts`, and the 820-line detail page's inline scripts are split into modules (map setup, section selector, QR code, elevation sync).

## 3. README is out of date

Prerequisites now mention `brew bundle` and osmium-tool, but the rest still describes a stack the repo no longer has:

- Says Leaflet; the site uses `maplibre-gl` + `pmtiles`.
- Documents `uv run python -m open_rando` without the `pipeline` subcommand from `3765102`, and the `--route/--dry-run/--reset` flags at the wrong level.
- No mention of `tiles/`, the `images` subcommand, mobile offline PMTiles, the run report, or `osm-index`.

Done when the README matches the current commands, stack and layout, and stops duplicating what `docs/` already explains.

## 4. Dead i18n keys from the removed step planner

`website/src/lib/i18n.ts` still carries keys no page or script reads: `filters.maxStep`, `filters.steps`, `filters.difficulty`, `filters.accommodation`, `filters.hotel`, `filters.camping`, `steps.label`, `detail.stepCount`, `detail.steps`, `detail.stations`, `detail.difficulty`, `hike.loop`, `hike.loopFrom`, `map.steps`. `getClientTranslations()` is itself unused outside its own test.

Done when every key is referenced by a page, component or script, and `getClientTranslations` is either used or removed. A test that fails on an unreferenced key would keep it that way.

## 5. Unused packaged data file

`pipeline/src/open_rando/data/gr-descriptions.yaml` (13.7KB) is read by no Python file — route descriptions come from `routes.yaml`. Either wire it back in or delete it.

## 6. No schema for the tile manifests

`catalog.json` is validated against `pipeline/src/open_rando/data/catalog.schema.json`, but the mobile client also reads `tiles/`-generated `grid.json` and `routes/{id}/pmtiles.json`, which have no contract — the same drift `c5ea355` already fixed by hand.

Done when both manifests have a JSON Schema, `build-grid.py` / `build-routes.py` validate their output, and CI runs that validation.

## 7. Trail gaps are recorded but never shown

`trail_gap_km`, `trail_segment_count` and the profile's `segment_boundaries_km` ship in the catalog and are read by nothing. A hiker planning GR 4 cannot see that it has a 19 km unmapped stretch until they are standing in it.

Done when the elevation chart marks the breaks and the route page states the gap, in both locales.

## 8. `website/.env.production` is required but absent

`.gitignore` whitelists it (`!website/.env.production`) while `ebb1c9b` deleted it, so a fresh clone builds a map with no base tiles. `bun run build` now fails loudly instead, and `docs/DEPLOYMENT.md` documents creating it, but the contradiction stands.

Done when the file is either committed (its value is a public `r2.dev` URL, already in the docs) or the `.gitignore` negation is dropped so its absence is intentional.
