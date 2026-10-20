import { describe, expect, test } from 'bun:test';
import { buildRailServiceRows, formatDepartureTime, type RailService, type RailServiceLabels } from './rail';

const labels: RailServiceLabels = {
  weekday: 'Semaine',
  saturday: 'Samedi',
  sunday: 'Dimanche',
  noService: 'Pas de service',
  departures: '{count} départs',
};

describe('formatDepartureTime', () => {
  test('formats a morning departure', () => {
    expect(formatDepartureTime(342)).toBe('05:42');
  });

  test('pads single-digit minutes', () => {
    expect(formatDepartureTime(9 * 60 + 5)).toBe('09:05');
  });

  test('wraps a departure past midnight', () => {
    expect(formatDepartureTime(25 * 60 + 10)).toBe('01:10');
  });

  test('formats midnight itself', () => {
    expect(formatDepartureTime(24 * 60)).toBe('00:00');
  });
});

describe('buildRailServiceRows', () => {
  const railService: RailService = {
    weekday: { first_departure_minutes: 342, last_departure_minutes: 1335, departure_count: 48 },
    saturday: { first_departure_minutes: 400, last_departure_minutes: 1450, departure_count: 30 },
    sunday: null,
  };

  test('returns one row per kind of day', () => {
    const rows = buildRailServiceRows(railService, labels);
    expect(rows.map((row) => row.dayType)).toEqual(['weekday', 'saturday', 'sunday']);
  });

  test('shows first train, last train and departure count', () => {
    const [weekdayRow] = buildRailServiceRows(railService, labels);
    expect(weekdayRow.text).toBe('05:42 → 22:15 · 48 départs');
  });

  test('wraps an after-midnight last train', () => {
    const rows = buildRailServiceRows(railService, labels);
    expect(rows[1].text).toBe('06:40 → 00:10 · 30 départs');
  });

  test('marks a day without service', () => {
    const rows = buildRailServiceRows(railService, labels);
    expect(rows[2].text).toBe('Pas de service');
    expect(rows[2].window).toBeNull();
  });

  test('returns nothing for a station without rail service data', () => {
    expect(buildRailServiceRows(null, labels)).toEqual([]);
  });
});
