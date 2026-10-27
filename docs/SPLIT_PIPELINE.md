# Split pipeline: tracks, POIs, links

Status: done (branch `feat/split-pipeline-tracks-pois`): pipeline stages, website, mobile contract.

## Goals

1. Compute each track and the POIs separately; each output is reusable alone.
2. POIs are not limited to the surroundings of curated tracks, so the companion app can import a custom GPX and find POIs along it.

## Decisions

- POI scope: all of France (the tile-grid bbox).
- POI storage: fixed grid, the same 12x8 grid over the same bbox as `tiles/build-grid.py`.
- POI ids are stable: `<osm_type>/<osm_id>` (for example `node/123`, `way/456`).
- Tracks are computed by the pipeline. Custom GPX is linked to POIs on the client, from the POI grid.
- Train station filtering by SNCF stays in the POI stage. A POI of kind `train_station` is already SNCF-verified.
- Landmarks stay per track (AI image prompts), computed in the `tracks` stage.
- Breaking change: the old `routes[].pois` is removed right away, with no shim.
- No elevation for custom tracks.

## Output layout (`~/.local/share/open-rando/data/`)

```
tracks/<id>/track.json           # track metadata, no POIs (written by `tracks`)
tracks/<id>/trail.geojson        # trail geometry only
tracks/<id>/trail.gpx            # trail only, no waypoints
tracks/<id>/elevation.json       # profile; train station positions come from links/
catalog.json                     # merge of every track.json + link counts (written by `catalog`)
pois/index.json                  # grid definition + non-empty squares + counts
pois/<col>_<row>.json            # every POI whose point is inside the square
links/<id>.json                  # POIs near the track, ordered, with distances
```

`generated_at`, `source`, and `license` stay on each top-level file.

### `pois/index.json`

```json
{
  "generated_at": "...",
  "grid": {"bbox": [-5.5, 41.0, 10.0, 51.5], "cols": 12, "rows": 8},
  "squares": [{"col": 3, "row": 4, "count": 1280}]
}
```

`squares` lists every square built so far, empty ones included (`count: 0`, no file). A reader that needs a square absent from the list must fail: it was never built, which is different from empty. `link` does.

A square covers `[lon_min + col*lon_step, lon_min + (col+1)*lon_step)` and the same for latitude.
A POI on the outer edge goes into the last square. POIs outside the bbox are dropped.

### `pois/<col>_<row>.json`

```json
{
  "square": {"col": 3, "row": 4},
  "pois": [
    {
      "id": "node/123",
      "kind": "train_station" | "bus_stop" | "hotel" | "camping",
      "name": "...",
      "lat": 0.0,
      "lon": 0.0,
      "url": "..." | null,
      "transit_lines": [],
      "rail_service": {...} | null
    }
  ]
}
```

### `links/<id>.json`

```json
{
  "route_id": "...",
  "counts": {"train_station": 15, "bus_stop": 91, "hotel": 110, "camping": 27,
             "train_station_with_rail_service": 12},
  "links": [
    {
      "poi_id": "node/123",
      "kind": "train_station",
      "distance_to_trail_m": 420.0,
      "distance_km": 12.3,
      "junction": [4.83, 45.76]
    }
  ]
}
```

`distance_km` is the position along the trail (train stations only; null for other kinds). `junction` is `[lon, lat]`, where the walk from the POI meets the trail: for train stations it is the point chosen by the OSRM walking-distance refinement. Links are sorted by `distance_km` (null last), then by distance to the trail.

Link thresholds: train stations 5 km, bus stops 2 km, hotels and campings 3 km. Bus stops without a GTFS match stay in the POI grid (OSM-only lines).

## Stages and commands

| Stage | Command | Input | Output |
| --- | --- | --- | --- |
| 1 | `tracks` | routes.yaml, OSM, SRTM | `tracks/` |
| 2a | `gtfs` | transport.data.gouv.fr feed catalog | GTFS stop index (`~/.cache/open-rando/gtfs/stops-index.sqlite`) + per-feed departures cache |
| 2b | `pois` | OSM index, SNCF, GTFS stop index | `pois/` |
| 3 | `link` | `tracks/`, `pois/` | `links/` |
| 4 | `catalog` | `tracks/`, `links/` | `catalog.json` (rebuilt from the tracks on disk) |

`pipeline` runs the stages in order (`gtfs` is skipped with `--skip-gtfs`). With `--route`, only the POI squares the track touches are built. `catalog.json` stays at the data root: the website, CI and the mobile client already read it there, and `catalog` rebuilds it from the tracks on disk, so there is no `--reset`.
`tracks` does not read POIs. The département comes from the nearest SNCF station to the trail start (within ~25 km), read straight from the station layer. The old pipeline used the first station matched along the trail.
The "at least 2 train stations" validity rule moves to `catalog`: a track without enough linked stations stays in `tracks/` but is left out of the catalog.

## Client-side linking (custom GPX)

The app loads the POI squares intersecting the GPX bbox plus a margin, then for each POI within `MAX_*_DISTANCE`:
projects the POI onto the track, measures haversine distance along it. Walking-distance junction refinement (OSRM) is not available offline, so custom tracks use the nearest vertex.

## Migration steps

1. Grid math and POI model with stable ids.
2. `pois` stage (France-wide, gridded).
3. `tracks` stage (no POIs).
4. `link` stage.
5. `catalog` stage, new schemas, tests.
6. Website: route pages join `links/<id>.json` with the POI squares at build time (`website/src/lib/catalog.ts`, pure join in `route-pois.ts`, grid maths in `poi-grid.ts`); elevation and GeoJSON are read from `tracks/<id>/`. The join throws when a linked POI is missing from the grid, so a stale `link` fails the build.
7. Update `ARCHITECTURE.md`, `MOBILE_OFFLINE.md`, `CLAUDE.md`.

Known change: the downloadable `trail.gpx` no longer carries train station waypoints (POIs are not known to the `tracks` stage).

## Risks

- GTFS: the `gtfs` stage downloads every feed once (562 feeds, ≥293 MB) instead of calling the `gtfs-stops` API per 28 km chunk. The per-feed departures cache is keyed by ISO week, so `pois` run more than a week after `gtfs` re-downloads the feeds it needs: rerun `gtfs` first.
- `routes[].pois` removal breaks the website and the mobile client together; they ship with this branch.
