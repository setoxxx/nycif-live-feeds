#!/usr/bin/env python3
"""Fetch current NYC Parks events from official NYC Open Data tables.

The legacy Parks website JSON endpoint now returns HTTP 405 in unattended
clients. NYC Open Data publishes the same Parks Events database as related
first-party tables. This collector uses the Event Listing table as the event
authority, joins Event Locations by ``event_id`` for first-party coordinates,
and joins Event Categories by ``event_id`` for classification input.

Coordinates are never inferred here. Valid coordinates from the official Parks
location table receive explicit ``exact_source_coordinate`` evidence; events
without a valid official coordinate remain non-exact for downstream semantic
review/list-only handling.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
REPORT_PATH = DATA_DIR / "nyc_parks_bigapps_events_sync_report.json"

OPEN_DATA_BASE = "https://data.cityofnewyork.us/resource"
EVENT_LISTING_DATASET = "fudw-fgrp"
EVENT_LOCATIONS_DATASET = "cpcm-i88g"
EVENT_CATEGORIES_DATASET = "xtsw-fqvh"
EVENTS_URL = f"{OPEN_DATA_BASE}/{EVENT_LISTING_DATASET}.json"
LOCATIONS_URL = f"{OPEN_DATA_BASE}/{EVENT_LOCATIONS_DATASET}.json"
CATEGORIES_URL = f"{OPEN_DATA_BASE}/{EVENT_CATEGORIES_DATASET}.json"
SOURCE_PAGE = "https://data.cityofnewyork.us/d/fudw-fgrp"
PAGE_LIMIT = 50000
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NYCIF-live-feeds/2.0 (+https://nycinfocus.com/)",
}

BOROUGH_CODES = {
    "M": "Manhattan",
    "MN": "Manhattan",
    "MANHATTAN": "Manhattan",
    "B": "Brooklyn",
    "BK": "Brooklyn",
    "BROOKLYN": "Brooklyn",
    "X": "Bronx",
    "BX": "Bronx",
    "BRONX": "Bronx",
    "Q": "Queens",
    "QN": "Queens",
    "QUEENS": "Queens",
    "R": "Staten Island",
    "SI": "Staten Island",
    "STATEN ISLAND": "Staten Island",
}


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def text(value: Any) -> str:
    return str(value or "").strip()


def first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def fetch_json(url: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params or {}, safe="(),'* >=<:")
    request_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(request_url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"unexpected NYC Open Data response from {url}")
    return [row for row in payload if isinstance(row, dict)]


def fetch_all(url: str, *, where: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {"$limit": str(PAGE_LIMIT), "$offset": str(offset)}
        if where:
            params["$where"] = where
        page = fetch_json(url, params)
        rows.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += len(page)
    return rows


def parse_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def valid_coordinate_pair(lat: Any, lng: Any) -> tuple[float | None, float | None]:
    lat_f = parse_float(lat)
    lng_f = parse_float(lng)
    if lat_f is None or lng_f is None:
        return None, None
    if not (40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0):
        return None, None
    return lat_f, lng_f


def canonical_borough(value: Any) -> str | None:
    key = text(value).upper()
    return BOROUGH_CODES.get(key) or (text(value) or None)


def normalize_date(value: Any) -> str:
    raw = text(value)
    if not raw:
        return ""
    # Socrata floating timestamps are normally YYYY-MM-DDT00:00:00.000.
    if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
        return raw[:10]
    # Defensive mm/dd/yyyy support for older exports.
    for fmt in ("%m/%d/%Y", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return ""


def normalize_time(value: Any) -> str:
    raw = text(value)
    if not raw:
        return ""
    if "T" in raw:
        raw = raw.split("T", 1)[1]
    raw = raw.rstrip("Z")
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(raw, fmt).strftime("%H:%M:%S")
        except ValueError:
            pass
    return raw


def combine_datetime(day: str, clock: str) -> str | None:
    if not day:
        return None
    return f"{day}T{clock or '00:00:00'}"


def official_coordinate_evidence(lat: float | None, lng: float | None) -> dict[str, Any] | None:
    if lat is None or lng is None:
        return None
    return {
        "tier": "exact_source_coordinate",
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": LOCATIONS_URL,
        "provider": "NYC Parks / NYC Open Data",
        "reason_code": "OFFICIAL_SOURCE_COORDINATE",
        "reason_detail": "Coordinate pair supplied by the official NYC Parks Events Listing location table.",
    }


def index_related(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        event_id = text(first(row, "event_id", "eventid", "id"))
        if event_id:
            indexed[event_id].append(row)
    return dict(indexed)


def choose_location(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    # Prefer a location with valid official coordinates; otherwise retain the
    # first official location as display/list-only context.
    for row in rows:
        lat, lng = valid_coordinate_pair(first(row, "lat", "latitude"), first(row, "long", "lng", "longitude"))
        if lat is not None and lng is not None:
            return row
    return rows[0]


def categories_for(rows: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for row in rows:
        value = text(first(row, "category", "name", "category_name", "event_category"))
        if value and value not in values:
            values.append(value)
    return values


def normalize_event_item(
    item: dict[str, Any],
    locations: list[dict[str, Any]],
    category_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    event_id = text(first(item, "event_id", "eventid", "id"))
    location = choose_location(locations)
    lat, lng = valid_coordinate_pair(
        first(location, "lat", "latitude"),
        first(location, "long", "lng", "longitude"),
    )

    event_day = normalize_date(first(item, "date", "event_date", "start_date", "startdate"))
    end_day = normalize_date(first(item, "end_date", "enddate")) or event_day
    start_time = normalize_time(first(item, "start_time", "starttime"))
    end_time = normalize_time(first(item, "end_time", "endtime"))

    park_name = text(first(item, "park_name", "parkname")) or text(first(location, "name", "location", "park_name"))
    location_name = text(first(location, "name", "location", "address")) or park_name
    borough = canonical_borough(first(item, "borough", "boro")) or canonical_borough(first(location, "borough", "boro"))
    category_values = categories_for(category_rows)
    event_type = text(first(item, "event_type", "type"))
    if event_type and event_type not in category_values:
        category_values.append(event_type)

    return {
        "source_dataset": "nyc-parks-bigapps-events",
        "source_event_id": event_id,
        "title": first(item, "title", "name", "event_name"),
        "start_date_time": combine_datetime(event_day, start_time),
        "end_date_time": combine_datetime(end_day, end_time),
        "start_date": event_day or None,
        "start_time": start_time or None,
        "end_date": end_day or None,
        "end_time": end_time or None,
        "location": location_name or None,
        "display_location": location_name or None,
        "address": first(location, "address"),
        "borough": borough,
        "park_names": [park_name] if park_name else [],
        "park_ids": first(location, "park_id", "parkid"),
        "categories": category_values,
        "event_type": event_type or None,
        "description": first(item, "description", "desc", "short_description"),
        "link": first(item, "link", "url", "permalink"),
        "registration_url": first(item, "registration_url"),
        "registration_description": first(item, "registration_description"),
        "contact_phone": first(item, "contact_phone", "phone"),
        "instructor": first(item, "instructor"),
        "image": first(item, "image", "image_url"),
        "lat": lat,
        "lng": lng,
        "location_evidence": official_coordinate_evidence(lat, lng),
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def fetch_events() -> tuple[list[dict[str, Any]], dict[str, int]]:
    today = date.today().isoformat()
    # The primary Parks listing exposes a floating timestamp field named date.
    # Filtering at the source keeps the daily launch transaction bounded.
    listing = fetch_all(EVENTS_URL, where=f"date >= '{today}T00:00:00.000'")
    if not listing:
        raise RuntimeError("NYC Parks Open Data event listing returned no current/future rows")

    locations = fetch_all(LOCATIONS_URL)
    categories = fetch_all(CATEGORIES_URL)
    location_index = index_related(locations)
    category_index = index_related(categories)

    normalized: list[dict[str, Any]] = []
    invalid_identity = 0
    for item in listing:
        event_id = text(first(item, "event_id", "eventid", "id"))
        if not event_id:
            invalid_identity += 1
            continue
        row = normalize_event_item(item, location_index.get(event_id, []), category_index.get(event_id, []))
        if row.get("title") and row.get("start_date_time"):
            normalized.append(row)
        else:
            invalid_identity += 1

    return normalized, {
        "listing_rows": len(listing),
        "location_rows": len(locations),
        "category_rows": len(categories),
        "invalid_missing_identity_or_date": invalid_identity,
    }


def main() -> int:
    generated_at = datetime.now(timezone.utc).isoformat()
    error: str | None = None
    source_counts: dict[str, int] = {}
    try:
        normalized, source_counts = fetch_events()
        fetch_mode = "live_open_data"
    except Exception as exc:
        normalized = []
        fetch_mode = "live_fetch_failed"
        error = str(exc)

    today = date.today().isoformat()
    current_future = [row for row in normalized if text(row.get("start_date_time"))[:10] >= today]
    with_coords = sum(1 for row in normalized if row.get("lat") is not None and row.get("lng") is not None)
    with_exact_source_evidence = sum(
        1
        for row in normalized
        if isinstance(row.get("location_evidence"), dict)
        and row["location_evidence"].get("exact_pin_eligible") is True
    )
    qa_pass = bool(normalized) and with_exact_source_evidence == with_coords and not error

    snapshot = {
        "generated_at_utc": generated_at,
        "source_url": EVENTS_URL,
        "source_page": SOURCE_PAGE,
        "source_locations_url": LOCATIONS_URL,
        "source_categories_url": CATEGORIES_URL,
        "fetch_mode": fetch_mode,
        "events": normalized,
    }
    report = {
        "generated_at_utc": generated_at,
        "qa_pass": qa_pass,
        "fetch_mode": fetch_mode,
        "source_url": EVENTS_URL,
        "source_page": SOURCE_PAGE,
        "snapshot_rows": len(normalized),
        "current_future_rows": len(current_future),
        "rows_with_coordinates": with_coords,
        "rows_with_exact_source_coordinate_evidence": with_exact_source_evidence,
        "coordinate_evidence_parity": with_exact_source_evidence == with_coords,
        **source_counts,
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
