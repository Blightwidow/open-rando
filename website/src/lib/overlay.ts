import type maplibregl from 'maplibre-gl';
import {
  overlayIconDataUrl,
  overlayIconImageId,
  registerOverlayImages,
  type OverlayIconColors,
  type OverlayIconName,
} from './overlay-icons';

/**
 * Hiking overlay: water, shelters, peaks, power lines and rivers read from `overlay.pmtiles`
 * (built by `tiles/Makefile.overlay`). Drawn on the map, never clicked: no popups, no cursor.
 * Layers are grouped so one toggle and one legend swatch stand for each kind of feature.
 */

export const OVERLAY_SOURCE_ID = 'overlay';
export const OVERLAY_PMTILES_PATH = 'overlay.pmtiles';

/** Source layers `overlay.pmtiles` carries. Streams are left out on purpose (96 MB of tiles). */
export const OVERLAY_SOURCE_LAYERS = [
  'river',
  'peak',
  'hut',
  'power_line',
  'water',
  'spring',
  'shelter',
  'viewpoint',
  'guidepost',
  'power_tower',
  'pass',
  'waterfall',
  'cave',
  'ford',
  'toilets',
  'church',
  'cemetery',
  'aerialway',
  'bridge',
  'shop',
  'eatery',
] as const;

export type OverlayGroupKey =
  | 'river'
  | 'water'
  | 'shelter'
  | 'peak'
  | 'viewpoint'
  | 'nature'
  | 'crossing'
  | 'landmark'
  | 'toilets'
  | 'shop'
  | 'eatery'
  | 'aerialway'
  | 'guidepost'
  | 'power';

export interface OverlayGroup {
  key: OverlayGroupKey;
  /** Translation key of the toggle and legend label. */
  labelKey: string;
  /** Legend swatch: a stroke for lines, an icon for point features, a dot for the rest. */
  swatch: 'dot' | 'line' | 'icon';
  /** The icon the legend shows when `swatch` is `icon`. */
  icon?: OverlayIconName;
  color: string;
  /** Guideposts and power lines are dense, so they start hidden. */
  defaultVisible: boolean;
  layers: maplibregl.LayerSpecification[];
}

interface Palette {
  river: string;
  water: string;
  shelter: string;
  peak: string;
  viewpoint: string;
  guidepost: string;
  power: string;
  waterfall: string;
  cave: string;
  church: string;
  cemetery: string;
  toilets: string;
  shop: string;
  eatery: string;
  aerialway: string;
  bridgeDeck: string;
  bridgeCasing: string;
  halo: string;
  text: string;
  dotOutline: string;
}

const LIGHT: Palette = {
  river: '#2563eb',
  water: '#0284c7',
  shelter: '#b45309',
  peak: '#57534e',
  viewpoint: '#db2777',
  guidepost: '#0f766e',
  power: '#78716c',
  waterfall: '#0891b2',
  cave: '#7c2d12',
  church: '#1c1917',
  cemetery: '#44403c',
  toilets: '#0d9488',
  shop: '#15803d',
  eatery: '#ca8a04',
  aerialway: '#1c1917',
  bridgeDeck: '#fafaf9',
  bridgeCasing: '#44403c',
  halo: '#ffffff',
  text: '#44403c',
  dotOutline: '#ffffff',
};

const DARK: Palette = {
  river: '#60a5fa',
  water: '#38bdf8',
  shelter: '#f59e0b',
  peak: '#d6d3d1',
  viewpoint: '#f472b6',
  guidepost: '#2dd4bf',
  power: '#a8a29e',
  waterfall: '#22d3ee',
  cave: '#fb923c',
  church: '#fafaf9',
  cemetery: '#d6d3d1',
  toilets: '#2dd4bf',
  shop: '#4ade80',
  eatery: '#fde047',
  aerialway: '#f5f5f4',
  bridgeDeck: '#292524',
  bridgeCasing: '#e7e5e4',
  halo: '#1c1917',
  text: '#e7e5e4',
  dotOutline: '#1c1917',
};

const FONT = ['Noto Sans Regular'];

/** "Name\n1234 m" when the elevation is known, the name alone otherwise. */
const ELEVATION_LABEL: maplibregl.ExpressionSpecification = [
  'case',
  ['has', 'ele'],
  ['concat', ['get', 'name'], '\n', ['to-string', ['get', 'ele']], ' m'],
  ['get', 'name'],
];

