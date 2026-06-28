#!/usr/bin/env python3
"""Build a safe test enriched feed from NYC Open Data raw rows.

This script creates test outputs only. It does not overwrite production feeds.

Outputs:
- data/nycif_live_test_enriched_events.json
- data/test_enriched_feed_manifest.json
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

RAW_URL = "https://data.cityofnewyork.us/resource/tvpp-9vvx.json"
RAW_PAGE_LIMIT = 50000
MAX_RAW_ROWS = 300000
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ENRICHED_PATH = ROOT / "nycif_all_radar_map_events.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
TEST_FEED_PATH = DATA_DIR / "nycif_live_test_enriched_events.json"
MANIFEST_PATH = DATA_DIR / "test_enriched_feed_manifest.json"
TODAY_UTC = datetime.now(timezone.utc).date().isoformat()


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


def fetch_raw_rows() -> list[dict[str, Any]]:
    """Fetch all available NYC Open Data rows instead of Socrata's default first page."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "$limit": RAW_PAGE_LIMIT,
            "$offset": offset,
            "$order": "start_date_time,event_id",
        }
        url = f"{RAW_URL}?{urlencode(params)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "NYCIF-live-test-feed/1.1"})
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("NYC Open Data response was not a list")
        page_rows = [row for row in payload if isinstance(row, dict)]
        rows.extend(page_rows)
        if len(page_rows) < RAW_PAGE_LIMIT:
            break
        offset += RAW_PAGE_LIMIT
        if offset >= MAX_RAW_ROWS:
            raise RuntimeError(f"NYC Open Data pagination exceeded safety cap: {MAX_RAW_ROWS}")
    return rows


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def location_cache_entries() -> dict[str, dict[str, Any]]:
    payload = load_json_file(LOCATION_CACHE_PATH, {})
    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return {str(k): v for k, v in payload["entries"].items() if isinstance(v, dict)}
    return {}


def date_key(value: Any) -> str:
    text = str(value or "")
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def time_label(value: Any) -> str:
    text = str(value or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}T(\d{2}):(\d{2})", text)
    if not match:
        return "Time TBA"
    hour = int(match.group(1))
    minute = match.group(2)
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute} {suffix}"


