#!/usr/bin/env python3
"""Build human-readable M11 supplemental manual approval review sheet.

Reads supplemental_manual_approval_queue.json. Review-only — does not approve,
promote, or modify protected feeds or the public map.

Outputs:
- data/supplemental_manual_approval_review_sheet.json
- data/supplemental_manual_approval_review_sheet.csv
- data/supplemental_manual_approval_review_sheet_report.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        write_csv,
    )

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
REVIEW_SHEET_JSON_PATH = DATA_DIR / "supplemental_manual_approval_review_sheet.json"
REVIEW_SHEET_CSV_PATH = DATA_DIR / "supplemental_manual_approval_review_sheet.csv"
REVIEW_SHEET_REPORT_PATH = DATA_DIR / "supplemental_manual_approval_review_sheet_report.json"

CSV_FIELDS = [
    "review_rank",
    "intake_type",
    "manual_review_status",
    "promotion_allowed",
    "title",
    "start_date_time",
    "display_location",
    "borough",
    "proposed_lat",
    "proposed_lng",
    "geocoder_source",
    "geocoder_confidence",
    "confidence_reason",
    "parks_title_date_match",
    "calendar_title_date_match",
    "has_coordinates",
    "google_maps_search_url",
    "google_maps_pin_url",
    "manual_review_notes",
    "approval_decision_reason",
    "manual_reviewer",
    "manual_reviewed_at_utc",
    "overlap_key",
    "source_event_id",
]


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def review_item(row: dict[str, Any]) -> dict[str, Any]:
    location = str(row.get("display_location") or "")
    borough = str(row.get("borough") or "")
    lat = row.get("proposed_lat")
    lng = row.get("proposed_lng")
    return {
        "review_rank": row.get("review_rank"),
        "intake_type": row.get("intake_type"),
        "manual_review_status": row.get("manual_review_status") or "pending",
        "promotion_allowed": False,
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time"),
        "display_location": location,
        "borough": borough,
        "proposed_lat": lat,
        "proposed_lng": lng,
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "parks_title_date_match": row.get("parks_title_date_match"),
        "calendar_title_date_match": row.get("calendar_title_date_match"),
        "has_coordinates": row.get("has_coordinates"),
        "google_maps_search_url": google_maps_search_url(location or row.get("title"), borough),
        "google_maps_pin_url": google_maps_pin_url(lat, lng),
        "manual_review_notes": row.get("manual_review_notes") or "",
        "approval_decision_reason": row.get("approval_decision_reason") or "",
        "manual_reviewer": row.get("manual_reviewer") or "",
        "manual_reviewed_at_utc": row.get("manual_reviewed_at_utc") or "",
        "overlap_key": row.get("overlap_key"),
        "source_event_id": row.get("source_event_id"),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def main() -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(payload, "approval_queue")
    queue.sort(key=lambda row: int(row.get("review_rank") or 0))
    review_rows = [review_item(row) for row in queue]

    generated_at = utc_now_iso()
    status_counts = Counter(row.get("manual_review_status") for row in review_rows)
    intake_counts = Counter(row.get("intake_type") for row in review_rows)
    report = {
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_manual_approval_review_sheet",
        "review_sheet_count": len(review_rows),
        "status_counts": dict(status_counts),
        "intake_counts": dict(intake_counts),
        "promotion_allowed_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "json_output": repo_relative(REVIEW_SHEET_JSON_PATH),
        "csv_output": repo_relative(REVIEW_SHEET_CSV_PATH),
        "next_required_step": (
            "Manually inspect supplemental rows via search/pin URLs. "
            "Update supplemental_manual_approval_queue.json in a separate reviewed commit when ready."
        ),
    }

    save_json_file(REVIEW_SHEET_JSON_PATH, {"generated_at_utc": generated_at, "review_sheet": review_rows})
    write_csv(REVIEW_SHEET_CSV_PATH, review_rows, CSV_FIELDS)
    save_json_file(REVIEW_SHEET_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
