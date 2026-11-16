import type maplibregl from 'maplibre-gl';

/**
 * Map icons for the hiking overlay, drawn on a canvas: a triangle for a summit, a house for a
 * hut, a cross for a church, and so on, in the manner of the IGN Scan 25 map. The Protomaps
 * sprite has none of them. Each icon is a coloured shape under a halo of the background colour,
 * so it stays readable on forest, snow and roads.
 */

export type OverlayIconName =
  | 'peak'
  | 'pass'
  | 'hut'
  | 'shelter'
  | 'water'
  | 'spring'
  | 'viewpoint'
  | 'waterfall'
  | 'cave'
  | 'ford'
  | 'toilets'
  | 'church'
  | 'cemetery'
  | 'shop'
  | 'eatery'
  | 'guidepost';

/** Colour of each icon, one per theme. */
export type OverlayIconColors = Record<OverlayIconName, string>;

interface Shape {
  /** SVG path data on a 48 by 48 grid. */
  path: string;
  fill?: boolean;
  evenOdd?: boolean;
  /** Stroke width; a shape with neither `fill` nor `stroke` draws nothing. */
  stroke?: number;
}

interface IconSpec {
  shapes: Shape[];
  /** Text laid over the shape in the halo colour (the "WC" of a toilet). */
  text?: string;
}

const GRID = 48;
const HALO_WIDTH = 5;
const IMAGE_PIXEL_RATIO = 2;

const TRIANGLE = 'M24 7L43 40H5Z';
const HOUSE = 'M24 6L44 24H38V42H10V24H4Z';
const HOUSE_OUTLINE = 'M24 10L41 25V40H7V25Z';
const DROP = 'M24 5C24 5 38 21 38 31A14 14 0 0 1 10 31C10 21 24 5 24 5Z';

const ICONS: Record<OverlayIconName, IconSpec> = {
  peak: { shapes: [{ path: TRIANGLE, fill: true }] },
  pass: { shapes: [{ path: 'M24 12L40 38H8Z', stroke: 5 }] },
  hut: { shapes: [{ path: HOUSE, fill: true }] },
  shelter: { shapes: [{ path: HOUSE_OUTLINE, stroke: 5 }] },
  water: { shapes: [{ path: DROP, fill: true }] },
  spring: { shapes: [{ path: DROP, stroke: 5 }] },
  viewpoint: {
    shapes: [
      { path: 'M3 24Q24 4 45 24Q24 44 3 24Z', stroke: 4 },
      { path: 'M17 24a7 7 0 1 0 14 0a7 7 0 1 0 -14 0Z', fill: true },
    ],
  },
  waterfall: { shapes: [{ path: 'M13 8V32M24 8V42M35 8V26', stroke: 6 }] },
  cave: {
    shapes: [{ path: 'M5 42V28A19 19 0 0 1 43 28V42Z M15 42V30A9 9 0 0 1 33 30V42Z', fill: true, evenOdd: true }],
  },
  ford: { shapes: [{ path: 'M4 18Q14 8 24 18T44 18M4 32Q14 22 24 32T44 32', stroke: 4 }] },
  toilets: {
    shapes: [{ path: 'M10 8H38Q42 8 42 12V36Q42 40 38 40H10Q6 40 6 36V12Q6 8 10 8Z', fill: true }],
    text: 'WC',
  },
  church: { shapes: [{ path: 'M20.5 5H27.5V43H20.5Z M11 15H37V22H11Z', fill: true }] },
  cemetery: {
    shapes: [
      { path: 'M8 8H40V40H8Z', stroke: 4 },
      { path: 'M22 15H26V35H22Z M16.5 20H31.5V24H16.5Z', fill: true },
    ],
  },
  shop: {
    shapes: [
      { path: 'M5 20H43L37 40H11Z', fill: true },
      { path: 'M14 20Q24 2 34 20', stroke: 4 },
    ],
  },
  eatery: {
    shapes: [
      { path: 'M11 7V20Q11 25 17 25Q23 25 23 20V7M17 7V42', stroke: 4 },
      { path: 'M34 7C42 13 42 23 34 28Z', fill: true },
      { path: 'M34 28V42', stroke: 4 },
    ],
  },
  guidepost: {
    shapes: [
      { path: 'M12 6V43', stroke: 4 },
      { path: 'M12 12H35L42 19L35 26H12Z', fill: true },
    ],
  },
};

export const OVERLAY_ICON_NAMES = Object.keys(ICONS) as OverlayIconName[];

/** Id under which an icon is registered on the map; the layers' `icon-image` uses it. */
export function overlayIconImageId(name: OverlayIconName): string {
  return `overlay-icon-${name}`;
}

function paintIcon(context: CanvasRenderingContext2D, spec: IconSpec, color: string, halo: string): void {
  const paths = spec.shapes.map((shape) => new Path2D(shape.path));
  context.lineJoin = 'round';
  context.lineCap = 'round';

  // Every halo first, so one part of an icon never cuts a ring into another.
  context.strokeStyle = halo;
  context.fillStyle = halo;
  spec.shapes.forEach((shape, index) => {
    context.lineWidth = (shape.stroke ?? 0) + HALO_WIDTH;
    context.stroke(paths[index]);
  });
  spec.shapes.forEach((shape, index) => {
    if (shape.fill) context.fill(paths[index], shape.evenOdd ? 'evenodd' : 'nonzero');
  });

  context.strokeStyle = color;
  context.fillStyle = color;
  spec.shapes.forEach((shape, index) => {
    if (shape.fill) context.fill(paths[index], shape.evenOdd ? 'evenodd' : 'nonzero');
    if (shape.stroke) {
      context.lineWidth = shape.stroke;
      context.stroke(paths[index]);
    }
  });

  if (spec.text) {
    context.fillStyle = halo;
    context.font = 'bold 17px sans-serif';
    context.textAlign = 'center';
    context.textBaseline = 'middle';
    context.fillText(spec.text, GRID / 2, GRID / 2 + 1);
  }
}

function drawIcon(name: OverlayIconName, color: string, halo: string): HTMLCanvasElement | null {
  const canvas = document.createElement('canvas');
  canvas.width = GRID;
  canvas.height = GRID;
  const context = canvas.getContext('2d');
  if (!context) return null;
  paintIcon(context, ICONS[name], color, halo);
  return canvas;
}

/**
 * Add every overlay icon to the map. `setStyle` drops images, so call it each time the overlay is
 * added; an icon already present is replaced, which is how a theme change recolours them.
 */
export function registerOverlayImages(map: maplibregl.Map, colors: OverlayIconColors, halo: string): void {
  for (const name of OVERLAY_ICON_NAMES) {
    const canvas = drawIcon(name, colors[name], halo);
    const context = canvas?.getContext('2d');
    if (!canvas || !context) continue;
    const imageId = overlayIconImageId(name);
    if (map.hasImage(imageId)) map.removeImage(imageId);
    map.addImage(imageId, context.getImageData(0, 0, GRID, GRID), { pixelRatio: IMAGE_PIXEL_RATIO });
  }
}

/** The icon as a PNG data URL, for the legend. */
export function overlayIconDataUrl(name: OverlayIconName, color: string, halo: string): string {
  return drawIcon(name, color, halo)?.toDataURL('image/png') ?? '';
}
