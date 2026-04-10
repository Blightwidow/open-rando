import { describe, expect, test } from 'bun:test';
import { normalize, extractStations, buildHikeStationIndex, findSuggestions } from './suggest';
import type { HikeIndexEntry } from './suggest';
import type { Hike, StationInfo, HikeStep } from './catalog';

function makeStation(name: string, code: string): StationInfo {
  return {
    name,
    code,
    lat: 0,
    lon: 0,
    distance_to_trail_m: 0,
    transit_lines: [],
    accommodation: { has_hotel: false, has_camping: false },
  };
}

function makeStep(startName: string, startCode: string, endName: string, endCode: string, duration: number, distance: number): HikeStep {
  return {
    start_station: makeStation(startName, startCode),
    end_station: makeStation(endName, endCode),
    estimated_duration_min: duration,
    distance_km: distance,
    elevation_gain_m: 0,
    elevation_loss_m: 0,
  };
}

function makeHike(id: string, steps: HikeStep[]): Hike {
  return {
    id,
    slug: id,
    path_ref: 'GR 1',
    path_name: 'Test',
    osm_relation_id: 0,
    start_station: steps[0].start_station,
    end_station: steps[steps.length - 1].end_station,
    steps,
    step_count: steps.length,
    distance_km: steps.reduce((sum, step) => sum + step.distance_km, 0),
    estimated_duration_min: steps.reduce((sum, step) => sum + step.estimated_duration_min, 0),
    elevation_gain_m: 0,
    elevation_loss_m: 0,
    max_elevation_m: 0,
    min_elevation_m: 0,
    difficulty: 'easy',
    bbox: [0, 0, 0, 0],
    region: 'Test',
    departement: 'Test',
    gpx_path: 'test.gpx',
    geojson_path: 'test.geojson',
    is_reversible: false,
    route_type: 'gr',
    is_grp: false,
    is_circular_trail: false,
    is_round_trip: false,
    terrain: [],
    last_updated: '2024-01-01',
  };
}

// ── normalize ──────────────────────────────────────────────────────────────

describe('normalize', () => {
  test('strips accents', () => {
    expect(normalize('Château')).toBe('chateau');
  });

  test('lowercases', () => {
    expect(normalize('PARIS')).toBe('paris');
  });

  test('no-op for plain ASCII', () => {
    expect(normalize('paris')).toBe('paris');
  });

  test('handles multiple accents', () => {
    expect(normalize('Béziers-lès-Bains')).toBe('beziers-les-bains');
  });
});

// ── extractStations ────────────────────────────────────────────────────────

describe('extractStations', () => {
  test('deduplicates stations by code', () => {
    const hikes = [
      makeHike('h1', [
        makeStep('Alpha', 'A', 'Bravo', 'B', 60, 10),
        makeStep('Bravo', 'B', 'Charlie', 'C', 60, 10),
      ]),
    ];
    const stations = extractStations(hikes);
    expect(stations.length).toBe(3);
    const codes = stations.map((station) => station.code);
    expect(codes).toContain('A');
    expect(codes).toContain('B');
    expect(codes).toContain('C');
  });

  test('sorts alphabetically by name', () => {
    const hikes = [
      makeHike('h1', [
        makeStep('Zèbre', 'Z', 'Alpha', 'A', 60, 10),
      ]),
    ];
    const stations = extractStations(hikes);
    expect(stations[0].name).toBe('Alpha');
    expect(stations[1].name).toBe('Zèbre');
  });

  test('deduplicates across multiple hikes', () => {
    const hikes = [
      makeHike('h1', [makeStep('Alpha', 'A', 'Bravo', 'B', 60, 10)]),
      makeHike('h2', [makeStep('Bravo', 'B', 'Charlie', 'C', 60, 10)]),
    ];
    const stations = extractStations(hikes);
    expect(stations.length).toBe(3);
  });
});

// ── buildHikeStationIndex ──────────────────────────────────────────────────

describe('buildHikeStationIndex', () => {
  test('maps station codes to positions', () => {
    const hikes = [
      makeHike('h1', [
        makeStep('Alpha', 'A', 'Bravo', 'B', 120, 15),
        makeStep('Bravo', 'B', 'Charlie', 'C', 180, 12),
      ]),
    ];
    const index = buildHikeStationIndex(hikes);
    expect(index.length).toBe(1);
    expect(index[0].stationPositions['A']).toEqual([0]);
    expect(index[0].stationPositions['B']).toEqual([1]);
    expect(index[0].stationPositions['C']).toEqual([2]);
  });

  test('preserves step data', () => {
    const hikes = [
      makeHike('h1', [makeStep('A', 'A', 'B', 'B', 120, 15)]),
    ];
    const index = buildHikeStationIndex(hikes);
    expect(index[0].steps[0].duration).toBe(120);
    expect(index[0].steps[0].distance).toBe(15);
  });

  test('station appearing at multiple positions', () => {
    const hikes = [
      makeHike('h1', [
        makeStep('Alpha', 'A', 'Bravo', 'B', 60, 10),
        makeStep('Bravo', 'B', 'Alpha', 'A', 60, 10),
      ]),
    ];
    const index = buildHikeStationIndex(hikes);
    // A at position 0 (start of step 0) and position 2 (end of step 1)
    expect(index[0].stationPositions['A']).toEqual([0, 2]);
  });
});

