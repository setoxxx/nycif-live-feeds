#!/usr/bin/env python3
"""Fetch the official NYC Parks Events Open Data tables (staging only).

This keeps the historical NYCIF Parks artifact paths stable while replacing the
legacy BigApps JSON endpoint as freshness authority. NYC Open Data documents
`fudw-fgrp` as the primary event table and the related tables as exact
`event_id` joins. No fuzzy joins, geocoding, promotion, or public-map writes are
performed here.

Outputs:
- data/nyc_parks_bigapps_events_snapshot.json
- data/nyc_parks_bigapps_events_sync_report.json
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
REPORT_PATH = DATA_DIR / "nyc_parks_bigapps_events_sync_report.json"

SOURCE_CONTRACT_VERSION = "NYCIF_PARKS_EVENTS_OPEN_DATA_V2"
EVENTS_DATASET_ID = "fudw-fgrp"
LOCATIONS_DATASET_ID = "cpcm-i88g"
CATEGORIES_DATASET_ID = "xtsw-fqvh"
SOCRATA_ROOT = "https://data.cityofnewyork.us/resource"
EVENTS_URL = f"{SOCRATA_ROOT}/{EVENTS_DATASET_ID}.json"
LOCATIONS_URL = f"{SOCRATA_ROOT}/{LOCATIONS_DATASET_ID}.json"
CATEGORIES_URL = f"{SOCRATA_ROOT}/{CATEGORIES_DATASET_ID}.json"
LEGACY_BIGAPPS_URL = "https://www.nycgovparks.org/xml/events_300_rss.json"
PAGE_LIMIT = 50000
MAX_ROWS_PER_TABLE = 500000
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NYCIF-live-feeds/2.0 (+https://github.com/setoxxx/nycif-live-feeds)",
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


def first_value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def fetch_socrata_rows(dataset_id: str, *, order_field: str = "event_id") -> list[dict[str, Any]]:
    """Fetch a complete Socrata table with explicit pagination."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"$limit": PAGE_LIMIT, "$offset": offset, "$order": order_field}
        url = f"{SOCRATA_ROOT}/{dataset_id}.json?{urlencode(params)}"
        request = urllib.request.Request(url, headers=DEFAULT_HEADERS, method="GET")
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 200:
                raise RuntimeError(f"{dataset_id} returned HTTP {response.status}")
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError(f"{dataset_id} response was not a JSON list")
        page = [row for row in payload if isinstance(row, dict)]
        rows.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        if offset >= MAX_ROWS_PER_TABLE:
            raise RuntimeError(f"{dataset_id} pagination exceeded safety cap {MAX_ROWS_PER_TABLE}")
    return rows


def iso_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        return match.group(1)
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text.split("T", 1)[0].split(" ", 1)[0], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def iso_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        text = text.split("T", 1)[1]
    text = text.rstrip("Z")
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    match = re.match(r"^(\d{2}:\d{2})(?::(\d{2}))?", text)
    if match:
        return match.group(1) + ":" + (match.group(2) or "00")
    return ""


def combine_date_time(day_value: Any, time_value: Any) -> str | None:
    day = iso_date(day_value)
    if not day:
        return None
    clock = iso_time(time_value)
    return f"{day}T{clock}" if clock else day


def parse_point(row: dict[str, Any]) -> tuple[float, float] | None:
    lat_value = first_value(row, "lat", "latitude")
    lng_value = first_value(row, "long", "lng", "lon", "longitude")
    try:
        lat, lng = float(lat_value), float(lng_value)
    except (TypeError, ValueError):
        return None
    if not (40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0):
        return None
    return round(lat, 7), round(lng, 7)


def event_id(row: dict[str, Any]) -> str:
    return str(first_value(row, "event_id", "eventid", "id") or "").strip()


def related_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = event_id(row)
        if key:
            out[key].append(row)
    return dict(out)


