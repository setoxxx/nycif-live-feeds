#!/usr/bin/env python3
"""NYCIF backend QA sync for NYC Open Data event feed.

This script is intentionally report-only.
It does not overwrite production map feeds.

Outputs:
- data/raw_nyc_open_data_snapshot.json
- data/live_sync_report.json
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAW_URL = "https://data.cityofnewyork.us/resource/tvpp-9vvx.json"
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_SNAPSHOT_PATH = DATA_DIR / "raw_nyc_open_data_snapshot.json"
REPORT_PATH = DATA_DIR / "live_sync_report.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
ENRICHED_PATH = ROOT / "nycif_all_radar_map_events.json"
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
    request = urllib.request.Request(RAW_URL, headers={"Accept": "application/json", "User-Agent": "NYCIF-live-feed-QA/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("NYC Open Data response was not a list")
    return [row for row in payload if isinstance(row, dict)]


def date_key(value: Any) -> str:
    text = str(value or "")
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def has_gps(row: dict[str, Any] | None) -> bool:
    if not row:
        return False
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def enriched_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def load_location_cache() -> dict[str, dict[str, Any]]:
    payload = load_json_file(LOCATION_CACHE_PATH, {})
    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return {str(k): v for k, v in payload["entries"].items() if isinstance(v, dict)}
    return {}


@dataclass
class EnrichedIndex:
    by_event_id: dict[str, dict[str, Any]]
    by_cemsid: dict[str, dict[str, Any]]
    by_text: dict[str, dict[str, Any]]


def build_enriched_index(rows: list[dict[str, Any]]) -> EnrichedIndex:
    by_event_id: dict[str, dict[str, Any]] = {}
    by_cemsid: dict[str, dict[str, Any]] = {}
    by_text: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = str(row.get("source_event_id") or row.get("event_id") or row.get("id") or "").strip()
        if event_id:
            by_event_id[event_id] = row
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
    return EnrichedIndex(by_event_id, by_cemsid, by_text)


def cache_lookup_keys(row: dict[str, Any]) -> list[str]:
    borough = row.get("event_borough") or row.get("borough") or ""
    location = row.get("event_location") or row.get("location") or row.get("display_location") or ""
    keys: list[str] = []
    event_id = str(row.get("event_id") or row.get("source_event_id") or "").strip()
    if event_id:
        keys.append(f"event_id:{event_id}")
    for cemsid in split_ids(row.get("cemsid") or row.get("source_cemsid")):
        keys.append(f"cemsid:{norm(borough)}:{cemsid}")
    keys.append(f"location:{norm(borough)}:{norm(location)}")
    return keys


def classify_raw_row(row: dict[str, Any], index: EnrichedIndex, location_cache: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    event_id = str(row.get("event_id") or "").strip()
    if event_id and event_id in index.by_event_id:
        return "event_id", index.by_event_id[event_id]
    borough = row.get("event_borough") or row.get("borough") or ""
    for cemsid in split_ids(row.get("cemsid")):
        match = index.by_cemsid.get(f"{norm(borough)}|{cemsid}")
        if match:
            return "cemsid", match
    text_key = "|".join([
        norm(row.get("event_name")),
        norm(borough),
        norm(row.get("event_location")),
        date_key(row.get("start_date_time")),
    ])
    if text_key in index.by_text:
        return "text_date_location", index.by_text[text_key]
    for key in cache_lookup_keys(row):
        cached = location_cache.get(key)
        if cached:
            return "location_cache", cached
    return "none", None


def normalize_raw(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_dataset": "tvpp-9vvx",
        "source_event_id": str(row.get("event_id") or "").strip(),
        "source_cemsid": split_ids(row.get("cemsid")),
        "event_name": row.get("event_name"),
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "event_agency": row.get("event_agency"),
        "event_type": row.get("event_type"),
        "event_borough": row.get("event_borough"),
        "event_location": row.get("event_location"),
        "street_closure_type": row.get("street_closure_type"),
        "community_board": split_ids(row.get("community_board")),
        "police_precinct": split_ids(row.get("police_precinct")),
    }


def main() -> int:
    raw_rows = fetch_raw_rows()
    enriched = enriched_rows(load_json_file(ENRICHED_PATH, []))
    location_cache = load_location_cache()
    index = build_enriched_index(enriched)
    current_future = [row for row in raw_rows if date_key(row.get("start_date_time")) >= TODAY_UTC]

    match_counts = {"event_id": 0, "cemsid": 0, "text_date_location": 0, "location_cache": 0, "none": 0}
    matched_with_gps = 0
    matched_without_gps = []
    needs_enrichment = []

    for row in current_future:
        match_type, match = classify_raw_row(row, index, location_cache)
        match_counts[match_type] += 1
        if match is None:
            if len(needs_enrichment) < 25:
                needs_enrichment.append(normalize_raw(row))
        elif has_gps(match):
            matched_with_gps += 1
        elif len(matched_without_gps) < 25:
            matched_without_gps.append(normalize_raw(row))

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_url": RAW_URL,
        "today_utc": TODAY_UTC,
        "raw_rows_loaded": len(raw_rows),
        "current_future_rows": len(current_future),
        "raw_rows_with_cemsid": sum(1 for row in raw_rows if split_ids(row.get("cemsid"))),
        "current_future_rows_with_cemsid": sum(1 for row in current_future if split_ids(row.get("cemsid"))),
        "enriched_rows_loaded": len(enriched),
        "location_cache_entries_loaded": len(location_cache),
        "match_counts": match_counts,
        "matched_with_gps": matched_with_gps,
        "matched_without_gps_sample": matched_without_gps,
        "needs_enrichment_sample": needs_enrichment,
        "production_feeds_modified": False,
    }

    save_json_file(RAW_SNAPSHOT_PATH, [normalize_raw(row) for row in raw_rows])
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
