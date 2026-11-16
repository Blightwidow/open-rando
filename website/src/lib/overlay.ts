import type maplibregl from 'maplibre-gl';

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
  | 'aerialway'
  | 'guidepost'
  | 'power';

export interface OverlayGroup {
  key: OverlayGroupKey;
  /** Translation key of the toggle and legend label. */
  labelKey: string;
  /** Legend swatch: a dot for point features, a stroke for lines, a cross for churches. */
  swatch: 'dot' | 'line' | 'cross';
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

export const CHURCH_ICON_ID = 'overlay-church-cross';
export const CEMETERY_ICON_ID = 'overlay-cemetery-cross';

/** Symbol layer drawing one of the icons registered by `registerOverlayImages`. */
function icon(id: string, sourceLayer: string, iconId: string, size: [number, number]): maplibregl.LayerSpecification {
  return {
    id,
    type: 'symbol',
    source: OVERLAY_SOURCE_ID,
    'source-layer': sourceLayer,
    layout: {
      'icon-image': iconId,
      'icon-size': ['interpolate', ['linear'], ['zoom'], 12, size[0], 16, size[1]],
      'icon-allow-overlap': true,
    },
  };
}

const ICON_PIXELS = 48;

/**
 * Cross for a church and cross in a square for a cemetery, in the manner of the IGN Scan 25 map.
 * Drawn on a canvas (a halo under a solid stroke keeps them readable on any ground) because the
 * Protomaps sprite has no such icons. Works with `setStyle`, which drops images: call it each time.
 */
export function registerOverlayImages(map: maplibregl.Map, isDark: boolean): void {
  const palette = isDark ? DARK : LIGHT;
  const images: Array<[string, (context: CanvasRenderingContext2D, color: string, halo: string) => void, string]> = [
    [CHURCH_ICON_ID, drawChurchCross, palette.church],
    [CEMETERY_ICON_ID, drawCemeteryCross, palette.cemetery],
  ];
  for (const [iconId, draw, color] of images) {
    const canvas = document.createElement('canvas');
    canvas.width = ICON_PIXELS;
    canvas.height = ICON_PIXELS;
    const context = canvas.getContext('2d');
    if (!context) continue;
    draw(context, color, palette.halo);
    if (map.hasImage(iconId)) map.removeImage(iconId);
    map.addImage(iconId, context.getImageData(0, 0, ICON_PIXELS, ICON_PIXELS), { pixelRatio: 2 });
  }
}

function fillCross(context: CanvasRenderingContext2D, centerX: number, top: number, height: number, thickness: number, grow: number): void {
  const armY = top + height * 0.3;
  const armWidth = height * 0.62;
  context.fillRect(centerX - thickness / 2 - grow, top - grow, thickness + 2 * grow, height + 2 * grow);
  context.fillRect(centerX - armWidth / 2 - grow, armY - thickness / 2 - grow, armWidth + 2 * grow, thickness + 2 * grow);
}

function drawChurchCross(context: CanvasRenderingContext2D, color: string, halo: string): void {
  context.fillStyle = halo;
  fillCross(context, ICON_PIXELS / 2, 6, 36, 7, 2.5);
  context.fillStyle = color;
  fillCross(context, ICON_PIXELS / 2, 6, 36, 7, 0);
}

function drawCemeteryCross(context: CanvasRenderingContext2D, color: string, halo: string): void {
  const inset = 7;
  const side = ICON_PIXELS - 2 * inset;
  context.lineWidth = 6;
  context.strokeStyle = halo;
  context.strokeRect(inset, inset, side, side);
  context.lineWidth = 3;
  context.strokeStyle = color;
  context.strokeRect(inset, inset, side, side);
  context.fillStyle = halo;
  fillCross(context, ICON_PIXELS / 2, 14, 20, 4, 1.5);
  context.fillStyle = color;
  fillCross(context, ICON_PIXELS / 2, 14, 20, 4, 0);
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
      swatch: 'dot',
      color: palette.water,
      defaultVisible: true,
      layers: [
        dot('overlay-spring', 'spring', palette.water, outline, [2.5, 4.5], { hollow: true }),
        dot('overlay-water', 'water', palette.water, outline, [3, 5.5]),
      ],
    },
    {
      key: 'shelter',
      labelKey: 'overlay.shelter',
      swatch: 'dot',
      color: palette.shelter,
      defaultVisible: true,
      layers: [
        dot('overlay-shelter', 'shelter', palette.shelter, outline, [3, 5]),
        dot('overlay-hut', 'hut', palette.shelter, outline, [4.5, 7.5]),
        label('overlay-hut-label', 'hut', ['get', 'name'], palette, 12),
      ],
    },
    {
      key: 'peak',
      labelKey: 'overlay.peak',
      swatch: 'dot',
      color: palette.peak,
      defaultVisible: true,
      layers: [
        dot('overlay-peak', 'peak', palette.peak, outline, [2.5, 5], { named: true }),
        label('overlay-peak-label', 'peak', ELEVATION_LABEL, palette, 11),
        dot('overlay-pass', 'pass', palette.peak, outline, [2.5, 5], { hollow: true }),
        label('overlay-pass-label', 'pass', ELEVATION_LABEL, palette, 12),
      ],
    },
    {
      key: 'viewpoint',
      labelKey: 'overlay.viewpoint',
      swatch: 'dot',
      color: palette.viewpoint,
      defaultVisible: true,
      layers: [dot('overlay-viewpoint', 'viewpoint', palette.viewpoint, outline, [3, 5.5])],
    },
    {
      key: 'nature',
      labelKey: 'overlay.nature',
      swatch: 'dot',
      color: palette.waterfall,
      defaultVisible: true,
      layers: [
        dot('overlay-waterfall', 'waterfall', palette.waterfall, outline, [3, 5.5]),
        dot('overlay-cave', 'cave', palette.cave, outline, [3, 5.5]),
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
        dot('overlay-ford', 'ford', palette.water, outline, [3, 5.5], { hollow: true }),
      ],
    },
    {
      key: 'landmark',
      labelKey: 'overlay.landmark',
      swatch: 'cross',
      color: '#78716c', // mid-tone: the legend reads on both a light and a dark panel
      defaultVisible: true,
      layers: [
        icon('overlay-cemetery', 'cemetery', CEMETERY_ICON_ID, [0.65, 1]),
        icon('overlay-church', 'church', CHURCH_ICON_ID, [0.75, 1.1]),
        label('overlay-church-label', 'church', ['get', 'name'], palette, 14),
      ],
    },
    {
      key: 'toilets',
      labelKey: 'overlay.toilets',
      swatch: 'dot',
      color: palette.toilets,
      defaultVisible: true,
      layers: [dot('overlay-toilets', 'toilets', palette.toilets, outline, [3, 5])],
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
      swatch: 'dot',
      color: palette.guidepost,
      defaultVisible: false,
      layers: [dot('overlay-guidepost', 'guidepost', palette.guidepost, outline, [2, 3.5])],
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
  registerOverlayImages(map, isDark);
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