def split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def gps_ok(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def gps_from(row: dict[str, Any] | None) -> tuple[float | None, float | None]:
    if not gps_ok(row):
        return None, None
    return float(row.get("lat")), float(row.get("lng"))


def build_indexes(enriched: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_cemsid: dict[str, dict[str, Any]] = {}
    by_text: dict[str, dict[str, Any]] = {}
    for row in enriched:
        event_id = str(row.get("source_event_id") or row.get("event_id") or row.get("id") or "").strip()
        if event_id:
            by_id[event_id] = row
        borough = row.get("borough") or row.get("event_borough") or ""
        for cemsid in split_ids(row.get("source_cemsid") or row.get("cemsid")):
            by_cemsid[f"{norm(borough)}|{cemsid}"] = row
        text_key = "|".join([
            norm(row.get("title") or row.get("event_name")),
            norm(borough),
            norm(row.get("location") or row.get("display_location") or row.get("event_location")),
            date_key(row.get("start_date_time") or row.get("date")),
        ])
        if text_key.replace("|", ""):
            by_text[text_key] = row
    return {"event_id": by_id, "cemsid": by_cemsid, "text": by_text}


def cache_keys(raw: dict[str, Any]) -> list[str]:
    borough = raw.get("event_borough") or raw.get("borough") or ""
    location = raw.get("event_location") or ""
    keys: list[str] = []
    event_id = str(raw.get("event_id") or "").strip()
    if event_id:
        keys.append(f"event_id:{event_id}")
    for cemsid in split_ids(raw.get("cemsid")):
        keys.append(f"cemsid:{norm(borough)}:{cemsid}")
    keys.append(f"location:{norm(borough)}:{norm(location)}")
    return keys


def find_match(raw: dict[str, Any], indexes: dict[str, dict[str, dict[str, Any]]], cache: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    event_id = str(raw.get("event_id") or "").strip()
    if event_id and event_id in indexes["event_id"]:
        return "event_id", indexes["event_id"][event_id]
    borough = raw.get("event_borough") or ""
    for cemsid in split_ids(raw.get("cemsid")):
        hit = indexes["cemsid"].get(f"{norm(borough)}|{cemsid}")
        if hit:
            return "cemsid", hit
    text_key = "|".join([
        norm(raw.get("event_name")),
        norm(borough),
        norm(raw.get("event_location")),
        date_key(raw.get("start_date_time")),
    ])
    if text_key in indexes["text"]:
        return "text_date_location", indexes["text"][text_key]
    for key in cache_keys(raw):
        if key in cache:
            return "location_cache", cache[key]
    return "none", None


def category(raw: dict[str, Any]) -> str:
    text = norm(" ".join([str(raw.get("event_name") or ""), str(raw.get("event_type") or ""), str(raw.get("event_agency") or "")]))
    if any(token in text for token in ["soccer", "baseball", "softball", "basketball", "tennis", "cricket", "football", "volleyball", "sport"]):
        return "sports"
    if any(token in text for token in ["market", "sidewalk sale", "fair", "plaza", "open street", "street activity"]):
        return "market"
    if any(token in text for token in ["movie", "music", "piano", "performance", "dance", "book", "arts"]):
        return "arts"
    if any(token in text for token in ["park", "picnic", "camp", "barbecue", "yoga", "zumba"]):
        return "parks"
    return "general"


def build_event(raw: dict[str, Any], match_type: str, match: dict[str, Any] | None) -> dict[str, Any]:
    lat, lng = gps_from(match)
    location = raw.get("event_location") or "Location TBA"
    title = raw.get("event_name") or "Untitled NYC event"
    start = raw.get("start_date_time")
    end = raw.get("end_date_time")
    needs_review = lat is None or lng is None
    return {
        "id": f"nyc_open_data:tvpp-9vvx:{str(raw.get('event_id') or '').strip()}",
        "title": title,
        "category": category(raw),
        "borough": raw.get("event_borough") or "",
        "location": location,
        "display_location": location,
        "lat": lat,
        "lng": lng,
        "date": date_key(start),
        "start_date_time": start,
        "end_date_time": end,
        "display_time": time_label(start),
        "event_agency": raw.get("event_agency"),
        "event_type": raw.get("event_type"),
        "street_closure_type": raw.get("street_closure_type"),
        "community_board": split_ids(raw.get("community_board")),
        "police_precinct": split_ids(raw.get("police_precinct")),
        "source_dataset": "tvpp-9vvx",
        "source_event_id": str(raw.get("event_id") or "").strip(),
        "source_cemsid": split_ids(raw.get("cemsid")),
        "match_type": match_type,
        "location_source": match_type if not needs_review else "needs_review",
        "needs_review": needs_review,
        "production_feed": False,
    }


def main() -> int:
    raw_rows = fetch_raw_rows()
    raw_current = [row for row in raw_rows if date_key(row.get("start_date_time")) >= TODAY_UTC]
    enriched = rows_from_payload(load_json_file(ENRICHED_PATH, []))
    cache = location_cache_entries()
    indexes = build_indexes(enriched)

    events: list[dict[str, Any]] = []
    match_counts = {"event_id": 0, "cemsid": 0, "text_date_location": 0, "location_cache": 0, "none": 0}
    gps_ready = 0
    needs_review = 0

    for raw in raw_current:
        match_type, match = find_match(raw, indexes, cache)
        match_counts[match_type] += 1
        event = build_event(raw, match_type, match)
        if event["needs_review"]:
            needs_review += 1
        else:
            gps_ready += 1
        events.append(event)

    events.sort(key=lambda row: (row.get("date") or "9999-99-99", row.get("start_date_time") or "", row.get("borough") or "", row.get("title") or ""))

    feed = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset": "tvpp-9vvx",
        "production_feed": False,
        "events": events,
    }
    manifest = {
        "generated_at_utc": feed["generated_at_utc"],
        "source_dataset": "tvpp-9vvx",
        "production_feed": False,
        "raw_page_limit": RAW_PAGE_LIMIT,
        "raw_rows_loaded": len(raw_rows),
        "current_future_rows": len(raw_current),
        "enriched_rows_loaded": len(enriched),
        "location_cache_entries_loaded": len(cache),
        "test_feed_events": len(events),
        "gps_ready_events": gps_ready,
        "needs_review_events": needs_review,
        "match_counts": match_counts,
    }

    save_json_file(TEST_FEED_PATH, feed)
    save_json_file(MANIFEST_PATH, manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
