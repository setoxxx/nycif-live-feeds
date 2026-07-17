#!/usr/bin/env python3
"""Build field-desk preview feed from approved supplemental queue rows only.

Does NOT modify location_cache.json, permit staged feed, or public map feeds.
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
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_approved_export_feed_report.json"


def queue_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("approval_queue"), list):
        return [row for row in payload["approval_queue"] if isinstance(row, dict)]
    return []


def export_event(row: dict[str, Any]) -> dict[str, Any]:
    lat = row.get("proposed_lat")
    lng = row.get("proposed_lng")
    return {
        "overlap_key": row.get("overlap_key"),
        "title": row.get("title"),
        "start_date_time": row.get("start_date_time"),
        "date": row.get("date"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "lat": float(lat) if lat is not None else None,
        "lng": float(lng) if lng is not None else None,
        "proposed_lat": float(lat) if lat is not None else None,
        "proposed_lng": float(lng) if lng is not None else None,
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "intake_type": row.get("intake_type"),
        "source_dataset": row.get("source_dataset"),
        "source_event_id": row.get("source_event_id"),
        "manual_review_status": "approved",
        "manual_reviewer": row.get("manual_reviewer"),
        "manual_reviewed_at_utc": row.get("manual_reviewed_at_utc"),
        "approval_decision_reason": row.get("approval_decision_reason"),
        "production_feed": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def build_export_payload(queue: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    approved = [row for row in queue if str(row.get("manual_review_status") or "").lower() == "approved"]
    with_coords = [row for row in approved if valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))]
    skipped = len(approved) - len(with_coords)
    events = [export_event(row) for row in with_coords]
    events.sort(key=lambda row: (row.get("date") or "", row.get("start_date_time") or "", row.get("title") or ""))
    generated_at = utc_now_iso()
    intake_counts = Counter(row.get("intake_type") for row in with_coords)
    payload = {
        "artifact_type": "supplemental_approved_export_feed",
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_approved_export",
        "production_feed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "source_queue_path": repo_relative(APPROVAL_QUEUE_PATH),
        "approved_queue_count": len(approved),
        "export_event_count": len(events),
        "skipped_approved_without_coordinates": skipped,
        "events": events,
    }
    report = {
        "artifact_type": "supplemental_approved_export_feed_report",
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_approved_export",
        "qa_pass": len(events) > 0 and skipped == 0,
        "approved_queue_count": len(approved),
        "export_event_count": len(events),
        "skipped_approved_without_coordinates": skipped,
        "intake_counts": dict(intake_counts),
        "export_path": repo_relative(EXPORT_PATH),
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Field-desk preview only. Public map merge and location_cache promotion "
            "require explicit Phase 2E authorization."
        ),
    }
    return payload, report


def main() -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = queue_rows(payload)
    export_payload, report = build_export_payload(queue)
    save_json_file(EXPORT_PATH, export_payload)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("qa_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
