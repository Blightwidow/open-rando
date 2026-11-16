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
] as const;

export type OverlayGroupKey = 'river' | 'water' | 'shelter' | 'peak' | 'viewpoint' | 'guidepost' | 'power';

export interface OverlayGroup {
  key: OverlayGroupKey;
  /** Translation key of the toggle and legend label. */
  labelKey: string;
  /** Legend swatch: a dot for point features, a stroke for lines. */
  swatch: 'dot' | 'line';
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
  halo: '#1c1917',
  text: '#e7e5e4',
  dotOutline: '#1c1917',
};

const FONT = ['Noto Sans Regular'];

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
        label(
          'overlay-peak-label',
          'peak',
          ['case', ['has', 'ele'], ['concat', ['get', 'name'], '\n', ['to-string', ['get', 'ele']], ' m'], ['get', 'name']],
          palette,
          11,
        ),
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
