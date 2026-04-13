import { readFileSync } from 'node:fs';
import { join } from 'node:path';

export { formatDuration } from './format';

export interface POI {
  name: string;
  lat: number;
  lon: number;
  poi_type: 'hotel' | 'camping' | 'train_station' | 'bus_stop';
  transit_lines?: string[];
  distance_km?: number;
}

export interface Route {
  id: string;
  slug: string;
  path_ref: string;
  path_name: string;
  description: string;
  osm_relation_id: number;
  pois: POI[];
  distance_km: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  max_elevation_m: number;
  min_elevation_m: number;
  bbox: [number, number, number, number];
  region: string;
  departement: string;
  difficulty: 'easy' | 'moderate' | 'difficult' | 'very_difficult' | 'unknown';
  is_circular_trail: boolean;
  terrain: string[];
  geojson_path: string;
  gpx_path: string;
  last_updated: string;
}

export interface RouteElevationProfile {
  distances_km: number[];
  elevations_m: number[];
  times_min: number[];
}

interface Catalog {
  generated_at: string;
  source: string;
  license: string;
  routes: Route[];
}

export function getAllRoutes(): Route[] {
  const catalogPath = join(process.cwd(), 'public', 'data', 'catalog.json');
  const raw = readFileSync(catalogPath, 'utf-8');
  const catalog: Catalog = JSON.parse(raw);
  return catalog.routes;
}

export function getRouteBySlug(slug: string): Route | undefined {
  return getAllRoutes().find((route) => route.slug === slug);
}

export function getTrainStations(route: Route): POI[] {
  return (route.pois ?? []).filter((poi) => poi.poi_type === 'train_station');
}
