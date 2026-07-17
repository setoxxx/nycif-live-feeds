#!/usr/bin/env python3
"""Build focused human-review sheet for supplemental pin-quality flagged rows.

Review-only. Does not approve, promote, or modify protected feeds.
"""

from __future__ import annotations

import json
import sys
from typing import Any

try:
    from scripts.build_supplemental_pin_quality_review_report import classify_row, parent_park_from_display, priority_score
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        load_parks_properties_name_index,
        repo_relative,
        save_json_file,
        utc_now_iso,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover
    from build_supplemental_pin_quality_review_report import classify_row, parent_park_from_display, priority_score
    from coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        load_parks_properties_name_index,
        repo_relative,
        save_json_file,
        utc_now_iso,
        write_csv,
    )

QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
JSON_PATH = DATA_DIR / "supplemental_pin_quality_human_review_sheet.json"
CSV_PATH = DATA_DIR / "supplemental_pin_quality_human_review_sheet.csv"
REPORT_PATH = DATA_DIR / "supplemental_pin_quality_human_review_sheet_report.json"

FLAGGED_CATEGORIES = {
    "outside_parks_feed_intake",
    "outside_after_pin_quality_correction",
    "outside_after_geoclient",
    "outside_medium_confidence_source",
    "outside_other",
    "no_polygon_match",
}

CSV_FIELDS = [
    "review_rank",
    "pin_quality_category",
    "priority_score",
    "manual_review_status",
    "promotion_allowed",
    "title",
    "display_location",
    "parent_park",
    "borough",
    "proposed_lat",
    "proposed_lng",
    "geocoder_source",
    "geocoder_confidence",
    "confidence_reason",
    "google_maps_search_url",
    "google_maps_pin_url",
    "approval_decision_reason",
    "manual_reviewer",
    "manual_reviewed_at_utc",
]


def review_row(row: dict[str, Any], *, category: str) -> dict[str, Any]:
    display = str(row.get("display_location") or "")
    borough = str(row.get("borough") or "")
    lat = row.get("proposed_lat")
    lng = row.get("proposed_lng")
    return {
        "review_rank": row.get("review_rank"),
        "pin_quality_category": category,
        "priority_score": priority_score(row, category),
        "manual_review_status": row.get("manual_review_status"),
        "promotion_allowed": False,
        "title": row.get("title"),
        "display_location": display,
        "parent_park": parent_park_from_display(display),
        "borough": borough,
        "proposed_lat": lat,
        "proposed_lng": lng,
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "google_maps_search_url": google_maps_search_url(display or row.get("title"), borough),
        "google_maps_pin_url": google_maps_pin_url(lat, lng),
        "approval_decision_reason": row.get("approval_decision_reason"),
        "manual_reviewer": row.get("manual_reviewer"),
        "manual_reviewed_at_utc": row.get("manual_reviewed_at_utc"),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def main() -> int:
    queue = load_json_file(QUEUE_PATH, {}).get("approval_queue") or []
    parks_index = load_parks_properties_name_index()
    flagged: list[dict[str, Any]] = []
    for row in queue:
        if (row.get("manual_review_status") or "") != "approved":
            continue
        category = classify_row(row, parks_index)
        if category in FLAGGED_CATEGORIES:
            flagged.append(review_row(row, category=category))
    flagged.sort(key=lambda item: (-int(item["priority_score"]), int(item.get("review_rank") or 0)))

    generated_at = utc_now_iso()
    report = {
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_pin_quality_human_review_sheet",
        "flagged_row_count": len(flagged),
        "json_output": repo_relative(JSON_PATH),
        "csv_output": repo_relative(CSV_PATH),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": (
            "Human reviewer inspects flagged rows via pin/search URLs. "
            "Do not promote until pins are verified. promotion_allowed remains false."
        ),
    }
    save_json_file(JSON_PATH, {"generated_at_utc": generated_at, "review_sheet": flagged})
    write_csv(CSV_PATH, flagged, CSV_FIELDS)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
