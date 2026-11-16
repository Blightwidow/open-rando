import { describe, expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { getTranslationKeys } from './i18n';

const SOURCE_DIRECTORY = join(import.meta.dir, '..');

/** Every page, component and script that can ask for a translation (the dictionary and tests excluded). */
function readSources(): string {
  const glob = new Bun.Glob('**/*.{astro,ts}');
  return [...glob.scanSync({ cwd: SOURCE_DIRECTORY })]
    .filter((file) => file !== 'lib/i18n.ts' && !file.endsWith('.test.ts'))
    .map((file) => readFileSync(join(SOURCE_DIRECTORY, file), 'utf-8'))
    .join('\n');
}

describe('translation keys', () => {
  test('French and English define the same keys', () => {
    expect(getTranslationKeys('en').sort()).toEqual(getTranslationKeys('fr').sort());
  });

  test('every key is read by a page, component or script', () => {
    const sources = readSources();

    const unreferenced = getTranslationKeys('fr').filter(
      (key) => !sources.includes(`'${key}'`) && !sources.includes(`"${key}"`),
    );

    expect(unreferenced).toEqual([]);
  });

  test('every key asked for in a page, component or script exists', () => {
    const known = new Set(getTranslationKeys('fr'));
    const requested = [...readSources().matchAll(/\bt\(\s*[A-Za-z]+,\s*'([^']+)'/g)].map((match) => match[1]);

    expect(requested.filter((key) => !known.has(key))).toEqual([]);
  });
});
