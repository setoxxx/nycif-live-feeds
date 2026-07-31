"""Source adapters for NYC Event Atlas (evidence → review queue only)."""

from .clearview import fetch_clearview
from .community import fetch_community_sources
from .holidays import fetch_holiday_sources
from .nyc_street_fairs import fetch_nyc_street_fairs
from .parks_bigapps import fetch_parks_bigapps
from .public_calendar import fetch_public_calendar
from .santa_rosalia import fetch_santa_rosalia

ADAPTERS = {
    "parks": fetch_parks_bigapps,
    "public_calendar": fetch_public_calendar,
    "clearview": fetch_clearview,
    "nyc_street_fairs": fetch_nyc_street_fairs,
    "community": fetch_community_sources,
    "holidays": fetch_holiday_sources,
    "santa_rosalia": fetch_santa_rosalia,
}

__all__ = ["ADAPTERS"]
