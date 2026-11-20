// Generated from pipeline/src/open_rando/data/tile-grid.schema.json by
// website/scripts/generate-types.mjs. Do not edit: change the schema and rerun
// `bun run generate:types`.

/**
 * @minItems 4
 * @maxItems 4
 */
export type Bbox = [number, number, number, number];
export type Zoom = number;

/**
 * Contract for data/grid.json (version 2), written by tiles/build-grid.py and read by the mobile client. `layers`, `base` and `files` are open maps keyed by layer name; the cross-checks JSON Schema cannot express (matching layer keys, matching zoom ranges, square keys inside the grid) live in tiles/tile_manifests.py.
 */
export interface OpenRandoTileGridManifest {
  version: 2;
  source_snapshot: string;
  grid: {
    bbox: Bbox;
    cols: number;
    rows: number;
    pad_deg: number;
  };
  layers: {
    [k: string]: {
      base_minzoom: Zoom;
      base_maxzoom: Zoom;
      grid_minzoom: Zoom;
      grid_maxzoom: Zoom;
    };
  };
  base: {
    [k: string]: TileFile;
  };
  squares: {
    [k: string]: {
      bbox: Bbox;
      files: {
        [k: string]: TileFile;
      };
    };
  };
}
export interface TileFile {
  url: string;
  size: number;
  minzoom: Zoom;
  maxzoom: Zoom;
}
