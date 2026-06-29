#!/usr/bin/env python3
"""Build a human-readable Phase 2D GPS manual approval review sheet.

This script reads data/gps_manual_approval_queue.json and writes review-only
artifacts for human checking. It does not approve, promote, modify the location
cache, modify the staged feed, or publish anything to the public map.

Outputs:
- data/gps_manual_approval_review_sheet.json
- data/gps_manual_approval_review_sheet.csv
- data/gps_manual_approval_review_sheet_report.json
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APPROVAL_QUEUE_PATH = DATA_DIR / "gps_manual_approval_queue.json"
REVIEW_SHEET_JSON_PATH = DATA_DIR / "gps_manual_approval_review_sheet.json"
REVIEW_SHEET_CSV_PATH = DATA_DIR / "gps_manual_approval_review_sheet.csv"
REVIEW_SHEET_REPORT_PATH = DATA_DIR / "gps_manual_approval_review_sheet_report.json"

CSV_FIELDS = [
    "review_rank",
    "manual_review_status",
    "promotion_allowed",
    "display_location",
    "borough",
    "event_count",
    "priority_score",
    "proposed_lat",
    "proposed_lng",
    "geocoder_source",
    "geocoder_confidence",
    "confidence_reason",
    "google_maps_search_url",
    "google_maps_pin_url",
    "manual_review_notes",
    "approval_decision_reason",
    "manual_reviewer",
    "manual_reviewed_at_utc",
    "group_key",
    "geocoder_place_id",
]


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def maps_query(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("display_location") or "").strip(),
        str(row.get("borough") or "").strip(),
        "New York, NY",
    ]
    return ", ".join(part for part in parts if part)


def google_maps_search_url(row: dict[str, Any]) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(maps_query(row))}"


def google_maps_pin_url(row: dict[str, Any]) -> str:
    lat = row.get("proposed_lat")
    lng = row.get("proposed_lng")
    if lat is None or lng is None:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(str(lat) + ',' + str(lng))}"


def review_item(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "review_rank": rank,
        "manual_review_status": row.get("manual_review_status") or "pending",
        "promotion_allowed": False,
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "event_count": row.get("event_count"),
        "priority_score": row.get("priority_score"),
        "proposed_lat": row.get("proposed_lat"),
        "proposed_lng": row.get("proposed_lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "google_maps_search_url": google_maps_search_url(row),
        "google_maps_pin_url": google_maps_pin_url(row),
        "manual_review_notes": row.get("manual_review_notes") or "",
        "approval_decision_reason": row.get("approval_decision_reason") or "",
        "manual_reviewer": row.get("manual_reviewer") or "",
        "manual_reviewed_at_utc": row.get("manual_reviewed_at_utc") or "",
        "group_key": row.get("group_key"),
        "geocoder_place_id": row.get("geocoder_place_id"),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(payload, "approval_queue")
    queue.sort(key=lambda row: int(row.get("priority_score") or 0), reverse=True)
    review_rows = [review_item(row, index + 1) for index, row in enumerate(queue)]

    generated_at = datetime.now(timezone.utc).isoformat()
    borough_counts = Counter(row.get("borough") or "unknown" for row in review_rows)
    confidence_counts = Counter(row.get("geocoder_confidence") or "unknown" for row in review_rows)
    status_counts = Counter(row.get("manual_review_status") or "unknown" for row in review_rows)
    source_counts = Counter(row.get("geocoder_source") or "unknown" for row in review_rows)
    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2d_manual_approval_review_sheet",
        "review_sheet_count": len(review_rows),
        "status_counts": dict(status_counts),
        "borough_counts": dict(borough_counts),
        "confidence_counts": dict(confidence_counts),
        "source_counts": dict(source_counts),
        "promotion_allowed_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "json_output": str(REVIEW_SHEET_JSON_PATH.relative_to(ROOT)),
        "csv_output": str(REVIEW_SHEET_CSV_PATH.relative_to(ROOT)),
        "next_required_step": "Manually inspect search/pin URLs. Do not approve or promote from this sheet directly; update the approval queue in a separate reviewed commit when ready.",
    }

    save_json_file(REVIEW_SHEET_JSON_PATH, {"generated_at_utc": generated_at, "review_sheet": review_rows})
    write_csv(REVIEW_SHEET_CSV_PATH, review_rows)
    save_json_file(REVIEW_SHEET_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