function dot(
  id: string,
  sourceLayer: string,
  color: string,
  outline: string,
  radius: [number, number],
  options: { hollow?: boolean; minzoom?: number; named?: boolean } = {},
): maplibregl.LayerSpecification {
  return {
    id,
    type: 'circle',
    source: OVERLAY_SOURCE_ID,
    'source-layer': sourceLayer,
    ...(options.minzoom === undefined ? {} : { minzoom: options.minzoom }),
    ...(options.named ? { filter: ['has', 'name'] as maplibregl.FilterSpecification } : {}),
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, radius[0], 15, radius[1]],
      'circle-color': options.hollow ? outline : color,
      'circle-stroke-color': options.hollow ? color : outline,
      'circle-stroke-width': options.hollow ? 1.5 : 1,
    },
  };
}

function label(
  id: string,
  sourceLayer: string,
  textField: maplibregl.ExpressionSpecification,
  palette: Palette,
  minzoom: number,
): maplibregl.LayerSpecification {
  return {
    id,
    type: 'symbol',
    source: OVERLAY_SOURCE_ID,
    'source-layer': sourceLayer,
    minzoom,
    filter: ['has', 'name'],
    layout: {
      'text-field': textField,
      'text-font': FONT,
      'text-size': 11,
      'text-anchor': 'top',
      'text-offset': [0, 0.6],
      'text-optional': true,
    },
    paint: {
      'text-color': palette.text,
      'text-halo-color': palette.halo,
      'text-halo-width': 1.5,
    },
  };
}

/** Zoom range an icon grows over: the first size at z9, the second at z15 (1 is 24 px). */
type IconSize = [number, number];

interface IconOptions {
  /** Draw only features that carry a name. */
  named?: boolean;
  /** Rare features overlap freely; dense ones thin out where they would collide. */
  allowOverlap?: boolean;
}

/** Symbol layer drawing an icon registered by `registerOverlayImages`. */
function icon(
  id: string,
  sourceLayer: string,
  name: OverlayIconName,
  size: IconSize,
  options: IconOptions = {},
): maplibregl.LayerSpecification {
  return {
    id,
    type: 'symbol',
    source: OVERLAY_SOURCE_ID,
    'source-layer': sourceLayer,
    ...(options.named ? { filter: ['has', 'name'] as maplibregl.FilterSpecification } : {}),
    layout: {
      'icon-image': overlayIconImageId(name),
      'icon-size': ['interpolate', ['linear'], ['zoom'], 9, size[0], 15, size[1]],
      'icon-allow-overlap': options.allowOverlap ?? false,
    },
  };
}

function iconColors(palette: Palette): OverlayIconColors {
  return {
    peak: palette.peak,
    pass: palette.peak,
    hut: palette.shelter,
    shelter: palette.shelter,
    water: palette.water,
    spring: palette.water,
    viewpoint: palette.viewpoint,
    waterfall: palette.waterfall,
    cave: palette.cave,
    ford: palette.water,
    toilets: palette.toilets,
    church: palette.church,
    cemetery: palette.cemetery,
    shop: palette.shop,
    eatery: palette.eatery,
    guidepost: palette.guidepost,
  };
}

/** Legend swatch for an icon group: the icon on a white halo, readable on a light or a dark panel. */
export function legendIconUrl(name: OverlayIconName): string {
  return overlayIconDataUrl(name, iconColors(LIGHT)[name], LIGHT.halo);
}

