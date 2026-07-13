#!/usr/bin/env python3
"""Build NYC Parks BigApps facility reference for Phase 2C geocoder fill.

Fetches official NYC Parks BigApps JSON feeds and writes a staging reference file.
Does NOT modify location_cache.json, staged feeds, or the public map.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "nyc_parks_facility_reference.json"
REPORT_PATH = DATA_DIR / "reports" / "nyc_parks_facility_reference_report.json"

BASE_URL = "https://www.nycgovparks.org/bigapps"

FACILITY_FEEDS: tuple[tuple[str, str, str], ...] = (
    ("DPR_Playgrounds_001", "playground", "Playgrounds"),
    ("DPR_Tennis_001", "tennis_court", "Tennis"),
    ("DPR_Basketball_001", "basketball_court", "Basketball"),
    ("DPR_Pools_outdoor_001", "outdoor_pool", "Outdoor Pools"),
    ("DPR_Pools_indoor_001", "indoor_pool", "Indoor Pools"),
    ("DPR_Beaches_001", "beach", "Beaches"),
    ("DPR_DogRuns_001", "dog_run", "Dog Runs"),
    ("DPR_RecreationCenter_001", "recreation_center", "Recreation Centers"),
    ("DPR_NatureCenters_001", "nature_center", "Nature Centers"),
    ("DPR_HistoricHouses_001", "historic_house", "Historic Houses"),
    ("DPR_RunningTracks_001", "running_track", "Running Tracks"),
    ("DPR_Handball_001", "handball_court", "Handball"),
    ("DPR_Bocce_001", "bocce_court", "Bocce"),
    ("DPR_Cricket_001", "cricket_field", "Cricket"),
    ("DPR_Barbecue_001", "barbecue_area", "Barbecue"),
    ("DPR_IceSkating_001", "ice_skating", "Ice Skating"),
    ("DPR_Kayak_001", "kayak_launch", "Kayak"),
    ("DPR_Parks_001", "park", "Parks"),
)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def fetch_json(url: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "NYCIF-live-feed-QA/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def pick_name(row: dict[str, Any]) -> str:
    for key in ("Name", "NAME", "name", "facility_name"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def pick_location(row: dict[str, Any]) -> str:
    for key in ("Location", "LOCATION", "ADDRESS", "address", "location"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def pick_borough(row: dict[str, Any]) -> str:
    for key in ("Borough", "BOROUGH", "borough"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def pick_prop_id(row: dict[str, Any]) -> str:
    for key in ("Prop_ID", "prop_id", "Playground_ID"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def normalize_facility(
    row: dict[str, Any],
    *,
    feed_id: str,
    facility_type: str,
    feed_label: str,
) -> dict[str, Any] | None:
    name = pick_name(row)
    location = pick_location(row)
    if not name and not location:
        return None

    lat = row.get("lat") or row.get("latitude") or row.get("Latitude")
    lng = row.get("lon") or row.get("lng") or row.get("longitude") or row.get("Longitude")
    has_coords = valid_nyc_lat_lng(lat, lng)

    display_location = name
    if location and location not in name:
        display_location = f"{name}: {location}" if name else location

    prop_id = pick_prop_id(row)
    facility_id = f"{feed_id}:{prop_id or name or location}".replace(" ", "_")

    entry: dict[str, Any] = {
        "id": facility_id,
        "facility_name": name or None,
        "name": name or None,
        "place_name": name or None,
        "display_location": display_location,
        "location_text": location or None,
        "borough": pick_borough(row) or None,
        "prop_id": prop_id or None,
        "facility_type": facility_type,
        "feed_id": feed_id,
        "feed_label": feed_label,
        "source": "nyc_parks_bigapps",
        "geocoder_source": "nyc_parks_bigapps",
        "confidence": "high" if has_coords else "reference_only",
        "confidence_reason": (
            "Official NYC Parks BigApps facility feed with published coordinates."
            if has_coords
            else "Official NYC Parks BigApps facility name/location reference without coordinates."
        ),
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    if has_coords:
        entry["lat"] = float(lat)
        entry["lng"] = float(lng)
    return entry


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    facilities: list[dict[str, Any]] = []
    feed_stats: list[dict[str, Any]] = []
    errors: list[str] = []

    for feed_id, facility_type, feed_label in FACILITY_FEEDS:
        url = f"{BASE_URL}/{feed_id}.json"
        try:
            rows = fetch_json(url)
        except Exception as exc:
            errors.append(f"{feed_id}: {exc}")
            feed_stats.append(
                {
                    "feed_id": feed_id,
                    "feed_label": feed_label,
                    "url": url,
                    "rows_loaded": 0,
                    "with_coordinates": 0,
                    "error": str(exc),
                }
            )
            continue

        with_coords = 0
        for row in rows:
            entry = normalize_facility(
                row,
                feed_id=feed_id,
                facility_type=facility_type,
                feed_label=feed_label,
            )
            if entry is None:
                continue
            if entry.get("lat") is not None:
                with_coords += 1
            facilities.append(entry)

        feed_stats.append(
            {
                "feed_id": feed_id,
                "feed_label": feed_label,
                "url": url,
                "rows_loaded": len(rows),
                "reference_rows_written": sum(
                    1
                    for entry in facilities
                    if entry.get("feed_id") == feed_id
                ),
                "with_coordinates": with_coords,
            }
        )

    with_coordinates = sum(1 for entry in facilities if entry.get("lat") is not None)
    payload = {
        "generated_at_utc": generated_at,
        "source": "https://www.nycgovparks.org/bigapps",
        "artifact_type": "nyc_parks_facility_reference",
        "facilities": facilities,
        "safety": {
            "production_feeds_modified": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
        },
    }
    report = {
        "generated_at_utc": generated_at,
        "qa_pass": bool(facilities) and with_coordinates > 0,
        "facility_feeds_requested": len(FACILITY_FEEDS),
        "facility_feeds_loaded": sum(1 for stat in feed_stats if stat.get("rows_loaded")),
        "reference_rows_total": len(facilities),
        "reference_rows_with_coordinates": with_coordinates,
        "feed_stats": feed_stats,
        "errors": errors,
        "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
    }

    save_json(OUTPUT_PATH, payload)
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
