#!/usr/bin/env python3
"""Build NYCIF location cache from enriched feed rows that already have GPS.

This is safe/report-supporting only. It does not modify production feeds.

Output:
- data/location_cache.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ENRICHED_PATH = ROOT / "nycif_all_radar_map_events.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def split_ids(value: Any) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def has_gps(row: dict[str, Any]) -> bool:
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def gps_payload(row: dict[str, Any], key_type: str, key_value: str) -> dict[str, Any]:
    lat = float(row.get("lat"))
    lng = float(row.get("lng"))
    title = row.get("title") or row.get("event_name") or ""
    borough = row.get("borough") or row.get("event_borough") or ""
    location = row.get("location") or row.get("display_location") or row.get("event_location") or ""
    return {
        "lat": lat,
        "lng": lng,
        "display_location": location,
        "borough": borough,
        "example_title": title,
        "key_type": key_type,
        "key_value": key_value,
        "confidence": "high" if key_type in {"cemsid", "location"} else "medium",
        "source": "existing_enriched_feed_gps",
        "last_verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def add(cache: dict[str, Any], key: str, payload: dict[str, Any]) -> None:
    if not key or key in cache:
        return
    cache[key] = payload


def main() -> int:
    rows = rows_from_payload(load_json_file(ENRICHED_PATH, []))
    cache: dict[str, Any] = {}
    rows_with_gps = 0

    for row in rows:
        if not has_gps(row):
            continue
        rows_with_gps += 1
        borough = row.get("borough") or row.get("event_borough") or ""
        location = row.get("location") or row.get("display_location") or row.get("event_location") or ""
        event_id = str(row.get("source_event_id") or row.get("event_id") or row.get("id") or "").strip()

        if event_id:
            add(cache, f"event_id:{event_id}", gps_payload(row, "event_id", event_id))

        for cemsid in split_ids(row.get("source_cemsid") or row.get("cemsid")):
            add(cache, f"cemsid:{norm(borough)}:{cemsid}", gps_payload(row, "cemsid", cemsid))

        location_key = f"location:{norm(borough)}:{norm(location)}"
        add(cache, location_key, gps_payload(row, "location", location_key))

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_feed": str(ENRICHED_PATH.name),
        "enriched_rows_loaded": len(rows),
        "enriched_rows_with_gps": rows_with_gps,
        "cache_entry_count": len(cache),
        "entries": cache,
        "production_feeds_modified": False,
    }
    save_json_file(LOCATION_CACHE_PATH, payload)
    print(json.dumps({k: payload[k] for k in payload if k != "entries"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
