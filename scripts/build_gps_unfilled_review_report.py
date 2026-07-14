#!/usr/bin/env python3
"""Build review artifacts for unfilled Phase 2C GPS geocoding proposals.

Reads data/gps_review_geocoding_filled_proposals.json and writes a breakdown
report plus human-review queue/CSV for rows still missing coordinates.

Does NOT approve, promote, or modify location_cache.json or staged feeds.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        repo_relative,
        safety_fields,
        save_json_file,
        simplified_place,
        utc_now_iso,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from coverage_gap_utils import (
        DATA_DIR,
        google_maps_pin_url,
        google_maps_search_url,
        load_json_file,
        repo_relative,
        safety_fields,
        save_json_file,
        simplified_place,
        utc_now_iso,
        write_csv,
    )

FILLED_PROPOSALS_PATH = DATA_DIR / "gps_review_geocoding_filled_proposals.json"
UNFILLED_REPORT_PATH = DATA_DIR / "gps_review_geocoding_unfilled_report.json"
UNFILLED_QUEUE_JSON = DATA_DIR / "gps_review_geocoding_unfilled_review_queue.json"
UNFILLED_QUEUE_CSV = DATA_DIR / "gps_review_geocoding_unfilled_review_queue.csv"
MANUAL_REFERENCE_TEMPLATE_PATH = DATA_DIR / "manual_gps_reference.template.json"

CSV_FIELDS = [
    "review_rank",
    "group_key",
    "display_location",
    "borough",
    "event_count",
    "priority_score",
    "location_complexity",
    "simplified_geocoder_query",
    "review_guidance",
    "google_maps_search_url",
    "manual_lat",
    "manual_lng",
    "manual_review_status",
    "promotion_allowed",
    "manual_review_notes",
    "approval_decision_reason",
]


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def review_guidance(row: dict[str, Any]) -> str:
    complexity = str(row.get("location_complexity") or "unknown")
    if complexity == "street_between_pair":
        return (
            "Open street segment between two cross streets. Add a midpoint coordinate to "
            "data/manual_gps_reference.json after field verification, then re-run Phase 2C fill."
        )
    if complexity == "park_or_facility_subsite":
        return (
            "Park or facility subsite. Check NYC Parks BigApps facility reference or verify "
            "the parent park pin manually before adding to manual_gps_reference.json."
        )
    return "Verify location manually and add to manual_gps_reference.json if appropriate."


def manual_reference_template(rows: list[dict[str, Any]]) -> dict[str, Any]:
    references = []
    for row in rows:
        references.append(
            {
                "group_key": row.get("group_key"),
                "display_location": row.get("display_location"),
                "borough": row.get("borough"),
                "location_complexity": row.get("location_complexity"),
                "simplified_geocoder_query": row.get("simplified_geocoder_query"),
                "lat": None,
                "lng": None,
                "geocoder_source": "manual_human_reference",
                "geocoder_confidence": None,
                "confidence_reason": "Fill after field verification. Do not commit real coordinates without review.",
                "manual_review_status": "pending",
                "promotion_allowed": False,
            }
        )
    return {
        "artifact_type": "manual_gps_reference_template",
        "generated_at_utc": utc_now_iso(),
        "instructions": [
            "Copy verified rows into data/manual_gps_reference.json with lat/lng filled.",
            "Re-run scripts/build_gps_geocoding_filled_proposals.py after updating manual reference.",
            "Do not set promotion_allowed=true here; use Phase 2D/2E workflows after manual approval.",
        ],
        "references": references,
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
        },
    }


def queue_item(row: dict[str, Any], rank: int) -> dict[str, Any]:
    item = {
        "review_rank": rank,
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "event_count": row.get("event_count"),
        "priority_score": row.get("priority_score"),
        "location_complexity": row.get("location_complexity"),
        "simplified_geocoder_query": row.get("simplified_geocoder_query"),
        "review_guidance": review_guidance(row),
        "google_maps_search_url": google_maps_search_url(
            row.get("display_location") or row.get("simplified_geocoder_query"),
            str(row.get("borough") or ""),
        ),
        "manual_lat": None,
        "manual_lng": None,
        "reference_place_key": simplified_place(
            str(row.get("display_location") or row.get("simplified_geocoder_query") or "")
        ),
    }
    item.update(safety_fields())
    return item


def main() -> int:
    payload = load_json_file(FILLED_PROPOSALS_PATH, {})
    proposals = rows_from_payload(payload, "proposals")
    unfilled = [
        row for row in proposals if row.get("proposal_status") == "unfilled_pending_geocoder"
    ]
    unfilled.sort(key=lambda row: int(row.get("priority_score") or 0), reverse=True)
    queue = [queue_item(row, index + 1) for index, row in enumerate(unfilled)]

    generated_at = utc_now_iso()
    complexity_counts = Counter(row.get("location_complexity") or "unknown" for row in unfilled)
    borough_counts = Counter(row.get("borough") or "unknown" for row in unfilled)

    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2c_unfilled_gps_review",
        "input_proposal_count": len(proposals),
        "unfilled_count": len(unfilled),
        "complexity_counts": dict(complexity_counts),
        "borough_counts": dict(borough_counts),
        "street_between_pair_count": complexity_counts.get("street_between_pair", 0),
        "park_or_facility_subsite_count": complexity_counts.get("park_or_facility_subsite", 0),
        "promotion_allowed_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "json_output": repo_relative(UNFILLED_QUEUE_JSON),
        "csv_output": repo_relative(UNFILLED_QUEUE_CSV),
        "manual_reference_template": repo_relative(MANUAL_REFERENCE_TEMPLATE_PATH),
        "next_required_step": (
            "Review unfilled rows in CSV. Add verified coordinates to manual_gps_reference.json, "
            "then re-run build_gps_geocoding_filled_proposals.py."
        ),
    }

    save_json_file(UNFILLED_REPORT_PATH, report)
    save_json_file(UNFILLED_QUEUE_JSON, {"generated_at_utc": generated_at, "review_queue": queue})
    write_csv(UNFILLED_QUEUE_CSV, queue, CSV_FIELDS)
    save_json_file(MANUAL_REFERENCE_TEMPLATE_PATH, manual_reference_template(unfilled))

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
