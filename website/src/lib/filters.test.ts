import { describe, expect, test } from 'bun:test';
import { matchesFilters, findLongestMatchingSection } from './filters';
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
    stepDistances: [12, 15, 10],
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

describe('findLongestMatchingSection', () => {
  test('all steps fit returns full range', () => {
    expect(findLongestMatchingSection([10, 12, 8], 15)).toEqual({ from: 0, to: 3, length: 3 });
  });

  test('no steps fit returns null', () => {
    expect(findLongestMatchingSection([20, 25, 30], 15)).toBeNull();
  });

  test('single matching step', () => {
    expect(findLongestMatchingSection([25, 10, 30], 15)).toEqual({ from: 1, to: 2, length: 1 });
  });

  test('longest contiguous section at start', () => {
    expect(findLongestMatchingSection([10, 12, 25, 8], 15)).toEqual({ from: 0, to: 2, length: 2 });
  });

  test('longest contiguous section at end', () => {
    expect(findLongestMatchingSection([25, 8, 10, 12], 15)).toEqual({ from: 1, to: 4, length: 3 });
  });

  test('picks longest when multiple sections exist', () => {
    expect(findLongestMatchingSection([10, 25, 8, 12, 11], 15)).toEqual({ from: 2, to: 5, length: 3 });
  });

  test('empty array returns null', () => {
    expect(findLongestMatchingSection([], 15)).toBeNull();
  });

  test('step exactly at limit is included', () => {
    expect(findLongestMatchingSection([15, 15], 15)).toEqual({ from: 0, to: 2, length: 2 });
  });
});

