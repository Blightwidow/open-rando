// Generated from pipeline/src/open_rando/data/catalog.schema.json by
// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun
// `bun run generate:types`.

/**
 * Contract for data/catalog.json, consumed by the website and the mobile client: curated tracks only. POIs live in pois/ and are joined through links/<id>.json. Fields are only ever added as optional; removing or retyping one is a breaking change.
 */
export interface OpenRandoRouteCatalog {
  generated_at: string;
  source: string;
  license: string;
  routes: Route[];
}
export interface Route {
  id: string;
  slug: string;
  path_ref: string;
  path_name: string;
  description: string;
  osm_relation_id: number;
  distance_km: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  max_elevation_m: number;
  min_elevation_m: number;
  /**
   * @minItems 4
   * @maxItems 4
   */
  bbox: [number, number, number, number];
  region: string;
  departement: string;
  difficulty: 'easy' | 'moderate' | 'difficult' | 'very_difficult' | 'unknown';
  is_circular_trail: boolean;
  terrain: string[];
  geojson_path: string;
  gpx_path: string;
  last_updated: string;
  image_path?: string | null;
  landmarks?: Landmark[];
  /**
   * Mapped segments the trail is made of; more than one means it has gaps.
   */
  trail_segment_count?: number;
  /**
   * Straight-line distance of the gaps between segments. Not included in distance_km.
   */
  trail_gap_km?: number;
  elevation_path: string;
  poi_counts: PoiCounts;
}
export interface Landmark {
  name: string;
  kind: string;
  lat: number;
  lon: number;
  elevation_m?: number | null;
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
