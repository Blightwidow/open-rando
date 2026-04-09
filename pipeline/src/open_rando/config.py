OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = 120
OVERPASS_CACHE_DIRECTORY = "~/.cache/open-rando/overpass"
OVERPASS_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days
OVERPASS_TRAIL_CACHE_TTL_SECONDS = 60 * 24 * 3600  # 60 days
DISCOVERY_CACHE_TTL_SECONDS = 60 * 24 * 3600  # 60 days

OVERPASS_COOLDOWN_SECONDS = 5

MAX_STATION_DISTANCE_METERS = 5000
MAX_STATION_BBOX_DEGREES = 3.0

OUTPUT_DIRECTORY = "~/.local/share/open-rando/data"
GPX_DIRECTORY = "~/.local/share/open-rando/data/gpx"
GEOJSON_DIRECTORY = "~/.local/share/open-rando/data/geojson"
CATALOG_PATH = "~/.local/share/open-rando/data/catalog.json"

WALKING_SPEED_KMH = 4.5

MIN_STEP_DISTANCE_KM = 8
MAX_STEP_DISTANCE_KM = 25

ACCOMMODATION_SEARCH_RADIUS_METERS = 2000

SRTM_CACHE_DIRECTORY = "~/.cache/open-rando/srtm"
SRTM_BASE_URL = "https://elevation-tiles-prod.s3.amazonaws.com/skadi"
ELEVATION_SAMPLE_INTERVAL_METERS = 50
ELEVATION_DIRECTORY = "~/.local/share/open-rando/data/elevation"

SNCF_STATIONS_URL = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/gares-de-voyageurs/exports/json?limit=-1"
SNCF_CACHE_DIRECTORY = "~/.cache/open-rando/sncf"
SNCF_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 days
