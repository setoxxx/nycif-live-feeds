"""NYC Geoclient intersection geocoding with on-disk cache.

Reads NYC_GEOCLIENT_APP_ID and NYC_GEOCLIENT_APP_KEY from the environment.
Optional NYC_GEOCLIENT_BASE_URL (default https://api.nyc.gov/geoclient/v2).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, save_json_file, valid_nyc_lat_lng
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, save_json_file, valid_nyc_lat_lng
    from gps_identity import normalize_text_legacy

GEOCLIENT_CACHE_PATH = DATA_DIR / "nyc_geoclient_cache.json"
DEFAULT_BASE_URL = "https://api.nyc.gov/geoclient/v2"
REQUEST_DELAY_SEC = 0.15

BOROUGH_GEOCLIENT_NAMES = {
    "manhattan": "Manhattan",
    "mn": "Manhattan",
    "brooklyn": "Brooklyn",
    "bk": "Brooklyn",
    "b": "Brooklyn",
    "queens": "Queens",
    "qn": "Queens",
    "q": "Queens",
    "bronx": "Bronx",
    "bx": "Bronx",
    "x": "Bronx",
    "staten island": "Staten Island",
    "si": "Staten Island",
    "r": "Staten Island",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def geoclient_borough_name(borough: Any) -> str | None:
    key = normalize_text_legacy(str(borough or ""))
    if key in BOROUGH_GEOCLIENT_NAMES:
        return BOROUGH_GEOCLIENT_NAMES[key]
    text = str(borough or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in BOROUGH_GEOCLIENT_NAMES:
        return BOROUGH_GEOCLIENT_NAMES[lowered]
    if lowered in {"manhattan", "brooklyn", "queens", "bronx", "staten island"}:
        return text.title() if lowered != "staten island" else "Staten Island"
    return None


def intersection_cache_key(street1: str, street2: str, borough: str) -> str:
    boro = normalize_text_legacy(geoclient_borough_name(borough) or borough)
    return "|".join(
        [
            boro,
            normalize_text_legacy(street1),
            normalize_text_legacy(street2),
        ]
    )


def _credentials() -> tuple[str, str] | None:
    app_id = os.environ.get("NYC_GEOCLIENT_APP_ID", "").strip()
    app_key = os.environ.get("NYC_GEOCLIENT_APP_KEY", "").strip()
    if app_id and app_key:
        return app_id, app_key
    return None


def extract_intersection_lat_lng(payload: dict[str, Any]) -> tuple[float, float] | None:
    section = payload.get("intersection")
    if not isinstance(section, dict):
        section = payload
    lat = section.get("latitude")
    lng = section.get("longitude")
    if lat is None or lng is None:
        lat = section.get("latitudeInternalLabel")
        lng = section.get("longitudeInternalLabel")
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    if valid_nyc_lat_lng(lat_f, lng_f):
        return lat_f, lng_f
    return None


def _geoclient_error(payload: dict[str, Any]) -> str | None:
    section = payload.get("intersection")
    if not isinstance(section, dict):
        section = payload
    message = str(section.get("message") or "").strip()
    return_code = str(section.get("geosupportReturnCode") or section.get("returnCode2w") or "").strip()
    if return_code and return_code not in {"00", "0"}:
        return message or f"Geoclient return code {return_code}"
    if message and re.search(r"not recognized|no match|error", message, flags=re.I):
        return message
    return None


class NYCGeoclientClient:
    def __init__(
        self,
        cache: dict[str, dict[str, Any]],
        *,
        allow_live: bool = False,
        base_url: str | None = None,
    ) -> None:
        self.cache = cache
        self.allow_live = allow_live
        self.base_url = (base_url or os.environ.get("NYC_GEOCLIENT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.live_calls = 0

    @classmethod
    def load_default(cls, *, allow_live: bool = False) -> NYCGeoclientClient:
        payload = load_json_file(GEOCLIENT_CACHE_PATH, {})
        entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        return cls(entries, allow_live=allow_live)

    def save_cache(self) -> None:
        save_json_file(
            GEOCLIENT_CACHE_PATH,
            {
                "artifact_type": "nyc_geoclient_cache",
                "generated_at_utc": utc_now_iso(),
                "entry_count": len(self.cache),
                "entries": self.cache,
                "safety": {
                    "public_map_modified": False,
                    "location_cache_modified": False,
                    "promotion_allowed": False,
                },
            },
        )

    def _live_intersection(
        self,
        street1: str,
        street2: str,
        borough: str,
    ) -> dict[str, Any] | None:
        creds = _credentials()
        if not creds:
            return None
        app_id, app_key = creds
        boro_name = geoclient_borough_name(borough)
        if not boro_name:
            return None
        params = urllib.parse.urlencode(
            {
                "crossStreetOne": street1,
                "crossStreetTwo": street2,
                "borough": boro_name,
                "app_id": app_id,
                "app_key": app_key,
            }
        )
        url = f"{self.base_url}/intersection.json?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "nycif-geoclient-client/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
        self.live_calls += 1
        time.sleep(REQUEST_DELAY_SEC)
        if not isinstance(payload, dict):
            return None
        err = _geoclient_error(payload)
        coords = extract_intersection_lat_lng(payload)
        if err or coords is None:
            return None
        lat, lng = coords
        section = payload.get("intersection") if isinstance(payload.get("intersection"), dict) else payload
        return {
            "lat": lat,
            "lng": lng,
            "street1": street1,
            "street2": street2,
            "borough": boro_name,
            "geocoder_source": "nyc_geoclient_intersection",
            "confidence": "high",
            "confidence_reason": (
                f"NYC Geoclient intersection match for '{street1}' and '{street2}' in {boro_name}."
            ),
            "geoclient_label": section.get("highLowAddressNumberOnStreet") or section.get("firstStreetNameNormalized"),
            "cached_at_utc": utc_now_iso(),
        }

    def resolve_intersection(
        self,
        street1: str,
        street2: str,
        borough: Any,
    ) -> dict[str, Any] | None:
        s1 = str(street1 or "").strip()
        s2 = str(street2 or "").strip()
        if not s1 or not s2:
            return None
        boro_name = geoclient_borough_name(borough)
        if not boro_name:
            return None
        key = intersection_cache_key(s1, s2, boro_name)
        cached = self.cache.get(key)
        if cached and valid_nyc_lat_lng(cached.get("lat"), cached.get("lng")):
            return dict(cached)
        if not self.allow_live:
            return None
        live = self._live_intersection(s1, s2, boro_name)
        if live:
            self.cache[key] = live
        return live
