// The fixed POI grid written by the pipeline's `pois` stage (data/pois/index.json).
// Same maths as pipeline/src/open_rando/poi_grid.py: a square is [col, row].

export interface PoiGridDefinition {
  /** [lonMin, latMin, lonMax, latMax] */
  bbox: [number, number, number, number];
  cols: number;
  rows: number;
}

export type PoiSquare = [number, number];

export function squareFileName([column, row]: PoiSquare): string {
  return `${column}_${row}.json`;
}

/** Squares intersecting bbox ([lonMin, latMin, lonMax, latMax]) widened by a margin. */
export function squaresForBoundingBox(
  grid: PoiGridDefinition,
  bbox: [number, number, number, number],
  marginDegrees = 0
): PoiSquare[] {
  const [gridLonMin, gridLatMin, gridLonMax, gridLatMax] = grid.bbox;
  const lonMin = Math.max(bbox[0] - marginDegrees, gridLonMin);
  const latMin = Math.max(bbox[1] - marginDegrees, gridLatMin);
  const lonMax = Math.min(bbox[2] + marginDegrees, gridLonMax);
  const latMax = Math.min(bbox[3] + marginDegrees, gridLatMax);
  if (lonMin > lonMax || latMin > latMax) return [];

  const lonStep = (gridLonMax - gridLonMin) / grid.cols;
  const latStep = (gridLatMax - gridLatMin) / grid.rows;
  const firstColumn = Math.max(Math.floor((lonMin - gridLonMin) / lonStep), 0);
  const lastColumn = Math.min(Math.floor((lonMax - gridLonMin) / lonStep), grid.cols - 1);
  const firstRow = Math.max(Math.floor((latMin - gridLatMin) / latStep), 0);
  const lastRow = Math.min(Math.floor((latMax - gridLatMin) / latStep), grid.rows - 1);

  const squares: PoiSquare[] = [];
  for (let row = firstRow; row <= lastRow; row++) {
    for (let column = firstColumn; column <= lastColumn; column++) {
      squares.push([column, row]);
    }
  }
  return squares;
}
