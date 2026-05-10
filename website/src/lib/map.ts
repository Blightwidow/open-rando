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
  for (const source of Object.values(style.sources ?? {})) {
    const s = source as { url?: string };
    if (s.url?.startsWith('pmtiles:///data/')) {
      s.url = `pmtiles://${PMTILES_BASE}/${s.url.slice('pmtiles:///data/'.length)}`;
    }
  }
  return style;
}

const WORLD_SOURCE = 'protomaps_world';

function stripToWorldOnly(style: maplibregl.StyleSpecification): maplibregl.StyleSpecification {
  const sources: Record<string, unknown> = {};
  if (style.sources?.[WORLD_SOURCE]) {
    sources[WORLD_SOURCE] = style.sources[WORLD_SOURCE];
  }
  const layers = (style.layers ?? [])
    .filter((layer) => {
      if (layer.type === 'background') return true;
      const source = (layer as { source?: string }).source;
      return source === WORLD_SOURCE;
    })
    .map((layer) => {
      const next = { ...layer } as { maxzoom?: number };
      delete next.maxzoom;
      return next as maplibregl.LayerSpecification;
    });
  return { ...style, sources: sources as maplibregl.StyleSpecification['sources'], layers };
}

function getStyle(isDark: boolean, lowRes: boolean): maplibregl.StyleSpecification {
  const source = (isDark ? styleDarkJson : styleLightJson) as maplibregl.StyleSpecification;
  const cloned = structuredClone(source);
  const shaped = lowRes ? stripToWorldOnly(cloned) : cloned;
  return rewritePmtilesUrls(shaped);
}

interface MapWithLowRes extends maplibregl.Map {
  __lowRes?: boolean;
}

export function createMap(
  container: HTMLElement,
  options?: { center?: [number, number]; zoom?: number; lowRes?: boolean }
): maplibregl.Map {
  ensurePmtilesProtocol();
  const isDark = document.documentElement.classList.contains('dark');
  const lowRes = options?.lowRes ?? false;
  const map = new maplibregl.Map({
    container,
    style: getStyle(isDark, lowRes),
    center: options?.center ?? [2.5, 46.5],
    zoom: options?.zoom ?? 6,
    attributionControl: {},
  });
  (map as MapWithLowRes).__lowRes = lowRes;
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }));
  return map;
}

export function switchTheme(map: maplibregl.Map) {
  const isDark = document.documentElement.classList.contains('dark');
  const lowRes = (map as MapWithLowRes).__lowRes ?? false;
  map.setStyle(getStyle(isDark, lowRes));
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
