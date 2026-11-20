import os

# Roots for pipeline output and download caches. Override with
# OPEN_RANDO_DATA_DIR / OPEN_RANDO_CACHE_DIR (tests, CI, a second checkout).
DATA_ROOT = os.environ.get("OPEN_RANDO_DATA_DIR", "~/.local/share/open-rando/data")
CACHE_ROOT = os.environ.get("OPEN_RANDO_CACHE_DIR", "~/.cache/open-rando")

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = 120
OVERPASS_CACHE_DIRECTORY = f"{CACHE_ROOT}/overpass"
OVERPASS_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days
OVERPASS_TRAIL_CACHE_TTL_SECONDS = 60 * 24 * 3600  # 60 days

OVERPASS_COOLDOWN_SECONDS = 5

# Local OSM extracts (see pipeline/Makefile.osm). When the index holds a layer,
# the matching fetcher reads it instead of calling Overpass.
OSM_EXTRACT_DIRECTORY = f"{CACHE_ROOT}/osm"
OSM_INDEX_PATH = f"{CACHE_ROOT}/osm/extract-index.sqlite"

MAX_STATION_DISTANCE_METERS = 5000
MAX_STATION_BBOX_DEGREES = 3.0

OUTPUT_DIRECTORY = DATA_ROOT
TRACKS_DIRECTORY = f"{DATA_ROOT}/tracks"
LINKS_DIRECTORY = f"{DATA_ROOT}/links"
POIS_DIRECTORY = f"{DATA_ROOT}/pois"
CATALOG_PATH = f"{DATA_ROOT}/catalog.json"
RUN_REPORT_PATH = f"{DATA_ROOT}/run-report.json"
# Routes whose last run raised (timeouts, rate limits), so --retry-failed
# reruns only those instead of the whole catalog.
FAILURE_LOG_PATH = f"{DATA_ROOT}/failed-routes.json"

MIN_TRAIN_STATIONS_PER_ROUTE = 2

MAX_BUS_STOP_DISTANCE_METERS = 2000

GTFS_DATASETS_API_URL = "https://transport.data.gouv.fr/api/datasets"
GTFS_CACHE_DIRECTORY = f"{CACHE_ROOT}/gtfs"
GTFS_FEEDS_CACHE_DIRECTORY = f"{CACHE_ROOT}/gtfs/feeds"
GTFS_STOPS_INDEX_PATH = f"{CACHE_ROOT}/gtfs/stops-index.sqlite"
GTFS_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days
GTFS_MATCH_RADIUS_METERS = 150
# Train stations sprawl (several platforms, several operators), so their GTFS
# stops sit further from the OSM node than a bus stop pole does.
TRAIN_GTFS_MATCH_RADIUS_METERS = 500

SRTM_CACHE_DIRECTORY = f"{CACHE_ROOT}/srtm"
SRTM_BASE_URL = "https://elevation-tiles-prod.s3.amazonaws.com/skadi"
ELEVATION_SAMPLE_INTERVAL_METERS = 50

SNCF_STATIONS_URL = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/gares-de-voyageurs/exports/json?limit=-1"
SNCF_CACHE_DIRECTORY = f"{CACHE_ROOT}/sncf"
SNCF_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days

OSRM_HOST = "http://router.project-osrm.org"
OSRM_BASE_URL = f"{OSRM_HOST}/route/v1/foot"
OSRM_TABLE_URL = f"{OSRM_HOST}/table/v1/foot"
OSRM_CACHE_DIRECTORY = f"{CACHE_ROOT}/osrm"
OSRM_CACHE_TTL_SECONDS = 90 * 24 * 3600  # 90 days
OSRM_COOLDOWN_SECONDS = 1
OSRM_TIMEOUT_SECONDS = 10
