import { readFileSync } from 'node:fs';
import { join } from 'node:path';

export interface StationInfo {
  name: string;
  code: string;
  lat: number;
  lon: number;
  distance_to_trail_m: number;
  transit_lines: string[];
}

export interface HikeStep {
  start_station: StationInfo;
  end_station: StationInfo;
  distance_km: number;
  estimated_duration_min: number;
}

export interface Hike {
  id: string;
  slug: string;
  path_ref: string;
  path_name: string;
  osm_relation_id: number;
  start_station: StationInfo;
  end_station: StationInfo;
  steps: HikeStep[];
  step_count: number;
  distance_km: number;
  estimated_duration_min: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  max_elevation_m: number;
  min_elevation_m: number;
  difficulty: string;
  bbox: [number, number, number, number];
  region: string;
  departement: string;
  gpx_path: string;
  geojson_path: string;
  is_reversible: boolean;
  last_updated: string;
}

interface Catalog {
  generated_at: string;
  source: string;
  license: string;
  hikes: Hike[];
}

export function getAllHikes(): Hike[] {
  const catalogPath = join(process.cwd(), 'public', 'data', 'catalog.json');
  const raw = readFileSync(catalogPath, 'utf-8');
  const catalog: Catalog = JSON.parse(raw);
  return catalog.hikes;
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hours > 0 && mins > 0) return `${hours}h${mins}min`;
  if (hours > 0) return `${hours}h`;
  return `${mins}min`;
}
