// Generate TypeScript types from the pipeline's JSON Schemas, the single source
// of the data contract. One file per schema in src/lib/generated/.
//
//   bun scripts/generate-types.mjs                 write the files
//   bun scripts/generate-types.mjs --check         exit 1 when a file is stale (CI)
//   bun scripts/generate-types.mjs --out-dir DIR   write elsewhere (e.g. the mobile app)

import { readdirSync, readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileFromFile } from 'json-schema-to-typescript';

const websiteDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const schemaDirectory = resolve(websiteDirectory, '../pipeline/src/open_rando/data');

const argumentsList = process.argv.slice(2);
const checkOnly = argumentsList.includes('--check');
const outDirectoryIndex = argumentsList.indexOf('--out-dir');
const outputDirectory =
  outDirectoryIndex >= 0
    ? resolve(argumentsList[outDirectoryIndex + 1])
    : join(websiteDirectory, 'src/lib/generated');

const banner = (schemaFileName) =>
  `// Generated from pipeline/src/open_rando/data/${schemaFileName} by\n` +
  `// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun\n` +
  `// \`bun run generate:types\`.\n`;

const schemaFileNames = readdirSync(schemaDirectory)
  .filter((fileName) => fileName.endsWith('.schema.json'))
  .sort();

const staleFiles = [];
for (const schemaFileName of schemaFileNames) {
  const typeScript = await compileFromFile(join(schemaDirectory, schemaFileName), {
    bannerComment: banner(schemaFileName),
    additionalProperties: false,
    format: true,
    style: { singleQuote: true, printWidth: 100 },
  });
  const outputPath = join(outputDirectory, schemaFileName.replace('.schema.json', '.ts'));
  const current = existsSync(outputPath) ? readFileSync(outputPath, 'utf-8') : null;
  if (current === typeScript) continue;
  if (checkOnly) {
    staleFiles.push(outputPath);
    continue;
  }
  mkdirSync(outputDirectory, { recursive: true });
  writeFileSync(outputPath, typeScript);
  console.log(`wrote ${outputPath}`);
}

if (staleFiles.length > 0) {
  console.error(
    `Generated types are stale, run \`bun run generate:types\` in website/:\n  ${staleFiles.join('\n  ')}`,
  );
  process.exit(1);
}
