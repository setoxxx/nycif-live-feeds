#!/usr/bin/env python3
"""Audit public-map GPS quality: clusters, duplicates, borough mismatches.

Reads discovery feed pages and location_cache.json. Writes a staging report only;
does not modify protected feeds or promote coordinates.
"""

from __future__ import annotations

import glob
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DISCOVERY_APPROVED = DATA_DIR / "schema-v1-discovery" / "approved"
DISCOVERY_MAJOR = DATA_DIR / "schema-v1-discovery" / "major" / "events.json"
DISCOVERY_REVIEW = DATA_DIR / "schema-v1-discovery" / "review"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
REPORT_PATH = DATA_DIR / "reports" / "public_map_gps_audit_report.json"

WHITE_ISLAND_LAT = 40.59704
WHITE_ISLAND_LNG = -73.91945
COORD_EPSILON = 1e-4

BOROUGH_BOUNDS = {
    "manhattan": {"lat_min": 40.70, "lat_max": 40.88, "lng_min": -74.02, "lng_max": -73.90},
    "brooklyn": {"lat_min": 40.57, "lat_max": 40.74, "lng_min": -74.05, "lng_max": -73.83},
    "queens": {"lat_min": 40.54, "lat_max": 40.80, "lng_min": -73.96, "lng_max": -73.70},
    "bronx": {"lat_min": 40.79, "lat_max": 40.92, "lng_min": -73.93, "lng_max": -73.75},
    "staten island": {"lat_min": 40.49, "lat_max": 40.65, "lng_min": -74.26, "lng_max": -74.05},
}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def coords_match(lat: Any, lng: Any, target_lat: float, target_lng: float) -> bool:
    try:
        return abs(float(lat) - target_lat) <= COORD_EPSILON and abs(float(lng) - target_lng) <= COORD_EPSILON
    except Exception:
        return False


def norm_borough(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {"bk": "brooklyn", "qn": "queens", "bx": "bronx", "mn": "manhattan", "si": "staten island"}
    return aliases.get(text, text)


def borough_mismatch(borough: Any, lat: Any, lng: Any) -> bool:
    label = norm_borough(borough)
    bounds = BOROUGH_BOUNDS.get(label)
    if not bounds:
        return False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return not (
        bounds["lat_min"] <= lat_f <= bounds["lat_max"]
        and bounds["lng_min"] <= lng_f <= bounds["lng_max"]
    )


def iter_discovery_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for layer_name, base in [("approved", DISCOVERY_APPROVED), ("review", DISCOVERY_REVIEW)]:
        for page_path in sorted(glob.glob(str(base / "pages" / "*.json"))):
            page = load_json(Path(page_path), {})
            for event in page.get("events") or []:
                if isinstance(event, dict):
                    row = dict(event)
                    row["_audit_layer"] = layer_name
                    events.append(row)
    major = load_json(DISCOVERY_MAJOR, {})
    for event in major.get("events") or []:
        if isinstance(event, dict):
            row = dict(event)
            row["_audit_layer"] = "major"
            events.append(row)
    return events


def coord_key(lat: Any, lng: Any) -> str | None:
    try:
        return f"{round(float(lat), 5)},{round(float(lng), 5)}"
    except Exception:
        return None


def audit_discovery(events: list[dict[str, Any]]) -> dict[str, Any]:
    white_island: list[dict[str, Any]] = []
    borough_mismatches: list[dict[str, Any]] = []
    overlap_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    coord_clusters: Counter[str] = Counter()

    for event in events:
        lat = event.get("latitude")
        lng = event.get("longitude")
        if lat is None or lng is None:
            continue
        key = coord_key(lat, lng)
        if not key:
            continue
        coord_clusters[key] += 1
        sample = {
            "id": event.get("id"),
            "title": event.get("title"),
            "borough": event.get("borough"),
            "location": event.get("location"),
            "latitude": lat,
            "longitude": lng,
            "layer": event.get("_audit_layer"),
        }
        if coords_match(lat, lng, WHITE_ISLAND_LAT, WHITE_ISLAND_LNG):
            white_island.append(sample)
        if borough_mismatch(event.get("borough"), lat, lng):
            borough_mismatches.append(sample)
        title = str(event.get("title") or "").strip().lower()
        day = str(event.get("start_date_time") or "")[:10]
        if title and day:
            overlap_index[f"{title}|{day}"].append(sample)

    duplicate_pins = [
        {"overlap_key": key, "count": len(rows), "samples": rows[:5]}
        for key, rows in overlap_index.items()
        if len(rows) > 1
    ]
    duplicate_pins.sort(key=lambda item: item["count"], reverse=True)

    hot_clusters = [
        {"coord_key": key, "event_count": count}
        for key, count in coord_clusters.most_common(25)
        if count >= 10
    ]

    return {
        "event_count_with_coordinates": sum(coord_clusters.values()),
        "white_island_cluster_count": len(white_island),
        "white_island_samples": white_island[:20],
        "borough_mismatch_count": len(borough_mismatches),
        "borough_mismatch_samples": borough_mismatches[:20],
        "duplicate_overlap_key_count": len(duplicate_pins),
        "duplicate_overlap_key_samples": duplicate_pins[:20],
        "hot_coord_clusters": hot_clusters,
    }


def audit_location_cache(entries: dict[str, Any]) -> dict[str, Any]:
    white_island_keys: list[str] = []
    marine_park_white = 0
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        lat = entry.get("lat")
        lng = entry.get("lng")
        if coords_match(lat, lng, WHITE_ISLAND_LAT, WHITE_ISLAND_LNG):
            white_island_keys.append(key)
            if "marine park" in str(entry.get("display_location") or "").lower():
                marine_park_white += 1
    return {
        "cache_entry_count": len(entries),
        "white_island_cache_entry_count": len(white_island_keys),
        "marine_park_white_island_cache_entry_count": marine_park_white,
        "white_island_cache_key_samples": white_island_keys[:20],
    }


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    events = iter_discovery_events()
    discovery = audit_discovery(events)

    cache_payload = load_json(LOCATION_CACHE_PATH, {})
    entries = cache_payload.get("entries") if isinstance(cache_payload, dict) else {}
    cache_audit = audit_location_cache(entries if isinstance(entries, dict) else {})

    report = {
        "artifact_type": "public_map_gps_audit_report",
        "generated_at_utc": generated_at,
        "phase": "public_map_gps_audit",
        "qa_pass": (
            discovery["white_island_cluster_count"] == 0
            and not any(
                "uncle tony" in item.get("overlap_key", "")
                for item in discovery["duplicate_overlap_key_samples"]
            )
        ),
        "discovery": discovery,
        "location_cache": cache_audit,
        "safety": {
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "promotion_allowed": False,
        },
    }
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