describe('matchesFilters', () => {
  test('all defaults pass with no section match', () => {
    const result = matchesFilters(makeDefaultHike(), makeDefaultFilters());
    expect(result.visible).toBe(true);
    expect(result.sectionMatch).toBeNull();
  });

  test('suggestHidden rejects', () => {
    expect(matchesFilters(makeDefaultHike({ suggestHidden: true }), makeDefaultFilters()).visible).toBe(false);
  });

  test('maxStepDistance over limit but section fits passes with sectionMatch', () => {
    const result = matchesFilters(
      makeDefaultHike({ maxStepDistance: 25, stepCount: 4, stepDistances: [10, 12, 25, 8] }),
      makeDefaultFilters({ maxStepDistance: 20 })
    );
    expect(result.visible).toBe(true);
    expect(result.sectionMatch).toEqual({ from: 0, to: 2, length: 2 });
  });

  test('maxStepDistance over limit and no section fits rejects', () => {
    const result = matchesFilters(
      makeDefaultHike({ maxStepDistance: 25, stepCount: 2, stepDistances: [25, 22] }),
      makeDefaultFilters({ maxStepDistance: 20 })
    );
    expect(result.visible).toBe(false);
  });

  test('maxStepDistance at limit passes without section match', () => {
    const result = matchesFilters(
      makeDefaultHike({ maxStepDistance: 20, stepDistances: [20, 15, 18] }),
      makeDefaultFilters({ maxStepDistance: 20 })
    );
    expect(result.visible).toBe(true);
    expect(result.sectionMatch).toBeNull();
  });

  test('step count filter applies to section length for section matches', () => {
    // Section has 2 steps but filter requires min 3
    const result = matchesFilters(
      makeDefaultHike({ maxStepDistance: 25, stepCount: 4, stepDistances: [10, 12, 25, 25] }),
      makeDefaultFilters({ maxStepDistance: 20, stepsMin: 3 })
    );
    expect(result.visible).toBe(false);
  });

  test('step count filter applies to full hike for full matches', () => {
    const result = matchesFilters(
      makeDefaultHike({ maxStepDistance: 15, stepCount: 3, stepDistances: [12, 15, 10] }),
      makeDefaultFilters({ maxStepDistance: 20, stepsMin: 2, stepsMax: 5 })
    );
    expect(result.visible).toBe(true);
    expect(result.sectionMatch).toBeNull();
  });

  test('step count below minimum rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ stepCount: 1, stepDistances: [12] }),
      makeDefaultFilters({ stepsMin: 2 })
    ).visible).toBe(false);
  });

  test('step count above maximum rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ stepCount: 5, stepDistances: [10, 12, 8, 11, 9] }),
      makeDefaultFilters({ stepsMax: 4 })
    ).visible).toBe(false);
  });

  test('step count within range passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ stepCount: 3, stepDistances: [12, 15, 10] }),
      makeDefaultFilters({ stepsMin: 2, stepsMax: 5 })
    ).visible).toBe(true);
  });

  test('hotel required but not available rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ hotelAllStops: false }),
      makeDefaultFilters({ requireHotel: true })
    ).visible).toBe(false);
  });

  test('hotel required and available passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ hotelAllStops: true }),
      makeDefaultFilters({ requireHotel: true })
    ).visible).toBe(true);
  });

  test('camping required but not available rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ campingAllStops: false }),
      makeDefaultFilters({ requireCamping: true })
    ).visible).toBe(false);
  });

  test('difficulty not in set rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ difficulty: 'moderate' }),
      makeDefaultFilters({ difficulties: new Set(['easy']) })
    ).visible).toBe(false);
  });

  test('difficulty in set passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ difficulty: 'moderate' }),
      makeDefaultFilters({ difficulties: new Set(['easy', 'moderate']) })
    ).visible).toBe(true);
  });

  test('empty difficulty set accepts all', () => {
    expect(matchesFilters(
      makeDefaultHike({ difficulty: 'very_difficult' }),
      makeDefaultFilters({ difficulties: new Set() })
    ).visible).toBe(true);
  });

  test('route type not in set rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ routeType: 'pr' }),
      makeDefaultFilters({ routeTypes: new Set(['gr']) })
    ).visible).toBe(false);
  });

  test('route type in set passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ routeType: 'gr' }),
      makeDefaultFilters({ routeTypes: new Set(['gr', 'grp']) })
    ).visible).toBe(true);
  });

  test('region not in set rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ region: 'Normandie' }),
      makeDefaultFilters({ regions: new Set(['Bretagne']) })
    ).visible).toBe(false);
  });

  test('region in set passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ region: 'Bretagne' }),
      makeDefaultFilters({ regions: new Set(['Bretagne', 'Normandie']) })
    ).visible).toBe(true);
  });

  test('terrain uses OR logic - one matching tag passes', () => {
    expect(matchesFilters(
      makeDefaultHike({ terrainTags: ['coastal', 'forest'] }),
      makeDefaultFilters({ terrains: new Set(['mountain', 'coastal']) })
    ).visible).toBe(true);
  });

  test('terrain with no matching tags rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({ terrainTags: ['forest', 'plains'] }),
      makeDefaultFilters({ terrains: new Set(['coastal', 'mountain']) })
    ).visible).toBe(false);
  });

  test('empty terrain set accepts all', () => {
    expect(matchesFilters(
      makeDefaultHike({ terrainTags: ['forest'] }),
      makeDefaultFilters({ terrains: new Set() })
    ).visible).toBe(true);
  });

  test('combined filters all must pass', () => {
    expect(matchesFilters(
      makeDefaultHike({
        maxStepDistance: 15,
        stepCount: 3,
        stepDistances: [12, 15, 10],
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
    ).visible).toBe(true);
  });

  test('combined filters one failing rejects', () => {
    expect(matchesFilters(
      makeDefaultHike({
        maxStepDistance: 15,
        stepDistances: [12, 15, 10],
        difficulty: 'easy', // not in set
      }),
      makeDefaultFilters({
        difficulties: new Set(['moderate', 'difficult']),
      })
    ).visible).toBe(false);
  });

  test('section match still checks non-distance filters', () => {
    const result = matchesFilters(
      makeDefaultHike({
        maxStepDistance: 25,
        stepCount: 3,
        stepDistances: [10, 25, 8],
        difficulty: 'easy',
      }),
      makeDefaultFilters({
        maxStepDistance: 20,
        difficulties: new Set(['moderate']),
      })
    );
    expect(result.visible).toBe(false);
  });
});
