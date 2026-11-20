// Generated from pipeline/src/open_rando/data/poi-square.schema.json by
// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun
// `bun run generate:types`.

/**
 * Contract for data/pois/<col>_<row>.json: every POI inside one square of the fixed grid, independent of any track.
 */
export interface OpenRandoPOIGridSquare {
  square: SquareCoordinates;
  pois: Poi[];
}
export interface SquareCoordinates {
  col: number;
  row: number;
}
export interface Poi {
  /**
   * Stable OSM identity.
   */
  id: string;
  kind: 'train_station' | 'bus_stop' | 'hotel' | 'camping' | 'shop' | 'eatery';
  name: string;
  lat: number;
  lon: number;
  url?: string | null;
  transit_lines?: string[];
  rail_service?: RailService | null;
  /**
   * Shops and eateries: the OSM kind, for example bakery or cafe.
   */
  category?: string | null;
  /**
   * Raw OSM opening_hours value, shops and eateries only.
   */
  opening_hours?: string | null;
  phone?: string | null;
}
/**
 * Departures read from the GTFS feeds serving this station, per kind of day. A null window means the feeds report no departure on that kind of day.
 */
export interface RailService {
  weekday: ServiceWindow | null;
  saturday: ServiceWindow | null;
  sunday: ServiceWindow | null;
}
export interface ServiceWindow {
  first_departure_minutes: number;
  last_departure_minutes: number;
  departure_count: number;
  /**
   * Calendar date the departures were counted on.
   */
  sample_date?: string | null;
}
