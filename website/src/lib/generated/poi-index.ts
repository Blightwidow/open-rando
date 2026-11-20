// Generated from pipeline/src/open_rando/data/poi-index.schema.json by
// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun
// `bun run generate:types`.

/**
 * Contract for data/pois/index.json. `squares` lists every square built, empty ones included: a square absent from it was never built.
 */
export interface OpenRandoPOIGridIndex {
  generated_at: string;
  source: string;
  license: string;
  grid: PoiGridDefinition;
  squares: {
    col: number;
    row: number;
    count: number;
  }[];
}
export interface PoiGridDefinition {
  /**
   * @minItems 4
   * @maxItems 4
   */
  bbox: [number, number, number, number];
  cols: number;
  rows: number;
}
