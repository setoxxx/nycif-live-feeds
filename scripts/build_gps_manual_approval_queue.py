#!/usr/bin/env python3
"""Build Phase 2D manual GPS approval queue.

Reads Phase 2C filled proposals and creates a human-review queue.
This script does not approve, promote, or publish anything.

Outputs:
- data/gps_manual_approval_queue.json
- data/gps_manual_approval_queue_report.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
FILLED_PROPOSALS_PATH = DATA_DIR / "gps_review_geocoding_filled_proposals.json"
APPROVAL_QUEUE_PATH = DATA_DIR / "gps_manual_approval_queue.json"
APPROVAL_QUEUE_REPORT_PATH = DATA_DIR / "gps_manual_approval_queue_report.json"


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


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def approval_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "group_key": row.get("group_key"),
        "priority_score": row.get("priority_score"),
        "event_count": row.get("event_count"),
        "borough": row.get("borough"),
        "display_location": row.get("display_location"),
        "simplified_geocoder_query": row.get("simplified_geocoder_query"),
        "location_complexity": row.get("location_complexity"),
        "proposed_lat": row.get("proposed_lat"),
        "proposed_lng": row.get("proposed_lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_place_id": row.get("geocoder_place_id"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "source_phase": "phase_2c_controlled_geocoder_fill",
        "manual_review_status": "pending",
        "manual_reviewer": None,
        "manual_reviewed_at_utc": None,
        "manual_review_notes": None,
        "approval_decision_reason": None,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def main() -> int:
    payload = load_json_file(FILLED_PROPOSALS_PATH, {})
    proposals = rows_from_payload(payload, "proposals")
    filled = [row for row in proposals if row.get("proposal_status") == "filled_pending_manual_review" and valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))]
    filled.sort(key=lambda row: int(row.get("priority_score") or 0), reverse=True)
    queue = [approval_item(row) for row in filled]

    generated_at = datetime.now(timezone.utc).isoformat()
    source_counts = Counter(row.get("geocoder_source") for row in queue)
    confidence_counts = Counter(row.get("geocoder_confidence") for row in queue)
    borough_counts = Counter(row.get("borough") for row in queue)
    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2d_manual_approval_queue",
        "input_proposal_count": len(proposals),
        "filled_candidates_loaded": len(filled),
        "approval_queue_count": len(queue),
        "approved_count": 0,
        "promotion_allowed_count": 0,
        "source_counts": dict(source_counts),
        "confidence_counts": dict(confidence_counts),
        "borough_counts": dict(borough_counts),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": "Manually review queue rows. Only after manual approval should a separate validator and promotion script be used.",
    }

    save_json_file(APPROVAL_QUEUE_PATH, {"generated_at_utc": generated_at, "approval_queue": queue})
    save_json_file(APPROVAL_QUEUE_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
