#!/usr/bin/env python3
"""Fetch current NYC Parks public events from NYC Open Data.

The Parks website JSON URL now rejects unattended GETs with HTTP 405. NYC Open
Data dataset ``w3wp-dpdi`` mirrors the current upcoming-14-days Parks feed and
exposes the same event schema, including first-party coordinate pairs.

This collector never geocodes. A valid coordinate from the official dataset is
carried as validated ``exact_source_coordinate`` evidence. Missing/invalid
coordinates remain non-exact for downstream review/list-only handling.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
REPORT_PATH = DATA_DIR / "nyc_parks_bigapps_events_sync_report.json"

DATASET_ID = "w3wp-dpdi"
EVENTS_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
SOURCE_PAGE = f"https://data.cityofnewyork.us/d/{DATASET_ID}"
PAGE_LIMIT = 50000
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NYCIF-live-feeds/2.0 (+https://nycinfocus.com/)",
}


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def text(value: Any) -> str:
    return str(value or "").strip()


def fetch_events() -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"$limit": str(PAGE_LIMIT)})
    request = urllib.request.Request(f"{EVENTS_URL}?{query}", headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("NYC Parks current-events dataset returned a non-list payload")
    rows = [row for row in payload if isinstance(row, dict)]
    if not rows:
        raise RuntimeError("NYC Parks current-events dataset returned no rows")
    return rows


def parse_coordinates(value: Any) -> tuple[float | None, float | None]:
    raw = text(value)
    if not raw or "," not in raw:
        return None, None
    pieces = [piece.strip() for piece in raw.split(",", 1)]
    try:
        lat, lng = float(pieces[0]), float(pieces[1])
    except (TypeError, ValueError):
        return None, None
    if not (40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0):
        return None, None
    return lat, lng


def date_part(value: Any) -> str:
    raw = text(value)
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        return raw[:10]
    return ""


def time_part(value: Any) -> str:
    raw = text(value)
    if not raw:
        return ""
    # Current Open Data values are e.g. "2026-08-07 07:00:00".
    if " " in raw:
        raw = raw.rsplit(" ", 1)[-1]
    if "T" in raw:
        raw = raw.rsplit("T", 1)[-1]
    return raw[:8]


def combine(day: str, clock: str) -> str | None:
    return f"{day}T{clock or '00:00:00'}" if day else None


def category_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text(item) for item in value if text(item)]
    raw = text(value)
    if not raw:
        return []
    delimiter = "|" if "|" in raw else ","
    return [piece.strip() for piece in raw.split(delimiter) if piece.strip()]


def link_value(value: Any) -> str | None:
    if isinstance(value, dict):
        return text(value.get("url")) or None
    return text(value) or None


def official_coordinate_evidence(lat: float | None, lng: float | None) -> dict[str, Any] | None:
    if lat is None or lng is None:
        return None
    return {
        "tier": "exact_source_coordinate",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": EVENTS_URL,
        "provider": "NYC Parks / NYC Open Data",
        "reason_code": "OFFICIAL_SOURCE_COORDINATE",
        "reason_detail": "Coordinate pair supplied directly by NYC Parks current-events Open Data.",
    }


def normalize_event_item(item: dict[str, Any]) -> dict[str, Any]:
    lat, lng = parse_coordinates(item.get("coordinates"))
    start_day = date_part(item.get("startdate"))
    end_day = date_part(item.get("enddate")) or start_day
    start_clock = time_part(item.get("starttime"))
    end_clock = time_part(item.get("endtime"))
    park_name = text(item.get("parknames"))
    location = text(item.get("location")) or park_name

    return {
        "source_dataset": "nyc-parks-bigapps-events",
        "source_event_id": text(item.get("guid")),
        "title": item.get("title"),
        "start_date_time": combine(start_day, start_clock),
        "end_date_time": combine(end_day, end_clock),
        "start_date": start_day or None,
        "start_time": start_clock or None,
        "end_date": end_day or None,
        "end_time": end_clock or None,
        "location": location or None,
        "display_location": location or None,
        "park_names": [park_name] if park_name else [],
        "park_ids": item.get("parkids"),
        "categories": category_list(item.get("categories")),
        "description": item.get("description"),
        "link": link_value(item.get("link")),
        "registration_url": link_value(item.get("registration_url")),
        "registration_description": item.get("registration_description"),
        "contact_phone": item.get("contact_phone"),
        "instructor": item.get("instructor"),
        "image": link_value(item.get("image")),
        "lat": lat,
        "lng": lng,
        "location_evidence": official_coordinate_evidence(lat, lng),
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    error: str | None = None
    try:
        source_rows = fetch_events()
        normalized = [normalize_event_item(row) for row in source_rows]
        fetch_mode = "live"
    except Exception as exc:
        source_rows = []
        normalized = []
        fetch_mode = "live_fetch_failed"
        error = str(exc)

    today = date.today().isoformat()
    normalized = [
        row for row in normalized
        if row.get("source_event_id") and row.get("title") and row.get("start_date_time")
    ]
    current_future = [row for row in normalized if text(row.get("start_date_time"))[:10] >= today]
    with_coords = sum(1 for row in normalized if row.get("lat") is not None and row.get("lng") is not None)
    with_exact_source_evidence = sum(
        1
        for row in normalized
        if isinstance(row.get("location_evidence"), dict)
        and row["location_evidence"].get("exact_pin_eligible") is True
    )
    qa_pass = (
        bool(current_future)
        and not error
        and with_exact_source_evidence == with_coords
    )

    snapshot = {
        "generated_at_utc": generated_at,
        "source_url": EVENTS_URL,
        "source_page": SOURCE_PAGE,
        "source_transport": "nyc_open_data_current_14_day",
        "fetch_mode": fetch_mode,
        "events": normalized,
    }
    report = {
        "generated_at_utc": generated_at,
        "qa_pass": qa_pass,
        "fetch_mode": fetch_mode,
        "source_transport": "nyc_open_data_current_14_day",
        "source_url": EVENTS_URL,
        "source_page": SOURCE_PAGE,
        "source_rows_received": len(source_rows),
        "snapshot_rows": len(normalized),
        "current_future_rows": len(current_future),
        "rows_with_coordinates": with_coords,
        "rows_with_exact_source_coordinate_evidence": with_exact_source_evidence,
        "coordinate_evidence_parity": with_exact_source_evidence == with_coords,
        "error": error,
        "live_fetch_error": error,
        "production_feeds_modified": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
    }

    save_json(SNAPSHOT_PATH, snapshot)
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
