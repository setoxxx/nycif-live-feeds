#!/usr/bin/env python3
"""Build human-review sheet for supplemental staging rows still missing coordinates.

Reads supplemental_events_staging_feed.json after memory auto-resolution.
Review-only — does not approve, promote, or modify protected feeds.

Outputs:
- data/supplemental_no_coord_human_review_sheet.json
- data/supplemental_no_coord_human_review_sheet.csv
- data/reports/supplemental_no_coord_human_review_sheet_report.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        is_summer_streets_event,
        is_ungeocodable_location,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        is_summer_streets_event,
        is_ungeocodable_location,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
        write_csv,
    )

FEED_PATH = DATA_DIR / "supplemental_events_staging_feed.json"
JSON_PATH = DATA_DIR / "supplemental_no_coord_human_review_sheet.json"
CSV_PATH = DATA_DIR / "supplemental_no_coord_human_review_sheet.csv"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_no_coord_human_review_sheet_report.json"

CSV_FIELDS = [
    "review_rank",
    "review_category",
    "suggested_disposition",
    "review_guidance",
    "manual_review_status",
    "promotion_allowed",
    "title",
    "display_location",
    "borough",
    "date",
    "overlap_key",
    "intake_type",
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


def classify_no_coord_row(row: dict[str, Any]) -> tuple[str, str, str]:
    title = str(row.get("title") or "")
    display = str(row.get("display_location") or "")
    title_lower = title.lower()
    display_lower = display.lower()

    if title_lower.startswith("canceled:") or "canceled" in title_lower[:20]:
        return (
            "canceled_event",
            "reject",
            "Canceled event — reject unless a verified replacement location is documented.",
        )

    if is_summer_streets_event(row):
        return (
            "summer_streets_route",
            "reject",
            "Summer Streets route event — not a single pin; reject or defer to route-specific policy.",
        )

    if "virtual" in display_lower or "online" in display_lower:
        return (
            "virtual_online",
            "reject",
            "Virtual/online event — reject for map intake (no physical pin).",
        )

    if any(token in display_lower for token in ("flyer", "see the flyer", "seee flyer")):
        return (
            "flyer_reference",
            "reject",
            "Location deferred to flyer — reject unless flyer address is researched and entered manually.",
        )

    if is_ungeocodable_location(display, row.get("borough")):
        if "election" in title_lower or "poll" in display_lower or "register" in title_lower:
            return (
                "election_admin",
                "reject",
                "Election/admin citywide event — not a mappable single venue; reject for supplemental map intake.",
            )
        if "watch part" in title_lower or "restaurant week" in title_lower:
            return (
                "citywide_program",
                "reject",
                "Multi-venue citywide program — not a single pin; reject unless one canonical venue is chosen.",
            )
        return (
            "citywide_multi_borough",
            "reject",
            "Citywide or multi-borough location text — reject unless narrowed to one borough + address.",
        )

    if re.search(r"\d+\s+\w+", display) or any(
        token in display_lower for token in ("avenue", "street", "broadway", "harlem", "floor")
    ):
        return (
            "geocodable_address",
            "approve_or_reject",
            "Physical address or venue name — research pin, approve with coords, or reject if invalid.",
        )

    return (
        "needs_manual_research",
        "approve_or_reject",
        "No memory match — research location, add coordinates if mappable, or reject.",
    )


def sheet_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
    category, suggested, guidance = classify_no_coord_row(row)
    display = str(row.get("display_location") or "")
    borough = str(row.get("borough") or "")
    return {
        "review_rank": rank,
        "review_category": category,
        "suggested_disposition": suggested,
        "review_guidance": guidance,
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "title": row.get("title"),
        "display_location": display,
        "borough": borough,
        "date": row.get("date"),
        "overlap_key": row.get("overlap_key"),
        "intake_type": row.get("intake_type"),
        "proposed_lat": row.get("proposed_lat"),
        "proposed_lng": row.get("proposed_lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "google_maps_search_url": google_maps_search_url(display, borough),
        "google_maps_pin_url": google_maps_pin_url(row.get("proposed_lat"), row.get("proposed_lng")),
        "approval_decision_reason": "",
        "manual_reviewer": "",
        "manual_reviewed_at_utc": "",
    }


def main() -> int:
    feed = load_json_file(FEED_PATH, {})
    events = feed.get("events", []) if isinstance(feed, dict) else []
    missing = [
        row
        for row in events
        if isinstance(row, dict) and not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))
    ]
    missing.sort(key=lambda row: (row.get("date") or "", row.get("title") or "", row.get("display_location") or ""))
    rows = [sheet_row(row, index + 1) for index, row in enumerate(missing)]
    category_counts = Counter(row["review_category"] for row in rows)
    suggested_counts = Counter(row["suggested_disposition"] for row in rows)

    generated_at = utc_now_iso()
    payload = {
        "artifact_type": "supplemental_no_coord_human_review_sheet",
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_no_coord_human_review",
        "source_feed": repo_relative(FEED_PATH),
        "row_count": len(rows),
        "rows": rows,
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
    }
    report = {
        "artifact_type": "supplemental_no_coord_human_review_sheet_report",
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_no_coord_human_review",
        "row_count": len(rows),
        "staging_feed_event_count": len(events),
        "staging_feed_with_coordinates_pct": round(
            (
                sum(
                    1
                    for row in events
                    if isinstance(row, dict) and valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))
                )
                / len(events)
            )
            * 100.0,
            2,
        )
        if events
        else 0.0,
        "review_category_counts": dict(category_counts),
        "suggested_disposition_counts": dict(suggested_counts),
        "csv_path": repo_relative(CSV_PATH),
        "json_path": repo_relative(JSON_PATH),
        "qa_pass": len(rows) <= 25,
        "safety": payload["safety"],
        "next_required_step": (
            "Review supplemental_no_coord_human_review_sheet.csv. "
            "Record decisions in supplemental_manual_approval_decisions.json and run "
            "apply_supplemental_manual_approval_decisions.py — or reject permanent non-mappable rows."
        ),
    }

    save_json_file(JSON_PATH, payload)
    write_csv(CSV_PATH, rows, CSV_FIELDS)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
