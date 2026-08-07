#!/usr/bin/env python3
"""Fetch NYC Parks BigApps public events feed (staging only).

Source: https://www.nycgovparks.org/xml/events_300_rss.json
Does NOT modify protected feeds or publish to the public map.

When Parks supplies a valid coordinate pair, the normalized row preserves that
first-party evidence explicitly. The coordinate is not re-geocoded or inferred;
downstream semantic authority still decides whether the event is publishable.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
REPORT_PATH = DATA_DIR / "nyc_parks_bigapps_events_sync_report.json"

EVENTS_URL = "https://www.nycgovparks.org/xml/events_300_rss.json"
DEFAULT_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": (
        "Mozilla/5.0 (compatible; NYCIF-live-feeds/1.0; "
        "+https://github.com/setoxxx/nycif-live-feeds)"
    ),
}


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def parse_coordinates(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "").strip()
    if not text or "," not in text:
        return None, None
    parts = [part.strip() for part in text.split(",", 1)]
    if len(parts) != 2:
        return None, None
    try:
        lat = float(parts[0])
        lng = float(parts[1])
    except Exception:
        return None, None
    if not (40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0):
        return None, None
    return lat, lng


def official_coordinate_evidence(lat: float | None, lng: float | None) -> dict[str, Any] | None:
    if lat is None or lng is None:
        return None
    return {
        "tier": "exact_source_coordinate",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": EVENTS_URL,
        "provider": "NYC Parks BigApps",
        "reason_code": "OFFICIAL_SOURCE_COORDINATE",
        "reason_detail": "Coordinate pair supplied directly by the NYC Parks BigApps event feed.",
    }


def normalize_event_item(item: dict[str, Any]) -> dict[str, Any]:
    lat, lng = parse_coordinates(item.get("coordinates"))
    start_date = str(item.get("startdate") or item.get("start_date") or "").strip()
    start_time = str(item.get("starttime") or item.get("start_time") or "").strip()
    end_date = str(item.get("enddate") or item.get("end_date") or "").strip()
    end_time = str(item.get("endtime") or item.get("end_time") or "").strip()
    start_date_time = start_date
    if start_date and start_time:
        start_date_time = f"{start_date}T{start_time}"
    end_date_time = end_date
    if end_date and end_time:
        end_date_time = f"{end_date}T{end_time}"

    park_names = item.get("parknames")
    if isinstance(park_names, list):
        park_name_list = [str(p).strip() for p in park_names if str(p).strip()]
    elif park_names:
        park_name_list = [str(park_names).strip()]
    else:
        park_name_list = []

    categories = item.get("categories")
    if isinstance(categories, list):
        category_list = [str(c).strip() for c in categories if str(c).strip()]
    elif categories:
        category_list = [str(categories).strip()]
    else:
        category_list = []

    return {
        "source_dataset": "nyc-parks-bigapps-events",
        "source_event_id": str(item.get("guid") or item.get("id") or "").strip(),
        "title": item.get("title"),
        "start_date_time": start_date_time or None,
        "end_date_time": end_date_time or None,
        "start_date": start_date or None,
        "start_time": start_time or None,
        "end_date": end_date or None,
        "end_time": end_time or None,
        "location": item.get("location"),
        "display_location": item.get("location"),
        "park_names": park_name_list,
        "park_ids": item.get("parkids"),
        "categories": category_list,
        "description": item.get("description"),
        "link": item.get("link"),
        "registration_url": item.get("registration_url"),
        "registration_description": item.get("registration_description"),
        "contact_phone": item.get("contact_phone"),
        "instructor": item.get("instructor"),
        "image": item.get("image"),
        "lat": lat,
        "lng": lng,
        "location_evidence": official_coordinate_evidence(lat, lng),
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def fetch_events() -> list[dict[str, Any]]:
    request = urllib.request.Request(EVENTS_URL, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("channel", {}).get("item") or payload.get("items") or []
        if isinstance(rows, dict):
            rows = [rows]
    else:
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def load_committed_snapshot_events() -> list[dict[str, Any]]:
    payload = load_json_file(SNAPSHOT_PATH, {})
    events = payload.get("events") if isinstance(payload, dict) else []
    if not isinstance(events, list):
        return []
    return [row for row in events if isinstance(row, dict)]


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    fetch_mode = "live"
    live_fetch_error = None
    normalized: list[dict[str, Any]] = []

    try:
        raw_items = fetch_events()
        normalized = [normalize_event_item(item) for item in raw_items]
    except Exception as exc:
        live_fetch_error = str(exc)
        committed_rows = load_committed_snapshot_events()
        if committed_rows:
            normalized = committed_rows
            fetch_mode = "committed_snapshot_fallback"
        else:
            fetch_mode = "live_fetch_failed"

    try:
        current_future = [
            row
            for row in normalized
            if str(row.get("start_date_time") or row.get("start_date") or "")[:10] >= today
        ]
        with_coords = sum(1 for row in normalized if row.get("lat") is not None)
        with_exact_source_evidence = sum(
            1
            for row in normalized
            if isinstance(row.get("location_evidence"), dict)
            and row["location_evidence"].get("exact_pin_eligible") is True
        )
        qa_pass = bool(normalized)
        error = live_fetch_error if fetch_mode != "live" else None
    except Exception as exc:
        current_future = []
        with_coords = 0
        with_exact_source_evidence = 0
        qa_pass = False
        error = str(exc)
        fetch_mode = "processing_failed"

    snapshot = {
        "generated_at_utc": generated_at,
        "source_url": EVENTS_URL,
        "source_page": "https://www.nycgovparks.org/bigapps",
        "fetch_mode": fetch_mode,
        "events": normalized,
    }
    report = {
        "generated_at_utc": generated_at,
        "qa_pass": qa_pass,
        "fetch_mode": fetch_mode,
        "source_url": EVENTS_URL,
        "snapshot_rows": len(normalized),
        "current_future_rows": len(current_future),
        "rows_with_coordinates": with_coords,
        "rows_with_exact_source_coordinate_evidence": with_exact_source_evidence,
        "coordinate_evidence_parity": with_exact_source_evidence == with_coords,
        "error": error,
        "live_fetch_error": live_fetch_error,
        "production_feeds_modified": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
    }

    save_json(SNAPSHOT_PATH, snapshot)
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if qa_pass and report["coordinate_evidence_parity"] else 1


if __name__ == "__main__":
    sys.exit(main())
