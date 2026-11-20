// Generated from pipeline/src/open_rando/data/links.schema.json by
// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun
// `bun run generate:types`.

/**
 * Contract for data/links/<route id>.json: which POIs belong to a track, and where.
 */
export interface OpenRandoTrackLinks {
  route_id: string;
  counts: PoiCounts;
  links: PoiLink[];
}
/**
 * How many linked POIs of each kind the track has. The POIs themselves live in the POI grid; links/<id>.json says which ones belong to this track.
 */
export interface PoiCounts {
  train_station: number;
  bus_stop: number;
  hotel: number;
  camping: number;
  shop: number;
  eatery: number;
  train_station_with_rail_service: number;
}
export interface PoiLink {
  poi_id: string;
  kind: 'train_station' | 'bus_stop' | 'hotel' | 'camping' | 'shop' | 'eatery';
  distance_to_trail_m: number;
  /**
   * Position along the trail from its start. Train stations only.
   */
  distance_km?: number | null;
  /**
   * [lon, lat] where the walk from the POI meets the trail.
   */
  junction?: [number, number] | null;
}
