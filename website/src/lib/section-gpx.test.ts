import { describe, expect, test } from 'bun:test';
import { buildSectionGpx, sectionGpxFileName } from './section-gpx';

const baseInput = {
  routeRef: 'GR 13',
  fromName: 'Gare A',
  toName: 'Gare B',
  sectionCoordinates: [[45.1, 5.2], [45.2, 5.3]] as [number, number][],
  firstIndex: 0,
  cumulativeDistances: [0, 10],
  endKm: 10,
};

describe('buildSectionGpx', () => {
  test('names the track after the route and both stations', () => {
    const gpx = buildSectionGpx({ ...baseInput, profile: null });

    expect(gpx).toContain('<name>GR 13 — Gare A → Gare B</name>');
  });

  test('writes one track point per section coordinate', () => {
    const gpx = buildSectionGpx({ ...baseInput, profile: null });

    expect(gpx.match(/<trkpt /g)?.length).toBe(2);
  });

  test('writes coordinates with six decimals', () => {
    const gpx = buildSectionGpx({ ...baseInput, profile: null });

    expect(gpx).toContain('<trkpt lat="45.100000" lon="5.200000"></trkpt>');
  });

  test('looks elevation up from the profile at each point distance', () => {
    const gpx = buildSectionGpx({
      ...baseInput,
      profile: { distances_km: [0, 5, 10], elevations_m: [100, 150, 200] },
    });

    expect(gpx).toContain('lon="5.200000"><ele>100.0</ele>');
  });

  test('omits elevation without a profile', () => {
    const gpx = buildSectionGpx({ ...baseInput, profile: null });

    expect(gpx).not.toContain('<ele>');
  });
});

describe('sectionGpxFileName', () => {
  test('joins route and stations with underscores and dashes inside names', () => {
    expect(sectionGpxFileName('GR 13', 'Gare de Lyon', 'Fontainebleau Avon')).toBe(
      'GR-13_Gare-de-Lyon_Fontainebleau-Avon.gpx',
    );
  });
});
