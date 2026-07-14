#!/usr/bin/env python3
"""Build a combined supplemental events staging feed for manual intake review.

Merges calendar-only and Parks-only coverage-gap queues into a single staging
artifact separate from the permit staged feed. Does NOT modify protected feeds
or the public map.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        date_key,
        load_json_file,
        repo_relative,
        row_coords,
        safety_fields,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from coverage_gap_utils import (
        DATA_DIR,
        date_key,
        load_json_file,
        repo_relative,
        row_coords,
        safety_fields,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )

CALENDAR_QUEUE = DATA_DIR / "supplemental_calendar_only_review_queue.json"
PARKS_QUEUE = DATA_DIR / "supplemental_parks_only_review_queue.json"
FEED_PATH = DATA_DIR / "supplemental_events_staging_feed.json"
MANIFEST_PATH = DATA_DIR / "supplemental_events_staging_manifest.json"
REPORT_PATH = DATA_DIR / "supplemental_events_staging_report.json"


def queue_rows(path: Path) -> list[dict[str, Any]]:
    payload = load_json_file(path, [])
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("review_queue", "rows", "events"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def calendar_event(row: dict[str, Any]) -> dict[str, Any]:
    lat = row.get("proposed_lat")
    lng = row.get("proposed_lng")
    if not valid_nyc_lat_lng(lat, lng):
        lat, lng = None, None
    boroughs = row.get("boroughs") or []
    borough = ", ".join(str(value) for value in boroughs if value)
    event = {
        "intake_type": "calendar_only",
        "overlap_key": row.get("overlap_key"),
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time"),
        "date": date_key(row.get("start_date_time")),
        "display_location": row.get("address") or "Location TBA",
        "borough": borough,
        "categories": row.get("categories") or [],
        "source_dataset": row.get("source_dataset") or "nyc-citywide-events-calendar-api",
        "source_event_id": row.get("source_event_id"),
        "permalink": row.get("permalink"),
        "lat": lat,
        "lng": lng,
        "proposed_lat": lat,
        "proposed_lng": lng,
        "geocoder_source": row.get("coord_proposal_source"),
        "geocoder_confidence": row.get("coord_proposal_confidence"),
        "confidence_reason": row.get("coord_proposal_reason"),
        "parks_title_date_match": bool(row.get("parks_title_date_match")),
        "review_reason": row.get("review_reason") or "calendar_title_date_key_not_in_permit_pipeline",
        "production_feed": False,
    }
    event.update(safety_fields())
    return event


def parks_event(row: dict[str, Any]) -> dict[str, Any]:
    lat, lng = row_coords(row)
    event = {
        "intake_type": "parks_only",
        "overlap_key": row.get("overlap_key"),
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time"),
        "date": date_key(row.get("start_date_time")),
        "display_location": row.get("location") or "Location TBA",
        "borough": row.get("borough") or "",
        "source_dataset": row.get("source_dataset") or "nyc-parks-bigapps-events",
        "source_event_id": row.get("source_event_id"),
        "link": row.get("link"),
        "lat": lat,
        "lng": lng,
        "proposed_lat": lat,
        "proposed_lng": lng,
        "geocoder_source": "nyc_parks_bigapps_events_snapshot" if lat is not None else None,
        "geocoder_confidence": "high" if lat is not None else None,
        "confidence_reason": (
            "Inline coordinates from NYC Parks BigApps events feed; manual review required before map merge."
            if lat is not None
            else "Parks-only row without inline coordinates; manual review required."
        ),
        "has_coordinates": bool(row.get("has_coordinates")),
        "calendar_title_date_match": bool(row.get("calendar_title_date_match")),
        "review_reason": row.get("review_reason") or "parks_title_date_key_not_in_permit_pipeline",
        "production_feed": False,
    }
    event.update(safety_fields())
    return event


def main() -> int:
    calendar_rows = queue_rows(CALENDAR_QUEUE)
    parks_rows = queue_rows(PARKS_QUEUE)

    events = [calendar_event(row) for row in calendar_rows]
    events.extend(parks_event(row) for row in parks_rows)
    events.sort(
        key=lambda row: (
            row.get("date") or "9999-99-99",
            row.get("start_date_time") or "",
            row.get("intake_type") or "",
            row.get("title") or "",
        )
    )

    with_coords = sum(1 for row in events if valid_nyc_lat_lng(row.get("lat"), row.get("lng")))
    calendar_count = sum(1 for row in events if row.get("intake_type") == "calendar_only")
    parks_count = sum(1 for row in events if row.get("intake_type") == "parks_only")

    generated_at = utc_now_iso()
    feed = {
        "generated_at_utc": generated_at,
        "phase": "supplemental_events_staging_intake",
        "production_feed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
        "events": events,
    }
    manifest = {
        "generated_at_utc": generated_at,
        "phase": "supplemental_events_staging_intake",
        "event_count": len(events),
        "calendar_only_count": calendar_count,
        "parks_only_count": parks_count,
        "with_proposed_coordinates_count": with_coords,
        "without_coordinates_count": len(events) - with_coords,
        "production_feed": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
        "source_queues": [
            repo_relative(CALENDAR_QUEUE),
            repo_relative(PARKS_QUEUE),
        ],
    }
    report = {
        "generated_at_utc": generated_at,
        "phase": "supplemental_events_staging_intake",
        "qa_pass": calendar_count > 0 and parks_count > 0,
        "event_count": len(events),
        "calendar_only_count": calendar_count,
        "parks_only_count": parks_count,
        "with_proposed_coordinates_count": with_coords,
        "without_coordinates_count": len(events) - with_coords,
        "feed_path": repo_relative(FEED_PATH),
        "manifest_path": repo_relative(MANIFEST_PATH),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "next_required_step": (
            "Human review of supplemental_events_staging_feed.json. "
            "Do not merge into permit staged feed without explicit authorization."
        ),
    }

    save_json_file(FEED_PATH, feed)
    save_json_file(MANIFEST_PATH, manifest)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
