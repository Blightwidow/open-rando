import { describe, expect, test } from 'bun:test';
import { squareFileName, squaresForBoundingBox, type PoiGridDefinition } from './poi-grid';

const GRID: PoiGridDefinition = { bbox: [-5.5, 41.0, 10.0, 51.5], cols: 12, rows: 8 };

describe('squaresForBoundingBox', () => {
  test('box inside one square returns that square', () => {
    expect(squaresForBoundingBox(GRID, [4.9, 45.7, 5.0, 45.8])).toEqual([[8, 3]]);
  });

  test('box straddling a column boundary returns both squares', () => {
    const boundaryLon = -5.5 + (15.5 / 12) * 8;
    expect(squaresForBoundingBox(GRID, [boundaryLon - 0.01, 45.7, boundaryLon + 0.01, 45.8])).toEqual([
      [7, 3],
      [8, 3],
    ]);
  });

  test('margin widens the selection in both directions', () => {
    const boundaryLon = -5.5 + (15.5 / 12) * 8;
    const bbox: [number, number, number, number] = [boundaryLon - 0.5, 45.7, boundaryLon - 0.4, 45.8];
    expect(squaresForBoundingBox(GRID, bbox)).toEqual([[7, 3]]);
    expect(squaresForBoundingBox(GRID, bbox, 0.5)).toEqual([
      [7, 3],
      [8, 3],
      [7, 4],
      [8, 4],
    ]);
  });

  test('box outside the grid returns nothing', () => {
    expect(squaresForBoundingBox(GRID, [20, 30, 21, 31])).toEqual([]);
  });

  test('box reaching past the grid is clamped to it', () => {
    expect(squaresForBoundingBox(GRID, [-9, 40, -8, 41.5])).toEqual([]);
    expect(squaresForBoundingBox(GRID, [9.9, 51.4, 12, 53])).toEqual([[11, 7]]);
  });
});

describe('squareFileName', () => {
  test('column then row', () => {
    expect(squareFileName([3, 4])).toBe('3_4.json');
  });
});
