// A build without PUBLIC_PMTILES_BASE silently ships a map with no background:
// the styles keep their site-relative pmtiles:/// URLs, and prebuild excludes
// *.pmtiles from public/data, so every base tile 404s in production.
import { existsSync, readFileSync } from 'node:fs';

const VARIABLE = 'PUBLIC_PMTILES_BASE';
const ENV_FILE = new URL('../.env.production', import.meta.url);

function isConfigured() {
  if (process.env[VARIABLE]) return true;
  if (!existsSync(ENV_FILE)) return false;
  return readFileSync(ENV_FILE, 'utf-8')
    .split('\n')
    .some((line) => line.trim().startsWith(`${VARIABLE}=`) && line.trim() !== `${VARIABLE}=`);
}

if (!isConfigured()) {
  console.error(
    [
      '',
      `Missing ${VARIABLE} — the built map would have no background.`,
      '',
      'Set it in website/.env.production (see docs/DEPLOYMENT.md):',
      '  PUBLIC_PMTILES_BASE=https://pub-8869314668be498091e185b1a6fe798d.r2.dev',
      '',
      'For a build that deliberately has no base tiles:',
      '  ALLOW_MISSING_PMTILES_BASE=1 bun run build',
      '',
    ].join('\n'),
  );
  process.exit(1);
}
