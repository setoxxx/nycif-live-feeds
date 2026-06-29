#!/usr/bin/env python3
"""Build and preserve the NYCIF GPS repository.

Purpose:
- Treat GitHub as the durable QA memory for known NYC event coordinates.
- Preserve existing data/location_cache.json entries.
- Add any successful GPS matches from the latest test/staged feeds.
- Write a complete review queue for events still missing usable GPS.

Outputs:
- data/location_cache.json
- data/gps_repository_report.json
- data/gps_needs_review_events.json
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
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
ENRICHED_PATH = ROOT / "nycif_all_radar_map_events.json"
TEST_FEED_PATH = DATA_DIR / "nycif_live_test_enriched_events.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
REPORT_PATH = DATA_DIR / "gps_repository_report.json"
NEEDS_REVIEW_PATH = DATA_DIR / "gps_needs_review_events.json"


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
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def valid_lat_lng(row: dict[str, Any]) -> bool:
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def date_key(row: dict[str, Any]) -> str:
    raw = str(row.get("date") or row.get("start_date_time") or row.get("start") or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def location_text(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or row.get("address") or "").strip()


def borough_text(row: dict[str, Any]) -> str:
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def title_text(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("event_name") or row.get("name") or "").strip()


def source_event_id(row: dict[str, Any]) -> str:
    return str(row.get("source_event_id") or row.get("event_id") or "").strip()


def gps_payload(row: dict[str, Any], key_type: str, key_value: str, source_feed: str) -> dict[str, Any]:
    lat = float(row.get("lat"))
    lng = float(row.get("lng"))
    return {
        "lat": lat,
        "lng": lng,
        "display_location": location_text(row),
        "borough": borough_text(row),
        "example_title": title_text(row),
        "example_date": date_key(row),
        "key_type": key_type,
        "key_value": key_value,
        "confidence": "high" if key_type in {"cemsid", "location", "event_id"} else "medium",
        "source": source_feed,
        "last_verified_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def candidate_keys(row: dict[str, Any]) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    event_id = source_event_id(row)
    borough = borough_text(row)
    location = location_text(row)
    if event_id:
        keys.append((f"event_id:{event_id}", "event_id"))
    for cemsid in split_ids(row.get("source_cemsid") or row.get("cemsid")):
        keys.append((f"cemsid:{norm(borough)}:{cemsid}", "cemsid"))
    if location:
        keys.append((f"location:{norm(borough)}:{norm(location)}", "location"))
    if title_text(row) and location and date_key(row):
        keys.append((f"text_date_location:{norm(title_text(row))}:{norm(borough)}:{norm(location)}:{date_key(row)}", "text_date_location"))
    return keys


def add_entries(cache: dict[str, Any], rows: list[dict[str, Any]], source_feed: str) -> tuple[int, int]:
    rows_with_gps = 0
    added = 0
    for row in rows:
        if not valid_lat_lng(row):
            continue
        rows_with_gps += 1
        for key, key_type in candidate_keys(row):
            if key and key not in cache:
                cache[key] = gps_payload(row, key_type, key, source_feed)
                added += 1
    return rows_with_gps, added


def review_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": title_text(row),
        "date": date_key(row),
        "start_date_time": row.get("start_date_time"),
        "borough": borough_text(row),
        "display_location": location_text(row),
        "source_event_id": source_event_id(row),
        "source_cemsid": split_ids(row.get("source_cemsid") or row.get("cemsid")),
        "event_type": row.get("event_type"),
        "event_agency": row.get("event_agency"),
        "reason": "missing_or_bad_gps",
    }


def main() -> int:
    existing_payload = load_json_file(LOCATION_CACHE_PATH, {})
    existing_entries = existing_payload.get("entries") if isinstance(existing_payload, dict) else {}
    cache: dict[str, Any] = dict(existing_entries) if isinstance(existing_entries, dict) else {}
    starting_entries = len(cache)

    enriched_rows = rows_from_payload(load_json_file(ENRICHED_PATH, []))
    test_rows = rows_from_payload(load_json_file(TEST_FEED_PATH, {}))
    staged_rows = rows_from_payload(load_json_file(STAGED_FEED_PATH, {}))

    enriched_gps, enriched_added = add_entries(cache, enriched_rows, "existing_enriched_feed_gps")
    test_gps, test_added = add_entries(cache, test_rows, "latest_test_feed_gps")
    staged_gps, staged_added = add_entries(cache, staged_rows, "latest_staged_feed_gps")

    needs_review = [review_event(row) for row in test_rows if not valid_lat_lng(row)]
    needs_review.sort(key=lambda row: (row.get("date") or "9999-99-99", row.get("borough") or "", row.get("title") or ""))

    generated_at = datetime.now(timezone.utc).isoformat()
    cache_payload = {
        "generated_at_utc": generated_at,
        "source_feed": "merged_enriched_test_staged_gps_repository",
        "starting_entry_count": starting_entries,
        "cache_entry_count": len(cache),
        "new_entries_added_this_run": len(cache) - starting_entries,
        "entries": cache,
        "production_feeds_modified": False,
    }
    report = {
        "generated_at_utc": generated_at,
        "starting_entry_count": starting_entries,
        "cache_entry_count": len(cache),
        "new_entries_added_this_run": len(cache) - starting_entries,
        "source_rows": {
            "enriched_rows_loaded": len(enriched_rows),
            "enriched_rows_with_gps": enriched_gps,
            "enriched_entries_added": enriched_added,
            "test_rows_loaded": len(test_rows),
            "test_rows_with_gps": test_gps,
            "test_entries_added": test_added,
            "staged_rows_loaded": len(staged_rows),
            "staged_rows_with_gps": staged_gps,
            "staged_entries_added": staged_added,
        },
        "needs_review_count": len(needs_review),
        "needs_review_sample": needs_review[:50],
        "production_feeds_modified": False,
    }

    save_json_file(LOCATION_CACHE_PATH, cache_payload)
    save_json_file(REPORT_PATH, report)
    save_json_file(NEEDS_REVIEW_PATH, {"generated_at_utc": generated_at, "events": needs_review})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
