#!/usr/bin/env python3
"""Build supplemental review queues for calendar-only and Parks-only coverage gaps.

Compares current/future title+date keys across permit Open Data, citywide calendar,
and NYC Parks BigApps events. Writes human-review staging artifacts only.

Does NOT modify location_cache.json, staged feeds, or the public map.
Does NOT set promotion_allowed=true or approve any rows.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.audit_multi_source_coverage import (
        build_calendar_index,
        build_parks_index,
        build_permit_index,
        calendar_rows,
        parks_rows,
        permit_rows,
    )
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        date_key,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        overlap_key,
        repo_relative,
        row_coords,
        safety_fields,
        save_json_file,
        utc_now_iso,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from audit_multi_source_coverage import (
        build_calendar_index,
        build_parks_index,
        build_permit_index,
        calendar_rows,
        parks_rows,
        permit_rows,
    )
    from coverage_gap_utils import (
        DATA_DIR,
        date_key,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        overlap_key,
        repo_relative,
        row_coords,
        safety_fields,
        save_json_file,
        utc_now_iso,
        write_csv,
    )

PERMIT_SNAPSHOT = DATA_DIR / "raw_nyc_open_data_snapshot.json"
CALENDAR_SNAPSHOT = DATA_DIR / "nyc_citywide_events_calendar_snapshot.json"
PARKS_SNAPSHOT = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"

CALENDAR_QUEUE_JSON = DATA_DIR / "supplemental_calendar_only_review_queue.json"
CALENDAR_QUEUE_CSV = DATA_DIR / "supplemental_calendar_only_review_queue.csv"
CALENDAR_QUEUE_REPORT = DATA_DIR / "supplemental_calendar_only_review_queue_report.json"

PARKS_QUEUE_JSON = DATA_DIR / "supplemental_parks_only_review_queue.json"
PARKS_QUEUE_CSV = DATA_DIR / "supplemental_parks_only_review_queue.csv"
PARKS_QUEUE_REPORT = DATA_DIR / "supplemental_parks_only_review_queue_report.json"

COORD_PROPOSALS_JSON = DATA_DIR / "calendar_parks_coord_match_proposals.json"
COORD_PROPOSALS_REPORT = DATA_DIR / "calendar_parks_coord_match_proposals_report.json"

CALENDAR_CSV_FIELDS = [
    "review_rank",
    "overlap_key",
    "title",
    "start_date_time",
    "address",
    "boroughs",
    "categories",
    "parks_title_date_match",
    "proposed_lat",
    "proposed_lng",
    "coord_proposal_source",
    "coord_proposal_confidence",
    "coord_proposal_reason",
    "google_maps_search_url",
    "google_maps_pin_url",
    "manual_review_status",
    "promotion_allowed",
    "manual_review_notes",
    "approval_decision_reason",
    "source_event_id",
    "permalink",
]

PARKS_CSV_FIELDS = [
    "review_rank",
    "overlap_key",
    "title",
    "start_date_time",
    "location",
    "borough",
    "lat",
    "lng",
    "has_coordinates",
    "calendar_title_date_match",
    "google_maps_search_url",
    "google_maps_pin_url",
    "manual_review_status",
    "promotion_allowed",
    "manual_review_notes",
    "approval_decision_reason",
    "source_event_id",
    "link",
]


def current_future_rows(rows: list[dict[str, Any]], *date_fields: str) -> list[dict[str, Any]]:
    today = utc_now_iso()[:10]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        for field in date_fields:
            if date_key(row.get(field)) >= today:
                filtered.append(row)
                break
    return filtered


def calendar_queue_item(
    row: dict[str, Any],
    rank: int,
    parks_match: dict[str, Any] | None,
) -> dict[str, Any]:
    lat, lng = row_coords(parks_match) if parks_match else (None, None)
    address = str(row.get("address") or "").strip()
    boroughs = row.get("boroughs") or []
    borough_label = ", ".join(str(value) for value in boroughs if value)
    item = {
        "review_rank": rank,
        "overlap_key": overlap_key(row.get("title"), row.get("start_date_time")),
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time"),
        "address": address,
        "boroughs": boroughs,
        "categories": row.get("categories") or [],
        "source_dataset": row.get("source_dataset") or "nyc-citywide-events-calendar-api",
        "source_event_id": row.get("source_event_id"),
        "permalink": row.get("permalink"),
        "review_reason": "calendar_title_date_key_not_in_permit_pipeline",
        "parks_title_date_match": bool(parks_match),
        "proposed_lat": lat,
        "proposed_lng": lng,
        "coord_proposal_source": "nyc_parks_bigapps_events_snapshot" if parks_match else None,
        "coord_proposal_confidence": "high" if parks_match else None,
        "coord_proposal_reason": (
            "Matched calendar row to Parks BigApps event by title+date; coordinates copied for manual review only."
            if parks_match
            else "No Parks title+date match; calendar snapshot has address text but no coordinates."
        ),
        "google_maps_search_url": google_maps_search_url(address or row.get("title"), borough_label),
        "google_maps_pin_url": google_maps_pin_url(lat, lng),
    }
    item.update(safety_fields())
    return item


def parks_queue_item(
    row: dict[str, Any],
    rank: int,
    calendar_match: bool,
) -> dict[str, Any]:
    lat, lng = row_coords(row)
    location = str(row.get("location") or row.get("display_location") or "").strip()
    borough = str(row.get("borough") or "").strip()
    item = {
        "review_rank": rank,
        "overlap_key": overlap_key(
            row.get("title"),
            row.get("start_date_time") or row.get("start_date"),
        ),
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time") or row.get("start_date"),
        "location": location,
        "borough": borough,
        "lat": lat,
        "lng": lng,
        "has_coordinates": lat is not None and lng is not None,
        "source_dataset": row.get("source_dataset") or "nyc-parks-bigapps-events",
        "source_event_id": row.get("source_event_id"),
        "link": row.get("link"),
        "review_reason": "parks_title_date_key_not_in_permit_pipeline",
        "calendar_title_date_match": calendar_match,
        "google_maps_search_url": google_maps_search_url(location or row.get("title"), borough),
        "google_maps_pin_url": google_maps_pin_url(lat, lng),
    }
    item.update(safety_fields())
    return item


def coord_proposal_item(calendar_row: dict[str, Any], parks_row: dict[str, Any]) -> dict[str, Any]:
    lat, lng = row_coords(parks_row)
    item = {
        "overlap_key": overlap_key(calendar_row.get("title"), calendar_row.get("start_date_time")),
        "calendar_title": calendar_row.get("title"),
        "calendar_start_date_time": calendar_row.get("start_date_time"),
        "calendar_address": calendar_row.get("address"),
        "calendar_source_event_id": calendar_row.get("source_event_id"),
        "parks_title": parks_row.get("title"),
        "parks_location": parks_row.get("location") or parks_row.get("display_location"),
        "parks_source_event_id": parks_row.get("source_event_id"),
        "proposed_lat": lat,
        "proposed_lng": lng,
        "geocoder_source": "nyc_parks_bigapps_events_snapshot",
        "geocoder_confidence": "high" if lat is not None else None,
        "confidence_reason": "Title+date overlap between citywide calendar and Parks BigApps events snapshot.",
        "proposal_status": "filled_pending_manual_review" if lat is not None else "unfilled_pending_geocoder",
    }
    item.update(safety_fields())
    return item


def main() -> int:
    permits = permit_rows(load_json_file(PERMIT_SNAPSHOT, []))
    calendar = calendar_rows(load_json_file(CALENDAR_SNAPSHOT, []))
    parks = parks_rows(load_json_file(PARKS_SNAPSHOT, {}))

    current_future_permits = current_future_rows(permits, "start_date_time")
    current_future_calendar = current_future_rows(calendar, "start_date_time")
    current_future_parks = current_future_rows(parks, "start_date_time", "start_date")

    permit_index = build_permit_index(current_future_permits)
    calendar_index = build_calendar_index(current_future_calendar)
    parks_index = build_parks_index(current_future_parks)

    permit_keys = set(permit_index)
    calendar_keys = set(calendar_index)
    parks_keys = set(parks_index)
    calendar_only_keys = sorted(calendar_keys - permit_keys)
    parks_only_keys = sorted(parks_keys - permit_keys)
    parks_calendar_overlap_keys = set(parks_keys) & set(calendar_keys)

    calendar_queue: list[dict[str, Any]] = []
    coord_proposals: list[dict[str, Any]] = []
    for rank, key in enumerate(calendar_only_keys, start=1):
        calendar_row = calendar_index[key][0]
        parks_match = parks_index.get(key, [None])[0]
        calendar_queue.append(calendar_queue_item(calendar_row, rank, parks_match))
        if parks_match:
            coord_proposals.append(coord_proposal_item(calendar_row, parks_match))

    calendar_queue.sort(
        key=lambda row: (
            0 if row.get("parks_title_date_match") else 1,
            -len(row.get("categories") or []),
            row.get("review_rank") or 0,
        )
    )
    for index, row in enumerate(calendar_queue, start=1):
        row["review_rank"] = index

    parks_queue: list[dict[str, Any]] = []
    for rank, key in enumerate(parks_only_keys, start=1):
        parks_row = parks_index[key][0]
        parks_queue.append(
            parks_queue_item(
                parks_row,
                rank,
                key in parks_calendar_overlap_keys,
            )
        )
    parks_queue.sort(
        key=lambda row: (
            0 if row.get("has_coordinates") else 1,
            row.get("review_rank") or 0,
        )
    )
    for index, row in enumerate(parks_queue, start=1):
        row["review_rank"] = index

    generated_at = utc_now_iso()
    calendar_category_counts = Counter()
    for row in calendar_queue:
        for category in row.get("categories") or []:
            calendar_category_counts[str(category)] += 1

    calendar_report = {
        "generated_at_utc": generated_at,
        "phase": "supplemental_calendar_only_review_queue",
        "queue_count": len(calendar_queue),
        "parks_title_date_match_count": sum(1 for row in calendar_queue if row.get("parks_title_date_match")),
        "without_parks_match_count": sum(1 for row in calendar_queue if not row.get("parks_title_date_match")),
        "with_proposed_coordinates_count": sum(
            1 for row in calendar_queue if row.get("proposed_lat") is not None and row.get("proposed_lng") is not None
        ),
        "category_counts": dict(calendar_category_counts.most_common(20)),
        "promotion_allowed_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "json_output": repo_relative(CALENDAR_QUEUE_JSON),
        "csv_output": repo_relative(CALENDAR_QUEUE_CSV),
        "next_required_step": "Manually review calendar-only rows. Parks title+date matches include proposed coordinates for review only; do not auto-merge into staged feed.",
    }

    parks_report = {
        "generated_at_utc": generated_at,
        "phase": "supplemental_parks_only_review_queue",
        "queue_count": len(parks_queue),
        "with_coordinates_count": sum(1 for row in parks_queue if row.get("has_coordinates")),
        "without_coordinates_count": sum(1 for row in parks_queue if not row.get("has_coordinates")),
        "calendar_title_date_match_count": sum(1 for row in parks_queue if row.get("calendar_title_date_match")),
        "promotion_allowed_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "json_output": repo_relative(PARKS_QUEUE_JSON),
        "csv_output": repo_relative(PARKS_QUEUE_CSV),
        "next_required_step": "Manually review Parks-only rows for supplemental ingestion. Coordinates are informational; permit pipeline merge requires explicit authorization.",
    }

    coord_report = {
        "generated_at_utc": generated_at,
        "phase": "calendar_parks_coord_match_proposals",
        "proposal_count": len(coord_proposals),
        "filled_count": sum(1 for row in coord_proposals if row.get("proposal_status") == "filled_pending_manual_review"),
        "unfilled_count": sum(1 for row in coord_proposals if row.get("proposal_status") == "unfilled_pending_geocoder"),
        "promotion_allowed_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": "Review proposed Parks coordinates for calendar-only overlaps. These are staging proposals only.",
    }

    save_json_file(CALENDAR_QUEUE_JSON, {"generated_at_utc": generated_at, "review_queue": calendar_queue})
    write_csv(CALENDAR_QUEUE_CSV, calendar_queue, CALENDAR_CSV_FIELDS)
    save_json_file(CALENDAR_QUEUE_REPORT, calendar_report)

    save_json_file(PARKS_QUEUE_JSON, {"generated_at_utc": generated_at, "review_queue": parks_queue})
    write_csv(PARKS_QUEUE_CSV, parks_queue, PARKS_CSV_FIELDS)
    save_json_file(PARKS_QUEUE_REPORT, parks_report)

    save_json_file(COORD_PROPOSALS_JSON, {"generated_at_utc": generated_at, "proposals": coord_proposals})
    save_json_file(COORD_PROPOSALS_REPORT, coord_report)

    summary = {
        "generated_at_utc": generated_at,
        "calendar_only_queue_count": len(calendar_queue),
        "parks_only_queue_count": len(parks_queue),
        "calendar_parks_coord_proposals_count": len(coord_proposals),
        "calendar_report": calendar_report,
        "parks_report": parks_report,
        "coord_report": coord_report,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
