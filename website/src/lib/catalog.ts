import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export { formatDuration } from './format';

import { joinRoutePois, type PoiRecord, type PoiLink, type RoutePoi } from './route-pois';
import { squareFileName, squaresForBoundingBox, type PoiGridDefinition } from './poi-grid';

export type { RoutePoi } from './route-pois';
export { getTrainStations } from './route-pois';

import type { OpenRandoRouteCatalog, Route } from './generated/catalog';

export type { PoiCounts, Route } from './generated/catalog';

export interface RouteElevationProfile {
  distances_km: number[];
  elevations_m: number[];
  times_min: number[];
  station_positions_km?: number[];
  /** Distances where the trail breaks between two mapped segments. */
  segment_boundaries_km?: number[];
}

export function getAllRoutes(): Route[] {
  const catalogPath = join(process.cwd(), 'public', 'data', 'catalog.json');
  const raw = readFileSync(catalogPath, 'utf-8');
  const catalog: OpenRandoRouteCatalog = JSON.parse(raw);
  return catalog.routes;
}

export function getRouteBySlug(slug: string): Route | undefined {
  return getAllRoutes().find((route) => route.slug === slug);
}

const DATA_DIRECTORY = join(process.cwd(), 'public', 'data');

// Must match CANDIDATE_BUFFER_DEGREES in pipeline/src/open_rando/processors/link.py:
// the squares read here are the squares the `link` stage linked from.
const LINK_MARGIN_DEGREES = 0.07;

interface PoiIndex {
  grid: PoiGridDefinition;
}

const poiSquareCache = new Map<string, PoiRecord[]>();

function readDataFile<T>(relativePath: string): T {
  return JSON.parse(readFileSync(join(DATA_DIRECTORY, relativePath), 'utf-8')) as T;
}

function readPoiSquare(squareName: string): PoiRecord[] {
  let pois = poiSquareCache.get(squareName);
  if (pois === undefined) {
    // A square without a file is built but empty (the index lists empty squares too).
    const squarePath = `pois/${squareName}`;
    pois = existsSync(join(DATA_DIRECTORY, squarePath))
      ? readDataFile<{ pois: PoiRecord[] }>(squarePath).pois
      : [];
    poiSquareCache.set(squareName, pois);
  }
  return pois;
}

/** POIs of one route: its links joined with the POI grid, at build time. */
export function getRoutePois(route: Route): RoutePoi[] {
  const { links } = readDataFile<{ links: PoiLink[] }>(`links/${route.id}.json`);
  const { grid } = readDataFile<PoiIndex>('pois/index.json');

  const poisById = new Map<string, PoiRecord>();
  for (const square of squaresForBoundingBox(grid, route.bbox, LINK_MARGIN_DEGREES)) {
    for (const poi of readPoiSquare(squareFileName(square))) {
      poisById.set(poi.id, poi);
    }
  }
  return joinRoutePois(links, poisById);
}
