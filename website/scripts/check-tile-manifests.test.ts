import { afterEach, beforeEach, describe, expect, test } from 'bun:test';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { findTileManifestProblems } from './check-tile-manifests.mjs';

let dataDirectory: string;

function writeJson(relativePath: string, content: unknown): void {
  const file = join(dataDirectory, relativePath);
  mkdirSync(join(file, '..'), { recursive: true });
  writeFileSync(file, JSON.stringify(content));
}

function writeCompleteData(): void {
  writeJson('catalog.json', { routes: [{ id: 'abc' }, { id: 'def' }] });
  writeJson('grid.json', { version: 2, squares: { '5_5': {}, '5_6': {} } });
  writeJson('routes/abc/pmtiles.json', { route_id: 'abc', squares: [[5, 5]] });
  writeJson('routes/def/pmtiles.json', { route_id: 'def', squares: [[5, 5], [5, 6]] });
}

beforeEach(() => {
  dataDirectory = mkdtempSync(join(tmpdir(), 'tile-manifests-'));
});

afterEach(() => {
  rmSync(dataDirectory, { recursive: true, force: true });
});

describe('findTileManifestProblems', () => {
  test('complete data has no problem', () => {
    writeCompleteData();

    expect(findTileManifestProblems(dataDirectory)).toEqual([]);
  });

  test('a missing grid.json is reported', () => {
    writeCompleteData();
    rmSync(join(dataDirectory, 'grid.json'));

    expect(findTileManifestProblems(dataDirectory)).toEqual(['grid.json is missing']);
  });

  test('a grid.json that is not a squares map is reported', () => {
    writeCompleteData();
    writeJson('grid.json', { version: 2 });

    expect(findTileManifestProblems(dataDirectory)[0]).toContain('"squares" map');
  });

  test('a route without a manifest is reported by id', () => {
    writeCompleteData();
    rmSync(join(dataDirectory, 'routes/def'), { recursive: true });

    expect(findTileManifestProblems(dataDirectory)).toEqual(['routes/def/pmtiles.json is missing']);
  });

  test('a route square absent from grid.json is reported', () => {
    writeCompleteData();
    writeJson('routes/abc/pmtiles.json', { route_id: 'abc', squares: [[9, 9]] });

    expect(findTileManifestProblems(dataDirectory)).toEqual([
      'routes/abc/pmtiles.json lists square 9_9, which is not in grid.json',
    ]);
  });

  test('a missing catalog is reported because routes cannot be checked', () => {
    writeCompleteData();
    rmSync(join(dataDirectory, 'catalog.json'));

    expect(findTileManifestProblems(dataDirectory)[0]).toContain('catalog.json');
  });

  test('a catalog with no routes needs no route manifest', () => {
    writeJson('catalog.json', { routes: [] });
    writeJson('grid.json', { version: 2, squares: {} });

    expect(findTileManifestProblems(dataDirectory)).toEqual([]);
  });
});
