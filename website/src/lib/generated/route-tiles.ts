// Generated from pipeline/src/open_rando/data/route-tiles.schema.json by
// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun
// `bun run generate:types`.

/**
 * Contract for data/routes/{id}/pmtiles.json, written by tiles/build-routes.py and read by the mobile client. Each `squares` entry is a [col, row] pair that must exist in grid.json; that cross-check lives in tiles/tile_manifests.py.
 */
export interface OpenRandoPerRouteTileManifest {
  route_id: string;
  source_snapshot: string;
  /**
   * @minItems 4
   * @maxItems 4
   */
  bbox: [number, number, number, number];
  squares: never[][];
}
