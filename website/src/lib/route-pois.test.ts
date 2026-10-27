import { describe, expect, test } from 'bun:test';
import { getTrainStations, joinRoutePois, type PoiLink, type PoiRecord } from './route-pois';

const STATION: PoiRecord = {
  id: 'node/1',
  kind: 'train_station',
  name: 'Melun',
  lat: 48.53,
  lon: 2.65,
  url: 'https://example.invalid/melun',
  rail_service: null,
};
const HOTEL: PoiRecord = { id: 'way/2', kind: 'hotel', name: 'Hotel', lat: 48.5, lon: 2.6, url: null };

const STATION_LINK: PoiLink = {
  poi_id: 'node/1',
  kind: 'train_station',
  distance_to_trail_m: 220,
  distance_km: 12.5,
  junction: [2.65, 48.5],
};
const HOTEL_LINK: PoiLink = {
  poi_id: 'way/2',
  kind: 'hotel',
  distance_to_trail_m: 900,
  distance_km: null,
  junction: null,
};

const POIS = new Map([STATION, HOTEL].map((poi) => [poi.id, poi]));

describe('joinRoutePois', () => {
  test('keeps the link order', () => {
    const joined = joinRoutePois([HOTEL_LINK, STATION_LINK], POIS);
    expect(joined.map((poi) => poi.id)).toEqual(['way/2', 'node/1']);
  });

  test('station gets its position along the trail', () => {
    const [station] = joinRoutePois([STATION_LINK], POIS);
    expect(station.distance_km).toBe(12.5);
  });

  test('poi_type is the grid kind', () => {
    const [station] = joinRoutePois([STATION_LINK], POIS);
    expect(station.poi_type).toBe('train_station');
  });

  test('a null link position becomes undefined', () => {
    const [hotel] = joinRoutePois([HOTEL_LINK], POIS);
    expect(hotel.distance_km).toBeUndefined();
  });

  test('a null url becomes undefined', () => {
    const [hotel] = joinRoutePois([HOTEL_LINK], POIS);
    expect(hotel.url).toBeUndefined();
  });

  test('a null junction becomes undefined', () => {
    const [hotel] = joinRoutePois([HOTEL_LINK], POIS);
    expect(hotel.junction).toBeUndefined();
  });

  test('fails loudly when a linked POI is missing from the grid', () => {
    const orphan: PoiLink = { ...HOTEL_LINK, poi_id: 'node/404' };
    expect(() => joinRoutePois([STATION_LINK, orphan], POIS)).toThrow('node/404');
  });
});

describe('getTrainStations', () => {
  test('keeps train stations only', () => {
    const joined = joinRoutePois([STATION_LINK, HOTEL_LINK], POIS);
    expect(getTrainStations(joined).map((poi) => poi.id)).toEqual(['node/1']);
  });
});