export function getOverlayGroups(isDark: boolean): OverlayGroup[] {
  const palette = isDark ? DARK : LIGHT;
  const outline = palette.dotOutline;

  return [
    {
      key: 'river',
      labelKey: 'overlay.river',
      swatch: 'line',
      color: palette.river,
      defaultVisible: true,
      layers: [
        {
          id: 'overlay-river-line',
          type: 'line',
          source: OVERLAY_SOURCE_ID,
          'source-layer': 'river',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': palette.river,
            'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.8, 14, 2.2],
            'line-opacity': 0.8,
          },
        },
        {
          // A `>` glyph laid along the line points the way the line was drawn, which for an OSM
          // waterway is downstream. The sprite's own arrow icon is grey and vanishes on the river.
          id: 'overlay-river-flow',
          type: 'symbol',
          source: OVERLAY_SOURCE_ID,
          'source-layer': 'river',
          minzoom: 11,
          layout: {
            'symbol-placement': 'line',
            'symbol-spacing': 110,
            'text-field': '>',
            'text-font': FONT,
            'text-size': 18,
            'text-keep-upright': false,
            'text-rotation-alignment': 'map',
            'text-allow-overlap': true,
          },
          paint: {
            'text-color': palette.river,
            'text-halo-color': palette.halo,
            'text-halo-width': 1.2,
          },
        },
      ],
    },
    {
      key: 'water',
      labelKey: 'overlay.water',
      swatch: 'icon',
      icon: 'water',
      color: palette.water,
      defaultVisible: true,
      layers: [
        icon('overlay-spring', 'spring', 'spring', [0.4, 0.7], { allowOverlap: true }),
        icon('overlay-water', 'water', 'water', [0.45, 0.8], { allowOverlap: true }),
      ],
    },
    {
      key: 'shelter',
      labelKey: 'overlay.shelter',
      swatch: 'icon',
      icon: 'hut',
      color: palette.shelter,
      defaultVisible: true,
      layers: [
        icon('overlay-hut', 'hut', 'hut', [0.55, 0.95], { allowOverlap: true }),
        icon('overlay-shelter', 'shelter', 'shelter', [0.45, 0.8], { allowOverlap: true }),
        label('overlay-hut-label', 'hut', ['get', 'name'], palette, 12),
      ],
    },
    {
      key: 'peak',
      labelKey: 'overlay.peak',
      swatch: 'icon',
      icon: 'peak',
      color: palette.peak,
      defaultVisible: true,
      layers: [
        icon('overlay-peak', 'peak', 'peak', [0.4, 0.8], { named: true }),
        label('overlay-peak-label', 'peak', ELEVATION_LABEL, palette, 11),
        icon('overlay-pass', 'pass', 'pass', [0.4, 0.75]),
        label('overlay-pass-label', 'pass', ELEVATION_LABEL, palette, 12),
      ],
    },
    {
      key: 'viewpoint',
      labelKey: 'overlay.viewpoint',
      swatch: 'icon',
      icon: 'viewpoint',
      color: palette.viewpoint,
      defaultVisible: true,
      layers: [icon('overlay-viewpoint', 'viewpoint', 'viewpoint', [0.5, 0.85], { allowOverlap: true })],
    },
    {
      key: 'nature',
      labelKey: 'overlay.nature',
      swatch: 'icon',
      icon: 'waterfall',
      color: palette.waterfall,
      defaultVisible: true,
      layers: [
        icon('overlay-waterfall', 'waterfall', 'waterfall', [0.45, 0.8], { allowOverlap: true }),
        icon('overlay-cave', 'cave', 'cave', [0.45, 0.8], { allowOverlap: true }),
        label('overlay-waterfall-label', 'waterfall', ['get', 'name'], palette, 13),
        label('overlay-cave-label', 'cave', ['get', 'name'], palette, 13),
      ],
    },
    {
      key: 'crossing',
      labelKey: 'overlay.crossing',
      swatch: 'line',
      color: '#a8a29e', // mid-tone: the legend reads on both a light and a dark panel
      defaultVisible: true,
      layers: [
        // A bridge reads as a pale deck between two dark edges, laid over the trail's own line.
        {
          id: 'overlay-bridge-casing',
          type: 'line',
          source: OVERLAY_SOURCE_ID,
          'source-layer': 'bridge',
          layout: { 'line-cap': 'butt' },
          paint: {
            'line-color': palette.bridgeCasing,
            'line-width': ['interpolate', ['linear'], ['zoom'], 13, 3, 17, 9],
          },
        },
        {
          id: 'overlay-bridge-deck',
          type: 'line',
          source: OVERLAY_SOURCE_ID,
          'source-layer': 'bridge',
          layout: { 'line-cap': 'butt' },
          paint: {
            'line-color': palette.bridgeDeck,
            'line-width': ['interpolate', ['linear'], ['zoom'], 13, 1.4, 17, 5.5],
          },
        },
        icon('overlay-ford', 'ford', 'ford', [0.4, 0.7]),
      ],
    },
    {
      key: 'landmark',
      labelKey: 'overlay.landmark',
      swatch: 'icon',
      icon: 'church',
      color: '#78716c', // mid-tone: the legend reads on both a light and a dark panel
      defaultVisible: true,
      layers: [
        icon('overlay-cemetery', 'cemetery', 'cemetery', [0.4, 0.75]),
        icon('overlay-church', 'church', 'church', [0.5, 0.95]),
        label('overlay-church-label', 'church', ['get', 'name'], palette, 14),
      ],
    },
    {
      key: 'toilets',
      labelKey: 'overlay.toilets',
      swatch: 'icon',
      icon: 'toilets',
      color: palette.toilets,
      defaultVisible: true,
      layers: [icon('overlay-toilets', 'toilets', 'toilets', [0.4, 0.75])],
    },
    {
      key: 'shop',
      labelKey: 'overlay.shop',
      swatch: 'icon',
      icon: 'shop',
      color: palette.shop,
      defaultVisible: true,
      layers: [
        icon('overlay-shop', 'shop', 'shop', [0.4, 0.75]),
        label('overlay-shop-label', 'shop', ['get', 'name'], palette, 15),
      ],
    },
    {
      key: 'eatery',
      labelKey: 'overlay.eatery',
      swatch: 'icon',
      icon: 'eatery',
      color: palette.eatery,
      defaultVisible: true,
      layers: [
        icon('overlay-eatery', 'eatery', 'eatery', [0.4, 0.75]),
        label('overlay-eatery-label', 'eatery', ['get', 'name'], palette, 15),
      ],
    },
    {
      key: 'aerialway',
      labelKey: 'overlay.aerialway',
      swatch: 'line',
      color: '#78716c', // mid-tone: the legend reads on both a light and a dark panel
      defaultVisible: true,
      layers: [
        {
          id: 'overlay-aerialway',
          type: 'line',
          source: OVERLAY_SOURCE_ID,
          'source-layer': 'aerialway',
          paint: {
            'line-color': palette.aerialway,
            'line-width': ['interpolate', ['linear'], ['zoom'], 10, 1, 15, 2.2],
            'line-dasharray': [2, 2],
          },
        },
      ],
    },
    {
      key: 'guidepost',
      labelKey: 'overlay.guidepost',
      swatch: 'icon',
      icon: 'guidepost',
      color: palette.guidepost,
      defaultVisible: false,
      layers: [icon('overlay-guidepost', 'guidepost', 'guidepost', [0.35, 0.65])],
    },
    {
      key: 'power',
      labelKey: 'overlay.power',
      swatch: 'line',
      color: palette.power,
      defaultVisible: false,
      layers: [
        {
          id: 'overlay-power-line',
          type: 'line',
          source: OVERLAY_SOURCE_ID,
          'source-layer': 'power_line',
          paint: {
            'line-color': palette.power,
            'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.8, 15, 1.6],
            'line-dasharray': [4, 3],
            'line-opacity': 0.9,
          },
        },
        dot('overlay-power-tower', 'power_tower', palette.power, outline, [1.5, 3]),
      ],
    },
  ];
}

