#!/usr/bin/env python3
"""Build M11 unified supplemental manual approval queue (Phase 2D-style).

Reads supplemental_events_staging_feed.json and writes a human-review approval
queue separate from permit GPS review. Does not approve, promote, or publish.

Outputs:
- data/supplemental_manual_approval_queue.json
- data/supplemental_manual_approval_queue_report.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        safety_fields,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        safety_fields,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )

STAGING_FEED_PATH = DATA_DIR / "supplemental_events_staging_feed.json"
APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
APPROVAL_QUEUE_REPORT_PATH = DATA_DIR / "supplemental_manual_approval_queue_report.json"


def events_from_feed(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def review_priority(row: dict[str, Any]) -> tuple[int, int, str, str]:
    has_coords = valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))
    intake = row.get("intake_type") or ""
    if intake == "parks_only" and has_coords and not row.get("calendar_title_date_match"):
        tier = 0
    elif intake == "calendar_only" and row.get("parks_title_date_match") and has_coords:
        tier = 1
    elif has_coords:
        tier = 2
    else:
        tier = 3
    return (tier, 0 if has_coords else 1, row.get("date") or "9999-99-99", row.get("title") or "")


def approval_item(row: dict[str, Any], rank: int) -> dict[str, Any]:
    item = {
        "review_rank": rank,
        "overlap_key": row.get("overlap_key"),
        "intake_type": row.get("intake_type"),
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time"),
        "date": row.get("date"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "proposed_lat": row.get("proposed_lat"),
        "proposed_lng": row.get("proposed_lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "parks_title_date_match": bool(row.get("parks_title_date_match")),
        "calendar_title_date_match": bool(row.get("calendar_title_date_match")),
        "has_coordinates": valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")),
        "source_dataset": row.get("source_dataset"),
        "source_event_id": row.get("source_event_id"),
        "review_reason": row.get("review_reason"),
        "source_phase": "m11_supplemental_events_staging_intake",
        "production_feed": False,
    }
    item.update(safety_fields())
    return item


def main() -> int:
    feed = load_json_file(STAGING_FEED_PATH, {})
    events = events_from_feed(feed)
    events.sort(key=review_priority)
    queue = [approval_item(row, index + 1) for index, row in enumerate(events)]

    generated_at = utc_now_iso()
    intake_counts = Counter(row.get("intake_type") for row in queue)
    status_counts = Counter(row.get("manual_review_status") for row in queue)
    with_coords = sum(1 for row in queue if row.get("has_coordinates"))
    report = {
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_manual_approval_queue",
        "source_feed": repo_relative(STAGING_FEED_PATH),
        "approval_queue_count": len(queue),
        "calendar_only_count": intake_counts.get("calendar_only", 0),
        "parks_only_count": intake_counts.get("parks_only", 0),
        "with_coordinates_count": with_coords,
        "without_coordinates_count": len(queue) - with_coords,
        "approved_count": 0,
        "rejected_count": 0,
        "pending_count": status_counts.get("pending", 0),
        "promotion_allowed_count": 0,
        "status_counts": dict(status_counts),
        "intake_counts": dict(intake_counts),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "qa_pass": len(queue) > 0 and status_counts.get("pending", 0) == len(queue),
        "next_required_step": (
            "Human review of supplemental_manual_approval_queue.json. "
            "Do not merge into feeds=main or permit staged feed without explicit authorization."
        ),
    }

    save_json_file(APPROVAL_QUEUE_PATH, {"generated_at_utc": generated_at, "approval_queue": queue})
    save_json_file(APPROVAL_QUEUE_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