// ── findSuggestions ────────────────────────────────────────────────────────

describe('findSuggestions', () => {
  const threeStepIndex: HikeIndexEntry[] = [{
    hikeId: 'h1',
    stepCount: 3,
    steps: [
      { duration: 120, distance: 10, startCode: 'A', endCode: 'B' },
      { duration: 180, distance: 15, startCode: 'B', endCode: 'C' },
      { duration: 90, distance: 8, startCode: 'C', endCode: 'D' },
    ],
    stationPositions: { A: [0], B: [1], C: [2], D: [3] },
  }];

  test('forward suggestions from start station', () => {
    const suggestions = findSuggestions(threeStepIndex, 'A', 500);
    const forward = suggestions.filter((suggestion) => suggestion.startsHere);
    expect(forward.length).toBeGreaterThanOrEqual(1);
    expect(forward[0].fromStep).toBe(0);
    expect(forward[0].startsHere).toBe(true);
  });

  test('backward suggestions to end station', () => {
    const suggestions = findSuggestions(threeStepIndex, 'D', 500);
    const backward = suggestions.filter((suggestion) => !suggestion.startsHere);
    expect(backward.length).toBeGreaterThanOrEqual(1);
    expect(backward[0].toStep).toBe(3);
    expect(backward[0].startsHere).toBe(false);
  });

  test('respects time budget', () => {
    // Budget of 100 minutes: only step A->B (120min) exceeds it, so no forward results
    const suggestions = findSuggestions(threeStepIndex, 'A', 100);
    expect(suggestions.length).toBe(0);
  });

  test('time budget includes partial forward expansion', () => {
    // Budget of 150: can do step 0 (120min) but not step 0+1 (300min)
    const suggestions = findSuggestions(threeStepIndex, 'A', 150);
    expect(suggestions.length).toBe(1);
    expect(suggestions[0].toStep).toBe(1); // only first step
    expect(suggestions[0].totalDuration).toBe(120);
  });

  test('empty results for unknown station', () => {
    const suggestions = findSuggestions(threeStepIndex, 'UNKNOWN', 500);
    expect(suggestions.length).toBe(0);
  });

  test('departures sorted before arrivals', () => {
    // Station B is in the middle: has both forward and backward
    const suggestions = findSuggestions(threeStepIndex, 'B', 500);
    const startsHereValues = suggestions.map((suggestion) => suggestion.startsHere);
    const firstArrivalIndex = startsHereValues.indexOf(false);
    if (firstArrivalIndex > 0) {
      // All items before first arrival should be departures
      for (let index = 0; index < firstArrivalIndex; index++) {
        expect(startsHereValues[index]).toBe(true);
      }
    }
  });

  test('deduplicates to best per hike', () => {
    const suggestions = findSuggestions(threeStepIndex, 'A', 500);
    const hikeIds = suggestions.map((suggestion) => suggestion.hikeId);
    const uniqueIds = new Set(hikeIds);
    expect(hikeIds.length).toBe(uniqueIds.size);
  });

  test('multi-hike results', () => {
    const multiIndex: HikeIndexEntry[] = [
      {
        hikeId: 'h1',
        stepCount: 1,
        steps: [{ duration: 120, distance: 10, startCode: 'A', endCode: 'B' }],
        stationPositions: { A: [0], B: [1] },
      },
      {
        hikeId: 'h2',
        stepCount: 1,
        steps: [{ duration: 90, distance: 8, startCode: 'A', endCode: 'C' }],
        stationPositions: { A: [0], C: [1] },
      },
    ];
    const suggestions = findSuggestions(multiIndex, 'A', 500);
    expect(suggestions.length).toBe(2);
    const hikeIds = suggestions.map((suggestion) => suggestion.hikeId);
    expect(hikeIds).toContain('h1');
    expect(hikeIds).toContain('h2');
  });

  test('higher utilization ranked first', () => {
    const multiIndex: HikeIndexEntry[] = [
      {
        hikeId: 'short',
        stepCount: 1,
        steps: [{ duration: 60, distance: 5, startCode: 'A', endCode: 'B' }],
        stationPositions: { A: [0], B: [1] },
      },
      {
        hikeId: 'long',
        stepCount: 1,
        steps: [{ duration: 200, distance: 18, startCode: 'A', endCode: 'C' }],
        stationPositions: { A: [0], C: [1] },
      },
    ];
    const suggestions = findSuggestions(multiIndex, 'A', 250);
    expect(suggestions[0].hikeId).toBe('long'); // 200/250 > 60/250
  });
});
