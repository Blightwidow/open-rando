import { describe, expect, test } from 'bun:test';
import {
  buildCumulativeDistancesKm,
  collectTrailCoordinates,
  findIndexAtDistance,
  findSectionIndexRange,
  haversineKm,
  interpolateAtDistance,
  orderSectionBounds,
  type LatLon,
} from './trail-geometry';

const KILOMETERS_PER_DEGREE_OF_LATITUDE = 111.195;

describe('haversineKm', () => {
  test('is zero between identical points', () => {
    expect(haversineKm(45, 5, 45, 5)).toBe(0);
  });

  test('one degree of latitude is about 111 km', () => {
    expect(haversineKm(45, 5, 46, 5)).toBeCloseTo(KILOMETERS_PER_DEGREE_OF_LATITUDE, 1);
  });
});

describe('collectTrailCoordinates', () => {
  test('swaps GeoJSON [lon, lat] into [lat, lon]', () => {
    const coordinates = collectTrailCoordinates([
      { geometry: { type: 'LineString', coordinates: [[5, 45], [6, 46]] } },
    ]);

    expect(coordinates).toEqual([[45, 5], [46, 6]]);
  });

  test('concatenates every line of a MultiLineString in order', () => {
    const coordinates = collectTrailCoordinates([
      { geometry: { type: 'MultiLineString', coordinates: [[[0, 1]], [[2, 3], [4, 5]]] } },
    ]);

    expect(coordinates).toEqual([[1, 0], [3, 2], [5, 4]]);
  });
});

describe('buildCumulativeDistancesKm', () => {
  test('starts at zero', () => {
    expect(buildCumulativeDistancesKm([[45, 5], [46, 5]])[0]).toBe(0);
  });

  test('adds the distance of each step', () => {
    const distances = buildCumulativeDistancesKm([[45, 5], [46, 5], [47, 5]]);

    expect(distances[2]).toBeCloseTo(2 * KILOMETERS_PER_DEGREE_OF_LATITUDE, 1);
  });

  test('a single point has no distance', () => {
    expect(buildCumulativeDistancesKm([[45, 5]])).toEqual([0]);
  });
});

describe('findIndexAtDistance', () => {
  const distances = [0, 10, 20, 30];

  test('returns the last index at or below the target', () => {
    expect(findIndexAtDistance(distances, 15)).toBe(1);
  });

  test('an exact match returns that index', () => {
    expect(findIndexAtDistance(distances, 20)).toBe(2);
  });

  test('a target before the start returns the first index', () => {
    expect(findIndexAtDistance(distances, -5)).toBe(0);
  });

  test('a target past the end stops one before the last index', () => {
    expect(findIndexAtDistance(distances, 99)).toBe(2);
  });
});

describe('orderSectionBounds', () => {
  test('keeps an ordered pair', () => {
    expect(orderSectionBounds(2, 8)).toEqual({ startKm: 2, endKm: 8 });
  });

  test('swaps a reversed pair', () => {
    expect(orderSectionBounds(8, 2)).toEqual({ startKm: 2, endKm: 8 });
  });
});

describe('findSectionIndexRange', () => {
  const distances = [0, 10, 20, 30, 40];

  test('ends one point after the point at the end distance', () => {
    expect(findSectionIndexRange(distances, 10, 20)).toEqual({ startIndex: 1, endIndex: 3 });
  });

  test('never runs past the last coordinate', () => {
    expect(findSectionIndexRange(distances, 10, 99).endIndex).toBe(4);
  });
});

describe('interpolateAtDistance', () => {
  const coordinates: LatLon[] = [[0, 0], [0, 10], [0, 20]];
  const distances = [0, 10, 20];

  test('halfway between two points is their midpoint', () => {
    expect(interpolateAtDistance(coordinates, distances, 5)).toEqual([0, 5]);
  });

  test('the total distance lands on the last point', () => {
    expect(interpolateAtDistance(coordinates, distances, 20)).toEqual([0, 20]);
  });

  test('zero lands on the first point', () => {
    expect(interpolateAtDistance(coordinates, distances, 0)).toEqual([0, 0]);
  });
});
