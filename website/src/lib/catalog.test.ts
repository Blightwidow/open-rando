import { describe, expect, test } from 'bun:test';
import { getStationTimetableUrl } from './catalog';
import { formatDuration } from './format';
import type { StationInfo } from './catalog';

function makeStation(name: string): StationInfo {
  return {
    name,
    code: 'TEST',
    lat: 0,
    lon: 0,
    distance_to_trail_m: 0,
    transit_lines: [],
    accommodation: { has_hotel: false, has_camping: false },
  };
}

describe('formatDuration', () => {
  test('hours and minutes', () => {
    expect(formatDuration(90)).toBe('1h30min');
  });

  test('hours only', () => {
    expect(formatDuration(120)).toBe('2h');
  });

  test('exact one hour', () => {
    expect(formatDuration(60)).toBe('1h');
  });

  test('minutes only', () => {
    expect(formatDuration(45)).toBe('45min');
  });

  test('zero minutes', () => {
    expect(formatDuration(0)).toBe('0min');
  });

  test('large duration', () => {
    expect(formatDuration(605)).toBe('10h5min');
  });
});

describe('getStationTimetableUrl', () => {
  test('simple name', () => {
    expect(getStationTimetableUrl(makeStation('Paris'))).toBe(
      'https://www.garesetconnexions.sncf/fr/gares-services/paris'
    );
  });

  test('accented characters stripped', () => {
    expect(getStationTimetableUrl(makeStation('Béziers'))).toBe(
      'https://www.garesetconnexions.sncf/fr/gares-services/beziers'
    );
  });

  test('spaces become hyphens', () => {
    expect(getStationTimetableUrl(makeStation('Aix en Provence'))).toBe(
      'https://www.garesetconnexions.sncf/fr/gares-services/aix-en-provence'
    );
  });

  test('hyphens preserved', () => {
    expect(getStationTimetableUrl(makeStation('Saint-Étienne'))).toBe(
      'https://www.garesetconnexions.sncf/fr/gares-services/saint-etienne'
    );
  });

  test('special characters removed', () => {
    expect(getStationTimetableUrl(makeStation("L'Isle-sur-la-Sorgue"))).toBe(
      'https://www.garesetconnexions.sncf/fr/gares-services/lisle-sur-la-sorgue'
    );
  });

  test('multiple spaces collapse to single hyphen', () => {
    expect(getStationTimetableUrl(makeStation('Gare  de   Lyon'))).toBe(
      'https://www.garesetconnexions.sncf/fr/gares-services/gare-de-lyon'
    );
  });
});
