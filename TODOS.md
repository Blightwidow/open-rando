# TODOs

Known work not yet done. Each entry says what is wrong, why it matters, and what "done" looks like.

## 1. Test the geometry code that keeps breaking

`pipeline/src/open_rando/processors/slice.py` (~500 lines) and `pipeline/src/open_rando/fetchers/overpass.py` (~376 lines) have no direct tests, while three separate commits fixed bugs in exactly that code: `1f3452c` (Overpass not fetching ways for simple routes), `f14dfeb` (MultiLineString extraction skipping gap jumps), `2e19acc` (trails not split at large gaps). Highest bug density, lowest coverage.

Done when:

- Fixture-based tests feed small hand-built Overpass relation JSON into the parser and assert the resulting geometry: simple route (ways only), super-relation recursion, member ordering, gap splitting, spurious fragment removal.
- `slice.py` has tests for `_extract_substring`, segment distance measurement, and junction cutting on both `LineString` and `MultiLineString` inputs, including a route whose geometry is reversed relative to the walking direction.
- Tests use synthetic geometry, no network.

## 2. Stop maintaining the site twice (FR/EN page forks)

`website/src/pages/app/route/[slug].astro` and `website/src/pages/en/app/route/[slug].astro` are 820-line near-copies (66 diff lines, almost all hardcoded strings). Same for `pages/app/index.astro` vs `pages/en/app/index.astro` (342 vs 340 lines). Every feature has to be written twice, and the rail-service work in this change had to be patched into both files separately — the EN copy silently used a different relative import depth.

Done when:

- Astro i18n routing (`astro.config.mjs` already declares `i18n` with `fr` default and `prefixDefaultLocale: false`) serves both locales from one template per page, with all copy from `src/lib/i18n.ts`.
- No page file exists only to restate another page in a different language.
- The 820-line detail page's inline scripts are split into modules (map setup, section selector, QR code, elevation sync) so the template is readable.

## 3. README is out of date

`README.md` describes a stack the repo no longer has:

- Says Leaflet; the site uses `maplibre-gl` + `pmtiles`.
- Says Python 3.13+ in one place while `CLAUDE.md` says 3.12+ (`pyproject.toml` requires >=3.13).
- Documents `uv run python -m open_rando` without the `pipeline` subcommand introduced in `3765102`, and the `--route/--dry-run/--reset` flags at the wrong level.
- No mention of `tiles/`, the `images` subcommand, mobile offline PMTiles, the run report, or the local OSM extracts (`Makefile.osm` + `osm-index`).

Done when the README matches the current commands, stack and directory layout, and stops duplicating what `docs/` already explains.

## 4. Dead i18n keys from the removed step planner

`website/src/lib/i18n.ts` still carries keys no page or script reads: `filters.maxStep`, `filters.steps`, `filters.difficulty`, `filters.accommodation`, `filters.hotel`, `filters.camping`, `steps.label`, `detail.stepCount`, `detail.steps`, `detail.stations`, `detail.difficulty`, `hike.loop`, `hike.loopFrom`, `map.steps`. They are leftovers of the step-based planner replaced in `66614d1`. `getClientTranslations()` is itself unused outside its own test.

Done when every key in `i18n.ts` is referenced by a page, component or script, and `getClientTranslations` is either used or removed. A test that fails on an unreferenced key would keep it that way.

## 5. Unused packaged data file

`pipeline/src/open_rando/data/gr-descriptions.yaml` (13.7KB) is not read by any Python file — route descriptions now come from `routes.yaml`. Either wire it back in or delete it.

## 6. No schema for the tile manifests

`catalog.json` is now validated against `pipeline/src/open_rando/data/catalog.schema.json`, but the mobile client also reads `tiles/`-generated `grid.json` and `routes/{id}/pmtiles.json`, which have no contract. Same drift risk that `c5ea355` already fixed once by hand.

Done when both manifests have a JSON Schema, `build-grid.py` / `build-routes.py` validate their output, and CI runs that validation.

## 7. Elevation gain and loss measure net drift, not climb

`processors/elevation.py:_compute_gain_loss` accumulates a signed running sum and only commits it when that sum crosses zero, so a profile that never returns to its starting elevation is committed once, at the end. The result is the net difference between start and finish rather than cumulative ascent:

| Route | Distance | Elevation range | Reported gain | Plausible gain |
|-------|----------|-----------------|---------------|----------------|
| GR 10 (Pyrenees) | 1100 km | 0.5 - 2734 m | **986 m** | tens of thousands |
| GR 2 (Seine) | 1126 km | -7 - 575 m | **0 m** | thousands |
| GR 137 (Morvan) | 53 km | 312 - 580 m | **12 m** | ~1000 |
| GR 1 (Ile-de-France) | 581 km | 15 - 217 m | **198 m** | thousands |

The elevation samples themselves are sound (GR 10 has 13914 distinct values from 22011 samples, no missing SRTM tiles), so this is purely the accumulation logic.

Knock-on effects: `classify_difficulty` keys off `gain_m`, so nearly every route lands in `easy`; the website shows the same wrong figures; `estimate_duration` under-estimates. Per-sample walking times in `_compute_cumulative_times` are computed independently and are not affected.

Done when gain/loss track monotone runs with hysteresis — accumulate a run, commit it on reversal when it exceeds `ELEVATION_NOISE_THRESHOLD_METERS`, absorb it as noise otherwise — with tests for a monotone climb, a sawtooth, and a flat profile carrying SRTM oscillation. Difficulty thresholds in `classify_difficulty` will need re-tuning against the corrected values, and the run report should flag routes whose gain changes by more than a set ratio.

## 8. `trail_gap_km` depends on the order segments happen to be stored in

Gaps are summed end-to-start over the stored segment sequence, but nothing orders that sequence along the route, so a trail mapped in scattered pieces reports jumps between pieces that are nowhere near each other. GR 70 (Chemin de Stevenson, 208.8 km) reports **213.0 km of gaps** — more gap than trail:

| Segment | Length | From → to |
|---------|--------|-----------|
| 0 | 144.2 km | 44.94,3.99 → 44.36,3.74 |
| 1 | 22.3 km | 44.22,3.81 → 44.11,3.89 |
| 2 | 19.4 km | 44.94,3.99 → 45.04,3.89 |
| 3 | 23.0 km | 44.13,4.07 → 44.11,3.89 |

Stored-order jumps are 16.9, 93.1 and 103.0 km, but segment 2 starts exactly where segment 0 starts — it is the northern extension, so walking order is 2, 0, 1, 3 and only the 16.9 km jump is a real gap. 23 routes carry multi-segment trails and 2628 km of reported gaps, most of it this artifact.

Done when segments are ordered by endpoint connectivity (greedy nearest-endpoint chaining, or a proper connectivity graph) before the trail is stored, so consecutive jumps are the real unmapped stretches. The elevation profile and station distances derive from the same order, so they improve with it. This is the same underlying weakness as #1: `_drop_spurious_segments` and the chaining compare everything against the single longest segment instead of modelling how the pieces join.
