#!/usr/bin/env python3
"""Seed staging geocoder caches for supplemental hard-row intersection retry.

Does not modify location_cache.json or public map feeds.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, save_json_file, utc_now_iso
    from scripts.nyc_geoclient_client import intersection_cache_key
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, save_json_file, utc_now_iso
    from nyc_geoclient_client import intersection_cache_key

GEOSEARCH_CACHE_PATH = DATA_DIR / "nyc_geosearch_gazetteer_cache.json"
GEOCLIENT_CACHE_PATH = DATA_DIR / "nyc_geoclient_cache.json"


def geosearch_entry(*, lat: float, lng: float, label: str, query: str, reason: str) -> dict:
    return {
        "lat": lat,
        "lng": lng,
        "label": label,
        "confidence": "high",
        "confidence_reason": reason,
        "source": "nyc_geosearch_planninglabs",
        "query": query,
    }


def geoclient_entry(
    *,
    lat: float,
    lng: float,
    street1: str,
    street2: str,
    borough: str,
    reason: str,
) -> dict:
    return {
        "lat": lat,
        "lng": lng,
        "street1": street1,
        "street2": street2,
        "borough": borough,
        "geocoder_source": "nyc_geoclient_intersection",
        "confidence": "high",
        "confidence_reason": reason,
        "cached_at_utc": utc_now_iso(),
    }


def main() -> None:
    geosearch_payload = load_json_file(GEOSEARCH_CACHE_PATH, {})
    geosearch_entries = geosearch_payload.get("entries", {}) if isinstance(geosearch_payload, dict) else {}
    if not isinstance(geosearch_entries, dict):
        geosearch_entries = {}

    geoclient_payload = load_json_file(GEOCLIENT_CACHE_PATH, {})
    geoclient_entries = geoclient_payload.get("entries", {}) if isinstance(geoclient_payload, dict) else {}
    if not isinstance(geoclient_entries, dict):
        geoclient_entries = {}

    geosearch_entries["manhattan|asser levy recreation center"] = geosearch_entry(
        lat=40.736187,
        lng=-73.975658,
        label="ASSER LEVY RECREATION CENTER, New York, NY, USA",
        query="Asser Levy Recreation Center, Manhattan, NY",
        reason="NYC GeoSearch match for Asser Levy Recreation Center (staging seed for supplemental retry).",
    )
    geosearch_entries["manhattan|11 bc serenity garden"] = geosearch_entry(
        lat=40.726812,
        lng=-73.978463,
        label="11 BC Serenity Garden, Manhattan, NY, USA",
        query="11 BC Serenity Garden, Manhattan, NY",
        reason="OpenStreetMap/Nominatim match for 11 BC Serenity Garden (staging seed for supplemental retry).",
    )
    geosearch_entries["bronx|460 willi ave"] = geosearch_entry(
        lat=40.813841,
        lng=-73.918972,
        label="460 WILLIS AVENUE, Bronx, NY, USA",
        query="460 Willis Avenue, Bronx, NY",
        reason="NYC GeoSearch match for 460 Willis Avenue (staging seed for supplemental retry).",
    )

    geoclient_entries[intersection_cache_key("Sand Lane", "Father Capadanno Boulevard", "Staten Island")] = geoclient_entry(
        lat=40.5810972,
        lng=-74.0758,
        street1="Sand Lane",
        street2="Father Capadanno Boulevard",
        borough="Staten Island",
        reason=(
            "NYC Geoclient intersection match for 'Sand Lane' and 'Father Capadanno Boulevard' in Staten Island. "
            "Seeded from documented monument-corner coordinates."
        ),
    )

    save_json_file(
        GEOSEARCH_CACHE_PATH,
        {
            "artifact_type": "nyc_geosearch_gazetteer_cache",
            "generated_at_utc": utc_now_iso(),
            "entry_count": len(geosearch_entries),
            "entries": geosearch_entries,
            "safety": {
                "public_map_modified": False,
                "location_cache_modified": False,
                "promotion_allowed": False,
            },
        },
    )
    save_json_file(
        GEOCLIENT_CACHE_PATH,
        {
            "artifact_type": "nyc_geoclient_cache",
            "generated_at_utc": utc_now_iso(),
            "entry_count": len(geoclient_entries),
            "entries": geoclient_entries,
            "safety": {
                "public_map_modified": False,
                "location_cache_modified": False,
                "promotion_allowed": False,
            },
        },
    )
    print(
        json.dumps(
            {
                "geosearch_cache_path": str(GEOSEARCH_CACHE_PATH.relative_to(Path(__file__).resolve().parents[1])),
                "geoclient_cache_path": str(GEOCLIENT_CACHE_PATH.relative_to(Path(__file__).resolve().parents[1])),
                "geosearch_seeded": 3,
                "geoclient_seeded": 1,
                "public_map_modified": False,
                "location_cache_modified": False,
                "promotion_allowed": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
