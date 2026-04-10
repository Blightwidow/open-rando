import { describe, expect, test } from 'bun:test';
import { matchesFilters } from './filters';
import type { FilterState, HikeFilterData } from './filters';

function makeDefaultFilters(overrides?: Partial<FilterState>): FilterState {
  return {
    maxStepDistance: 20,
    stepsMin: 1,
    stepsMax: 10,
    requireHotel: false,
    requireCamping: false,
    difficulties: new Set(),
    routeTypes: new Set(),
    regions: new Set(),
    terrains: new Set(),
    ...overrides,
  };
}

function makeDefaultHike(overrides?: Partial<HikeFilterData>): HikeFilterData {
  return {
    maxStepDistance: 15,
    stepCount: 3,
    hotelAllStops: true,
    campingAllStops: false,
    difficulty: 'moderate',
    routeType: 'gr',
    region: 'Bretagne',
    terrainTags: ['coastal', 'forest'],
    suggestHidden: false,
    ...overrides,
  };
}

describe('matchesFilters', () => {
  test('all defaults pass', () => {
    expect(matchesFilters(makeDefaultHike(), makeDefaultFilters())).toBe(true);
  });

  test('suggestHidden rejects', () => {
    expect(matchesFilters(makeDefaultHike({ suggestHidden: true }), makeDefaultFilters())).toBe(false);
  });

  test('maxStepDistance over limit rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ maxStepDistance: 25 }),
      makeDefaultFilters({ maxStepDistance: 20 })
    )).toBe(false);
  });

  test('maxStepDistance at limit passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ maxStepDistance: 20 }),
      makeDefaultFilters({ maxStepDistance: 20 })
    )).toBe(true);
  });

  test('step count below minimum rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ stepCount: 1 }),
      makeDefaultFilters({ stepsMin: 2 })
    )).toBe(false);
  });

  test('step count above maximum rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ stepCount: 5 }),
      makeDefaultFilters({ stepsMax: 4 })
    )).toBe(false);
  });

  test('step count within range passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ stepCount: 3 }),
      makeDefaultFilters({ stepsMin: 2, stepsMax: 5 })
    )).toBe(true);
  });

  test('hotel required but not available rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ hotelAllStops: false }),
      makeDefaultFilters({ requireHotel: true })
    )).toBe(false);
  });

  test('hotel required and available passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ hotelAllStops: true }),
      makeDefaultFilters({ requireHotel: true })
    )).toBe(true);
  });

  test('camping required but not available rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ campingAllStops: false }),
      makeDefaultFilters({ requireCamping: true })
    )).toBe(false);
  });

  test('difficulty not in set rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ difficulty: 'moderate' }),
      makeDefaultFilters({ difficulties: new Set(['easy']) })
    )).toBe(false);
  });

  test('difficulty in set passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ difficulty: 'moderate' }),
      makeDefaultFilters({ difficulties: new Set(['easy', 'moderate']) })
    )).toBe(true);
  });

  test('empty difficulty set accepts all', () => {
    expect(matchesFilters(
      makeDefaultHike({ difficulty: 'very_difficult' }),
      makeDefaultFilters({ difficulties: new Set() })
    )).toBe(true);
  });

  test('route type not in set rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ routeType: 'pr' }),
      makeDefaultFilters({ routeTypes: new Set(['gr']) })
    )).toBe(false);
  });

  test('route type in set passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ routeType: 'gr' }),
      makeDefaultFilters({ routeTypes: new Set(['gr', 'grp']) })
    )).toBe(true);
  });

  test('region not in set rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ region: 'Normandie' }),
      makeDefaultFilters({ regions: new Set(['Bretagne']) })
    )).toBe(false);
  });

  test('region in set passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ region: 'Bretagne' }),
      makeDefaultFilters({ regions: new Set(['Bretagne', 'Normandie']) })
    )).toBe(true);
  });

  test('terrain uses OR logic - one matching tag passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ terrainTags: ['coastal', 'forest'] }),
      makeDefaultFilters({ terrains: new Set(['mountain', 'coastal']) })
    )).toBe(true);
  });

  test('terrain with no matching tags rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ terrainTags: ['forest', 'plains'] }),
      makeDefaultFilters({ terrains: new Set(['coastal', 'mountain']) })
    )).toBe(false);
  });

  test('empty terrain set accepts all', () => {
    expect(matchesFilters(
      makeDefaultHike({ terrainTags: ['forest'] }),
      makeDefaultFilters({ terrains: new Set() })
    )).toBe(true);
  });

  test('combined filters all must pass', () => {
    expect(matchesFilters(
      makeDefaultHike({
        maxStepDistance: 15,
        stepCount: 3,
        difficulty: 'moderate',
        routeType: 'gr',
        region: 'Bretagne',
        terrainTags: ['coastal'],
        hotelAllStops: true,
      }),
      makeDefaultFilters({
        maxStepDistance: 20,
        stepsMin: 2,
        stepsMax: 5,
        requireHotel: true,
        difficulties: new Set(['moderate', 'difficult']),
        routeTypes: new Set(['gr']),
        regions: new Set(['Bretagne']),
        terrains: new Set(['coastal']),
      })
    )).toBe(true);
  });

  test('combined filters one failing rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({
        maxStepDistance: 15,
        difficulty: 'easy', // not in set
      }),
      makeDefaultFilters({
        difficulties: new Set(['moderate', 'difficult']),
      })
    )).toBe(false);
  });
});