export function defaultVisibleGroups(): Set<OverlayGroupKey> {
  return new Set(getOverlayGroups(false).filter((group) => group.defaultVisible).map((group) => group.key));
}

/**
 * Add the overlay source and its layers. Call it before the trail and POI layers so they stay on top.
 * Layers of hidden groups are added with `visibility: none`, so a toggle is one layout change.
 */
export function addOverlay(
  map: maplibregl.Map,
  pmtilesUrl: string,
  isDark: boolean,
  visibleGroups: Set<OverlayGroupKey>,
): void {
  registerOverlayImages(map, iconColors(isDark ? DARK : LIGHT), (isDark ? DARK : LIGHT).halo);
  map.addSource(OVERLAY_SOURCE_ID, {
    type: 'vector',
    url: pmtilesUrl,
    attribution: '© OpenStreetMap contributors',
  });
  for (const group of getOverlayGroups(isDark)) {
    const visibility = visibleGroups.has(group.key) ? 'visible' : 'none';
    for (const layer of group.layers) {
      map.addLayer({ ...layer, layout: { ...(layer.layout ?? {}), visibility } } as maplibregl.LayerSpecification);
    }
  }
}

export function setOverlayGroupVisibility(map: maplibregl.Map, group: OverlayGroup, visible: boolean): void {
  for (const layer of group.layers) {
    if (map.getLayer(layer.id)) map.setLayoutProperty(layer.id, 'visibility', visible ? 'visible' : 'none');
  }
}
