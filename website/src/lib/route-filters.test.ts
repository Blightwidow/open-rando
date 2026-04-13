import { describe, expect, test } from 'bun:test';
import { matchesRouteFilters, defaultRouteFilterState, isFilterActive } from './route-filters';
import type { RouteFilterData, RouteFilterState } from './route-filters';

function makeRoute(overrides: Partial<RouteFilterData> = {}): RouteFilterData {
  return {
    region: 'Île-de-France',
    terrainTags: ['forest', 'hills'],
    ...overrides,
  };
}

// ── defaultRouteFilterState ───────────────────────────────────────────────

describe('defaultRouteFilterState', () => {
  test('returns empty sets', () => {
    const filters = defaultRouteFilterState();
    expect(filters.regions.size).toBe(0);
    expect(filters.terrains.size).toBe(0);
  });
});

// ── isFilterActive ────────────────────────────────────────────────────────

describe('isFilterActive', () => {
  test('false when all sets empty', () => {
    expect(isFilterActive(defaultRouteFilterState())).toBe(false);
  });

  test('true when regions set', () => {
    const filters = defaultRouteFilterState();
    filters.regions.add('Bretagne');
    expect(isFilterActive(filters)).toBe(true);
  });

  test('true when terrains set', () => {
    const filters = defaultRouteFilterState();
    filters.terrains.add('forest');
    expect(isFilterActive(filters)).toBe(true);
  });
});

// ── matchesRouteFilters ───────────────────────────────────────────────────

describe('matchesRouteFilters', () => {
  test('matches everything when no filters active', () => {
    const route = makeRoute();
    const filters = defaultRouteFilterState();
    expect(matchesRouteFilters(route, filters)).toBe(true);
  });

  test('filters by region', () => {
    const route = makeRoute({ region: 'Bretagne' });
    const filters = defaultRouteFilterState();
    filters.regions.add('Provence');
    expect(matchesRouteFilters(route, filters)).toBe(false);
  });

  test('matches region', () => {
    const route = makeRoute({ region: 'Bretagne' });
    const filters = defaultRouteFilterState();
    filters.regions.add('Bretagne');
    expect(matchesRouteFilters(route, filters)).toBe(true);
  });

  test('filters by terrain — no overlap', () => {
    const route = makeRoute({ terrainTags: ['coastal'] });
    const filters = defaultRouteFilterState();
    filters.terrains.add('mountain');
    expect(matchesRouteFilters(route, filters)).toBe(false);
  });

  test('matches terrain — partial overlap', () => {
    const route = makeRoute({ terrainTags: ['forest', 'hills'] });
    const filters = defaultRouteFilterState();
    filters.terrains.add('hills');
    expect(matchesRouteFilters(route, filters)).toBe(true);
  });

  test('empty terrain tags rejected when terrain filter active', () => {
    const route = makeRoute({ terrainTags: [] });
    const filters = defaultRouteFilterState();
    filters.terrains.add('forest');
    expect(matchesRouteFilters(route, filters)).toBe(false);
  });

  test('combined filters — all must pass', () => {
    const route = makeRoute({ region: 'Bretagne', terrainTags: ['coastal'] });
    const filters: RouteFilterState = {
      regions: new Set(['Bretagne']),
      terrains: new Set(['coastal']),
    };
    expect(matchesRouteFilters(route, filters)).toBe(true);
  });

  test('combined filters — one fails', () => {
    const route = makeRoute({ region: 'Bretagne', terrainTags: ['coastal'] });
    const filters: RouteFilterState = {
      regions: new Set(['Provence']),
      terrains: new Set(['coastal']),
    };
    expect(matchesRouteFilters(route, filters)).toBe(false);
  });

  test('multiple values in filter — any match suffices', () => {
    const route = makeRoute({ region: 'Bretagne' });
    const filters = defaultRouteFilterState();
    filters.regions.add('Provence');
    filters.regions.add('Bretagne');
    expect(matchesRouteFilters(route, filters)).toBe(true);
  });
});
