import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import styleLightJson from './styles/style-light.json';
import styleDarkJson from './styles/style-dark.json';

let protocolRegistered = false;

function ensurePmtilesProtocol() {
  if (protocolRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  protocolRegistered = true;
}

export const POI_COLORS: Record<string, string> = {
  train_station: '#22c55e',
  bus_stop: '#3b82f6',
  hotel: '#a855f7',
  camping: '#f59e0b',
};

export const POI_RADII: Record<string, number> = {
  train_station: 7,
  bus_stop: 5,
  hotel: 5,
  camping: 5,
};

export const TRAIL_COLOR = '#E72323';

const PMTILES_BASE = import.meta.env.PUBLIC_PMTILES_BASE ?? '';

function rewritePmtilesUrls(style: maplibregl.StyleSpecification): maplibregl.StyleSpecification {
  if (!PMTILES_BASE) return style;
  const next = structuredClone(style);
  for (const source of Object.values(next.sources ?? {})) {
    const s = source as { url?: string };
    if (s.url?.startsWith('pmtiles:///data/')) {
      s.url = `pmtiles://${PMTILES_BASE}/${s.url.slice('pmtiles:///data/'.length)}`;
    }
  }
  return next;
}

function getStyle(isDark: boolean): maplibregl.StyleSpecification {
  const style = (isDark ? styleDarkJson : styleLightJson) as maplibregl.StyleSpecification;
  return rewritePmtilesUrls(style);
}

export function createMap(
  container: HTMLElement,
  options?: { center?: [number, number]; zoom?: number }
): maplibregl.Map {
  ensurePmtilesProtocol();
  const isDark = document.documentElement.classList.contains('dark');
  const map = new maplibregl.Map({
    container,
    style: getStyle(isDark),
    center: options?.center ?? [2.5, 46.5],
    zoom: options?.zoom ?? 6,
    attributionControl: {},
  });
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }));
  return map;
}

export function switchTheme(map: maplibregl.Map) {
  const isDark = document.documentElement.classList.contains('dark');
  map.setStyle(getStyle(isDark));
}

export function fitBoundsFromBbox(
  map: maplibregl.Map,
  bbox: [number, number, number, number],
  padding = 30
) {
  // bbox is [minLon, minLat, maxLon, maxLat] from catalog
  map.fitBounds(
    [
      [bbox[0], bbox[1]], // [west, south]
      [bbox[2], bbox[3]], // [east, north]
    ],
    { padding }
  );
}
