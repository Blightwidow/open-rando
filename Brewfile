# Native tools TrainRando needs. Install everything with:
#
#   brew bundle
#
# Python packages come from uv (pipeline/pyproject.toml), JS packages from bun
# (website/package.json). Only the binaries the Makefiles shell out to live here.

# --- Pipeline ---------------------------------------------------------------
# uv runs the Python pipeline; osmium-tool filters the Geofabrik France extract
# into the per-layer PBFs that replace Overpass queries (make -f Makefile.osm).
brew "uv"
brew "osmium-tool"

# --- Tile pipelines --------------------------------------------------------
# gdal provides gdal_contour, gdalwarp, gdalbuildvrt, ogrmerge.py and ogr2ogr
# for the contour and hillshade builds; tippecanoe turns the contours into
# vector tiles; rclone uploads the PMTiles archives to Cloudflare R2.
brew "gdal"
brew "tippecanoe"
brew "rclone"

# go-pmtiles is not in Homebrew: tiles/download.sh fetches the pinned release
# binary (see tiles/Makefile.protomaps).

# --- Website ---------------------------------------------------------------
tap "oven-sh/bun"
brew "oven-sh/bun/bun"
