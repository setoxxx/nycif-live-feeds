#!/usr/bin/env python3
"""Build staging recreation-center -> park/coordinate aliases for supplemental pin QA.

Sources (in order):
1. nyc_parks_facility_reference.json recreation_center rows (address text)
2. NYC Planning GeoSearch for official addresses
3. Optional parks_properties_signname when a related park polygon exists

Does not modify location_cache.json or public map feeds.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, save_json_file, utc_now_iso, valid_nyc_lat_lng
    from scripts.geojson_polygon_utils import build_parks_properties_name_index, find_park_property_row, normalize_park_name
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, save_json_file, utc_now_iso, valid_nyc_lat_lng
    from geojson_polygon_utils import build_parks_properties_name_index, find_park_property_row, normalize_park_name
    from gps_identity import normalize_text_legacy

OUTPUT_PATH = DATA_DIR / "supplemental_recreation_center_park_aliases.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_recreation_center_park_aliases_report.json"
FACILITY_PATH = DATA_DIR / "nyc_parks_facility_reference.json"
PARKS_PROPERTIES_PATH = DATA_DIR / "nyc_parks_properties_reference.json"
GEOSEARCH_BASE = "https://geosearch.planninglabs.nyc/v2/search"

# Parents flagged by supplemental pin-quality review (no polygon match / outside polygon).
TARGET_ALIASES: list[dict[str, str]] = [
    {
        "alias": "Shirley Chisholm Recreation Center",
        "borough": "Bk",
        "address": "3105 Farragut Place, Brooklyn, NY",
        "parks_properties_signname": None,
    },
    {
        "alias": "St. John's Recreation Center",
        "borough": "Bk",
        "address": "1251 Prospect Place, Brooklyn, NY",
        "parks_properties_signname": "St. John's Park",
    },
    {
        "alias": "Al Oerter Recreation Center",
        "borough": "Qn",
        "address": "131-40 Fowler Avenue, Queens, NY",
        "parks_properties_signname": None,
    },
    {
        "alias": "Fort Hamilton Senior Recreation Center",
        "borough": "Bk",
        "address": "9941 Fort Hamilton Parkway, Brooklyn, NY",
        "parks_properties_signname": "Fort Hamilton Athletic Field",
    },
    {
        "alias": "Jackie Robinson Recreation Center",
        "borough": "Mn",
        "address": "85 Bradhurst Avenue, Manhattan, NY",
        "parks_properties_signname": "Jackie Robinson Park",
    },
    {
        "alias": "Fort Totten Park",
        "borough": "Qn",
        "address": "Fort Totten Park entrance, Queens, NY",
        "parks_properties_signname": "Fort Totten Park",
    },
]


def clean_alias_name(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def alias_key(alias: str, borough: str) -> str:
    return f"{normalize_text_legacy(borough)}|{normalize_park_name(clean_alias_name(alias))}"


def geosearch_address(query: str) -> dict[str, Any] | None:
    params = urllib.parse.urlencode({"text": query, "size": 1})
    url = f"{GEOSEARCH_BASE}?{params}"
    request = urllib.request.Request(url, headers={"User-Agent": "nycif-supplemental-rc-alias-builder/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    time.sleep(0.15)
    features = payload.get("features") or []
    if not features:
        return None
    feature = features[0]
    coords = (feature.get("geometry") or {}).get("coordinates") or []
    if len(coords) != 2:
        return None
    lng, lat = float(coords[0]), float(coords[1])
    if not valid_nyc_lat_lng(lat, lng):
        return None
    props = feature.get("properties") or {}
    return {
        "facility_lat": lat,
        "facility_lng": lng,
        "geocoder_label": props.get("label") or props.get("name"),
        "geocoder_source": "nyc_geosearch_planninglabs",
        "confidence": "high",
        "confidence_reason": f"NYC GeoSearch address match for recreation center alias ({query}).",
        "address_query": query,
    }


def load_facility_address_index() -> dict[str, str]:
    payload = load_json_file(FACILITY_PATH, {})
    facilities = payload.get("facilities", payload) if isinstance(payload, dict) else payload
    index: dict[str, str] = {}
    if not isinstance(facilities, list):
        return index
    for row in facilities:
        if not isinstance(row, dict):
            continue
        if str(row.get("facility_type") or "") != "recreation_center":
            continue
        name = clean_alias_name(str(row.get("facility_name") or row.get("name") or ""))
        address = str(row.get("location_text") or "").strip()
        if name and address and name not in index:
            index[name] = address
    return index


def main() -> int:
    facility_addresses = load_facility_address_index()
    parks_properties = load_json_file(PARKS_PROPERTIES_PATH, {}).get("properties", [])
    parks_index = build_parks_properties_name_index(parks_properties if isinstance(parks_properties, list) else [])
    entries: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for target in TARGET_ALIASES:
        alias = clean_alias_name(target["alias"])
        borough = target["borough"]
        address = target.get("address") or facility_addresses.get(alias) or ""
        if not address:
            errors.append(f"Missing address for alias: {alias}")
            continue
        geocoded = geosearch_address(address)
        if not geocoded:
            errors.append(f"GeoSearch failed for alias: {alias}")
            continue
        signname = target.get("parks_properties_signname")
        parks_row = None
        if signname:
            parks_row = find_park_property_row(signname, borough, parks_index)
        entry = {
            "alias": alias,
            "borough": borough,
            "normalized_alias": normalize_park_name(alias),
            "parks_properties_signname": signname,
            "parks_properties_matched": bool(parks_row),
            "facility_lat": geocoded["facility_lat"],
            "facility_lng": geocoded["facility_lng"],
            "geocoder_label": geocoded.get("geocoder_label"),
            "geocoder_source": geocoded["geocoder_source"],
            "confidence": geocoded["confidence"],
            "confidence_reason": geocoded["confidence_reason"],
            "address_query": address,
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
        }
        entries[alias_key(alias, borough)] = entry

    payload = {
        "artifact_type": "supplemental_recreation_center_park_aliases",
        "generated_at_utc": utc_now_iso(),
        "entry_count": len(entries),
        "entries": entries,
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
        },
    }
    save_json_file(OUTPUT_PATH, payload)
    report = {
        "generated_at_utc": payload["generated_at_utc"],
        "artifact_type": "supplemental_recreation_center_park_aliases_report",
        "entry_count": len(entries),
        "errors": errors,
        "passed": not errors,
        "output_path": str(OUTPUT_PATH.relative_to(DATA_DIR.parent)),
        "public_map_modified": False,
        "location_cache_modified": False,
        "promotion_allowed": False,
    }
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