def unique_text(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def category_name(row: dict[str, Any]) -> str:
    return str(first_value(row, "category", "name", "category_name", "title") or "").strip()


def normalize_event_item(
    item: dict[str, Any],
    locations: list[dict[str, Any]],
    categories: list[dict[str, Any]],
) -> dict[str, Any]:
    sid = event_id(item)
    raw_date = first_value(item, "date", "start_date", "startdate", "start_date_time")
    raw_start_time = first_value(item, "start_time", "starttime")
    raw_end_date = first_value(item, "end_date", "enddate", "end_date_time") or raw_date
    raw_end_time = first_value(item, "end_time", "endtime")
    start_date = iso_date(raw_date)
    end_date = iso_date(raw_end_date) or start_date
    start_date_time = combine_date_time(raw_date, raw_start_time)
    end_date_time = combine_date_time(raw_end_date, raw_end_time)

    points = sorted({point for row in locations if (point := parse_point(row)) is not None})
    chosen_point = points[0] if len(points) == 1 else None
    location_names = unique_text([first_value(row, "name", "location", "location_name") for row in locations])
    addresses = unique_text([row.get("address") for row in locations])
    park_ids = unique_text([first_value(row, "park_id", "parkid") for row in locations])
    boroughs = unique_text([row.get("borough") for row in locations])
    location_text = str(first_value(item, "location", "location_text", "park_name") or "").strip()
    if not location_text:
        location_text = "; ".join(location_names or addresses)

    category_values = unique_text([category_name(row) for row in categories])
    item_category = first_value(item, "category", "event_type")
    if item_category:
        category_values = unique_text(category_values + [item_category])

    lat = chosen_point[0] if chosen_point else None
    lng = chosen_point[1] if chosen_point else None
    coordinate_state = (
        "single_source_location_point"
        if len(points) == 1
        else "multiple_source_location_points"
        if len(points) > 1
        else "no_source_location_point"
    )

    return {
        # Preserve the legacy logical source namespace so event identity does not
        # churn solely because the transport changed. Provenance below records
        # the official replacement datasets precisely.
        "source_dataset": "nyc-parks-bigapps-events",
        "source_event_id": sid,
        "source_authority_dataset": EVENTS_DATASET_ID,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "title": first_value(item, "title", "name", "event_name"),
        "event_type": first_value(item, "event_type", "type"),
        "start_date_time": start_date_time,
        "end_date_time": end_date_time,
        "start_date": start_date or None,
        "start_time": iso_time(raw_start_time) or None,
        "end_date": end_date or None,
        "end_time": iso_time(raw_end_time) or None,
        "location": location_text or None,
        "display_location": location_text or None,
        "park_names": location_names,
        "park_ids": park_ids,
        "borough": first_value(item, "borough") or (boroughs[0] if len(boroughs) == 1 else None),
        "categories": category_values,
        "description": first_value(item, "description", "desc"),
        "link": first_value(item, "link", "url", "source_url"),
        "registration_url": first_value(item, "registration_url"),
        "registration_description": first_value(item, "registration_description"),
        "contact_phone": first_value(item, "contact_phone", "phone"),
        "instructor": first_value(item, "instructor"),
        "image": first_value(item, "image", "image_url"),
        "lat": lat,
        "lng": lng,
        "source_location_count": len(locations),
        "source_coordinate_count": len(points),
        "source_coordinate_state": coordinate_state,
        "source_locations": [
            {
                "name": first_value(row, "name", "location", "location_name"),
                "park_id": first_value(row, "park_id", "parkid"),
                "lat": parse_point(row)[0] if parse_point(row) else None,
                "lng": parse_point(row)[1] if parse_point(row) else None,
                "address": row.get("address"),
                "zip": row.get("zip"),
                "borough": row.get("borough"),
            }
            for row in locations
        ],
        "provenance": {
            "events_dataset_id": EVENTS_DATASET_ID,
            "locations_dataset_id": LOCATIONS_DATASET_ID,
            "categories_dataset_id": CATEGORIES_DATASET_ID,
            "join_key": "event_id",
            "legacy_endpoint_retired_from_freshness_authority": LEGACY_BIGAPPS_URL,
        },
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def load_committed_snapshot_events() -> list[dict[str, Any]]:
    payload = load_json_file(SNAPSHOT_PATH, {})
    events = payload.get("events") if isinstance(payload, dict) else []
    if not isinstance(events, list):
        return []
    return [row for row in events if isinstance(row, dict)]


def fetch_official_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        fetch_socrata_rows(EVENTS_DATASET_ID),
        fetch_socrata_rows(LOCATIONS_DATASET_ID),
        fetch_socrata_rows(CATEGORIES_DATASET_ID),
    )


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()
    fetch_mode = "live"
    live_fetch_error = None
    source_event_rows = source_location_rows = source_category_rows = 0
    duplicate_source_event_ids: list[str] = []
    normalized: list[dict[str, Any]] = []

    try:
        event_rows, location_rows, category_rows = fetch_official_tables()
        source_event_rows = len(event_rows)
        source_location_rows = len(location_rows)
        source_category_rows = len(category_rows)
        if not event_rows:
            raise RuntimeError("official Parks event listing returned zero rows")
        if not location_rows:
            raise RuntimeError("official Parks event locations returned zero rows")

        locations_by_id = related_index(location_rows)
        categories_by_id = related_index(category_rows)
        counts: dict[str, int] = defaultdict(int)
        for row in event_rows:
            sid = event_id(row)
            if sid:
                counts[sid] += 1
        duplicate_source_event_ids = sorted(key for key, count in counts.items() if count > 1)
        if duplicate_source_event_ids:
            raise RuntimeError(
                f"official Parks primary table contains duplicate event_id values: {duplicate_source_event_ids[:10]}"
            )

        all_normalized = [
            normalize_event_item(row, locations_by_id.get(event_id(row), []), categories_by_id.get(event_id(row), []))
            for row in event_rows
            if event_id(row)
        ]
        # The retired BigApps endpoint represented current/future discovery. Keep
        # that contract and do not inject the complete 2013+ history downstream.
        normalized = [
            row
            for row in all_normalized
            if str(row.get("end_date") or row.get("start_date") or "") >= today
        ]
        if not normalized:
            raise RuntimeError("official Parks tables produced zero current/future events")
    except Exception as exc:
        live_fetch_error = str(exc)
        committed_rows = load_committed_snapshot_events()
        if committed_rows:
            normalized = committed_rows
            fetch_mode = "committed_snapshot_fallback"
        else:
            fetch_mode = "live_fetch_failed"

    current_future = [
        row
        for row in normalized
        if str(row.get("end_date") or row.get("start_date") or row.get("start_date_time") or "")[:10] >= today
    ]
    with_coords = sum(1 for row in normalized if row.get("lat") is not None and row.get("lng") is not None)
    multiple_points = sum(1 for row in normalized if row.get("source_coordinate_state") == "multiple_source_location_points")
    qa_pass = bool(normalized)
    error = live_fetch_error if fetch_mode != "live" else None

    snapshot = {
        "generated_at_utc": generated_at,
        "source_url": EVENTS_URL,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_datasets": {
            "events": EVENTS_DATASET_ID,
            "locations": LOCATIONS_DATASET_ID,
            "categories": CATEGORIES_DATASET_ID,
        },
        "legacy_source_url": LEGACY_BIGAPPS_URL,
        "legacy_source_is_freshness_authority": False,
        "fetch_mode": fetch_mode,
        "events": normalized,
    }
    report = {
        "generated_at_utc": generated_at,
        "qa_pass": qa_pass,
        "fetch_mode": fetch_mode,
        "source_url": EVENTS_URL,
        "source_contract_version": SOURCE_CONTRACT_VERSION,
        "source_datasets": {
            "events": EVENTS_DATASET_ID,
            "locations": LOCATIONS_DATASET_ID,
            "categories": CATEGORIES_DATASET_ID,
        },
        "source_event_rows_fetched": source_event_rows,
        "source_location_rows_fetched": source_location_rows,
        "source_category_rows_fetched": source_category_rows,
        "snapshot_rows": len(normalized),
        "current_future_rows": len(current_future),
        "rows_with_coordinates": with_coords,
        "rows_with_multiple_authoritative_location_points": multiple_points,
        "duplicate_source_event_id_count": len(duplicate_source_event_ids),
        "error": error,
        "live_fetch_error": live_fetch_error,
        "legacy_source_url": LEGACY_BIGAPPS_URL,
        "legacy_source_is_freshness_authority": False,
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
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
