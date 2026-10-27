// Joins a track's links (links/<id>.json) with the POIs they point at (pois/<col>_<row>.json).
// The pipeline stores them apart so one POI can serve many tracks and custom GPX imports.

import type { RailService } from './rail';

export type PoiKind = 'hotel' | 'camping' | 'train_station' | 'bus_stop';

/** A POI as stored in the grid, independent of any track. */
export interface PoiRecord {
  id: string;
  kind: PoiKind;
  name: string;
  lat: number;
  lon: number;
  url?: string | null;
  transit_lines?: string[];
  rail_service?: RailService | null;
}

/** How a POI relates to one track. */
export interface PoiLink {
  poi_id: string;
  kind: PoiKind;
  distance_to_trail_m: number;
  /** Position along the trail from its start. Train stations only. */
  distance_km: number | null;
  /** [lon, lat] where the walk from the POI meets the trail. */
  junction: [number, number] | null;
}

/** A POI of one track: the grid record plus its link. */
export interface RoutePoi {
  id: string;
  name: string;
  lat: number;
  lon: number;
  poi_type: PoiKind;
  url?: string;
  transit_lines?: string[];
  /** Position along the trail (train stations only). */
  distance_km?: number;
  distance_to_trail_m: number;
  junction?: [number, number];
  /** Train stations only: departures read from GTFS feeds. */
  rail_service?: RailService | null;
}

export function joinRoutePois(links: PoiLink[], poisById: Map<string, PoiRecord>): RoutePoi[] {
  const missingIds = links.filter((link) => !poisById.has(link.poi_id)).map((link) => link.poi_id);
  if (missingIds.length > 0) {
    // The grid was rebuilt after the links: shipping a route with holes would hide it.
    throw new Error(
      `${missingIds.length} linked POI(s) missing from the POI grid (first: ${missingIds[0]}). Rerun \`link\`.`
    );
  }

  return links.map((link) => {
    const poi = poisById.get(link.poi_id)!;
    return {
      id: poi.id,
      name: poi.name,
      lat: poi.lat,
      lon: poi.lon,
      poi_type: poi.kind,
      url: poi.url ?? undefined,
      transit_lines: poi.transit_lines,
      distance_km: link.distance_km ?? undefined,
      distance_to_trail_m: link.distance_to_trail_m,
      junction: link.junction ?? undefined,
      rail_service: poi.rail_service,
    };
  });
}

export function getTrainStations(pois: RoutePoi[]): RoutePoi[] {
  return pois.filter((poi) => poi.poi_type === 'train_station');
}
