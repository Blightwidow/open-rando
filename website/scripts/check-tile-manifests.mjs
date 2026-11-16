// The mobile app reads /data/grid.json and /data/routes/<id>/pmtiles.json from the
// published site. The data pipeline does not write them (tiles/build-grid.py and
// build-routes.py do, into the same data dir), so a data dir without them builds
// and deploys fine while both files answer 404 in production.
//
// Usage: bun scripts/check-tile-manifests.mjs [data-directory]   (default: dist/data)
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const MAX_REPORTED_PROBLEMS = 10;

function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, 'utf-8'));
  } catch {
    return null;
  }
}

/** What is wrong with the tile manifests in a built data directory; empty when they are all there. */
export function findTileManifestProblems(dataDirectory) {
  const gridFile = join(dataDirectory, 'grid.json');
  if (!existsSync(gridFile)) return ['grid.json is missing'];
  const grid = readJson(gridFile);
  if (!grid || typeof grid.squares !== 'object' || grid.squares === null) {
    return ['grid.json is not valid JSON with a "squares" map'];
  }

  const catalog = readJson(join(dataDirectory, 'catalog.json'));
  if (!catalog || !Array.isArray(catalog.routes)) {
    return ['catalog.json is missing or has no "routes" list, so route manifests cannot be checked'];
  }

  const problems = [];
  for (const route of catalog.routes) {
    const manifestFile = join(dataDirectory, 'routes', route.id, 'pmtiles.json');
    if (!existsSync(manifestFile)) {
      problems.push(`routes/${route.id}/pmtiles.json is missing`);
      continue;
    }
    const manifest = readJson(manifestFile);
    if (!manifest || !Array.isArray(manifest.squares)) {
      problems.push(`routes/${route.id}/pmtiles.json has no "squares" list`);
      continue;
    }
    for (const [column, row] of manifest.squares) {
      if (!(`${column}_${row}` in grid.squares)) {
        problems.push(`routes/${route.id}/pmtiles.json lists square ${column}_${row}, which is not in grid.json`);
      }
    }
  }
  return problems;
}

if (import.meta.main) {
  const dataDirectory = process.argv[2] ?? 'dist/data';
  const problems = findTileManifestProblems(dataDirectory);
  if (problems.length > 0) {
    const shown = problems.slice(0, MAX_REPORTED_PROBLEMS);
    const hidden = problems.length - shown.length;
    console.error(
      [
        '',
        `Tile manifests in ${dataDirectory} are not publishable:`,
        ...shown.map((problem) => `  - ${problem}`),
        ...(hidden > 0 ? [`  ... and ${hidden} more`] : []),
        '',
        'The mobile app would get a 404 on /data/grid.json. Build them (see docs/DEPLOYMENT.md):',
        '  cd tiles',
        '  make -f Makefile.routes grid-manifest-from-r2   # or build-grid with the master archives',
        '  make -f Makefile.routes build-routes',
        '',
        'To publish without them on purpose:',
        '  ALLOW_MISSING_TILE_MANIFESTS=1 bun run deploy',
        '',
      ].join('\n'),
    );
    process.exit(1);
  }
  console.log(`Tile manifests OK in ${dataDirectory}`);
}
