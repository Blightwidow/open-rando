"""OSM tag values shared by the Overpass queries and the local extract index.

Both paths must select the same features, so the tag vocabulary lives here
rather than in either fetcher.
"""

from __future__ import annotations

HISTORIC_LANDMARK_KINDS = (
    "castle",
    "monument",
    "ruins",
    "memorial",
    "archaeological_site",
    "fort",
    "tower",
    "wayside_cross",
)
TOURISM_LANDMARK_KINDS = ("attraction", "viewpoint")
NATURAL_LANDMARK_KINDS = ("peak", "cliff", "cave_entrance", "waterfall")
MAN_MADE_LANDMARK_KINDS = ("lighthouse", "tower")

LANDMARK_KINDS_BY_KEY = (
    ("historic", HISTORIC_LANDMARK_KINDS),
    ("tourism", TOURISM_LANDMARK_KINDS),
    ("natural", NATURAL_LANDMARK_KINDS),
    ("man_made", MAN_MADE_LANDMARK_KINDS),
)

ACCOMMODATION_KINDS = ("hotel", "guest_house", "hostel", "camp_site")
FOREST_TAGS = (("landuse", "forest"), ("natural", "wood"))
TRAIL_ROUTE_VALUES = ("hiking", "foot")
