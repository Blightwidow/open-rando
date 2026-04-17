# Contour tile pipeline: SRTM .hgt → GDAL → tippecanoe → PMTiles
#
# Prerequisites: gdal (gdal_contour), tippecanoe, ogrmerge.py
# Input: SRTM .hgt tiles in SRTM_DIR (cached by the Python pipeline)
# Output: contours.pmtiles in OUTPUT_DIR
#
# Contours are extracted per-tile (no merge step), then combined.
#
# Usage:
#   make install    # verify dependencies
#   make            # build contours.pmtiles
#   make upload     # upload to GitHub Release
#   make clean      # remove intermediate files

SRTM_DIR ?= $(HOME)/.cache/open-rando/srtm
OUTPUT_DIR ?= $(HOME)/.local/share/open-rando/data
BUILD_DIR := build

HGT_FILES := $(wildcard $(SRTM_DIR)/*.hgt)
CONTOUR_25M_DIR := $(BUILD_DIR)/contours_25m
CONTOUR_100M_DIR := $(BUILD_DIR)/contours_100m
CONTOURS_25M := $(BUILD_DIR)/contours_25m.fgb
CONTOURS_100M := $(BUILD_DIR)/contours_100m.fgb
CONTOURS_25M_CLIPPED := $(BUILD_DIR)/contours_25m_clipped.fgb
CONTOURS_100M_CLIPPED := $(BUILD_DIR)/contours_100m_clipped.fgb
PMTILES := $(OUTPUT_DIR)/contours.pmtiles
FRANCE_POLYGON := $(OUTPUT_DIR)/france-boundary.geojson

# Per-tile contour outputs
PER_TILE_25M := $(patsubst $(SRTM_DIR)/%.hgt,$(CONTOUR_25M_DIR)/%.fgb,$(HGT_FILES))
PER_TILE_100M := $(patsubst $(SRTM_DIR)/%.hgt,$(CONTOUR_100M_DIR)/%.fgb,$(HGT_FILES))

.PHONY: all install upload clean

all: $(PMTILES)

$(CONTOUR_25M_DIR) $(CONTOUR_100M_DIR):
	mkdir -p $@

# Extract 25m contours per tile
$(CONTOUR_25M_DIR)/%.fgb: $(SRTM_DIR)/%.hgt | $(CONTOUR_25M_DIR)
	gdal_contour -a elevation -i 25 -f FlatGeobuf $< $@

# Extract 100m contours per tile
$(CONTOUR_100M_DIR)/%.fgb: $(SRTM_DIR)/%.hgt | $(CONTOUR_100M_DIR)
	gdal_contour -a elevation -i 100 -f FlatGeobuf $< $@

# Merge per-tile contours into single files
$(CONTOURS_25M): $(PER_TILE_25M)
	ogrmerge.py -o $@ -f FlatGeobuf -single $^

$(CONTOURS_100M): $(PER_TILE_100M)
	ogrmerge.py -o $@ -f FlatGeobuf -single $^

# Clip merged contours to French admin border
$(CONTOURS_25M_CLIPPED): $(CONTOURS_25M) $(FRANCE_POLYGON)
	ogr2ogr -f FlatGeobuf -clipsrc $(FRANCE_POLYGON) $@ $<

$(CONTOURS_100M_CLIPPED): $(CONTOURS_100M) $(FRANCE_POLYGON)
	ogr2ogr -f FlatGeobuf -clipsrc $(FRANCE_POLYGON) $@ $<

# Build vector tiles from both clipped contour layers
$(PMTILES): $(CONTOURS_25M_CLIPPED) $(CONTOURS_100M_CLIPPED)
	mkdir -p $(OUTPUT_DIR)
	tippecanoe \
		-o $@ \
		--force \
		--name "contours" \
		--attribution "SRTM / NASA" \
		--no-feature-limit \
		--no-tile-size-limit \
		-L'{"file": "$(CONTOURS_25M_CLIPPED)", "layer": "contour_25m", "minzoom": 13, "maxzoom": 15}' \
		-L'{"file": "$(CONTOURS_100M_CLIPPED)", "layer": "contour_100m", "minzoom": 8, "maxzoom": 15}'

install:
	@command -v gdal_contour >/dev/null 2>&1 || { echo "ERROR: gdal_contour not found. Install GDAL."; exit 1; }
	@command -v ogrmerge.py >/dev/null 2>&1 || { echo "ERROR: ogrmerge.py not found. Install GDAL."; exit 1; }
	@command -v tippecanoe >/dev/null 2>&1 || { echo "ERROR: tippecanoe not found. Install tippecanoe."; exit 1; }
	@echo "All dependencies found."

upload: $(PMTILES)
	gh release upload latest $(PMTILES) --clobber

clean:
	rm -rf $(BUILD_DIR)
