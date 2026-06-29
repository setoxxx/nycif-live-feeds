#!/usr/bin/env python3
"""Build Phase 2B staging-only GPS geocoding proposals.

This script does not call a geocoder, does not modify location_cache.json,
does not modify the staged/public feed, and does not publish to the map.

It prepares the safest top repeated review-candidate groups for a later
manual/API geocoding pass.

Outputs:
- data/gps_review_geocoding_proposals.json
- data/gps_review_geocoding_proposal_report.json
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
QUEUE_PATH = DATA_DIR / "gps_review_geocoding_queue.json"
GROUP_REPORT_PATH = DATA_DIR / "gps_review_group_report.json"
PROPOSALS_PATH = DATA_DIR / "gps_review_geocoding_proposals.json"
PROPOSAL_REPORT_PATH = DATA_DIR / "gps_review_geocoding_proposal_report.json"
DEFAULT_LIMIT = 50


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


def valid_queue_item(row: dict[str, Any]) -> bool:
    return (
        row.get("confidence_hint") in {"good_candidate", "review_candidate"}
        and row.get("location_complexity") != "multi_segment_corridor"
        and bool(row.get("display_location"))
        and bool(row.get("borough"))
    )


def main() -> int:
    limit = int(os.environ.get("GPS_PROPOSAL_LIMIT", DEFAULT_LIMIT))
    queue_payload = load_json_file(QUEUE_PATH, {})
    queue = queue_payload.get("queue") if isinstance(queue_payload, dict) else []
    queue = [row for row in queue if isinstance(row, dict)]
    safe_candidates = [row for row in queue if valid_queue_item(row)]
    safe_candidates.sort(key=lambda row: int(row.get("priority_score") or 0), reverse=True)
    selected = safe_candidates[:limit]

    generated_at = datetime.now(timezone.utc).isoformat()
    proposals: list[dict[str, Any]] = []
    for row in selected:
        proposals.append({
            "group_key": row.get("group_key"),
            "priority_score": row.get("priority_score"),
            "event_count": row.get("event_count"),
            "borough": row.get("borough"),
            "display_location": row.get("display_location"),
            "geocoder_query": row.get("geocoder_query"),
            "simplified_geocoder_query": row.get("simplified_geocoder_query") or row.get("geocoder_query"),
            "confidence_hint": row.get("confidence_hint"),
            "location_complexity": row.get("location_complexity"),
            "proposal_status": "ready_for_manual_or_api_geocoding",
            "proposed_lat": None,
            "proposed_lng": None,
            "geocoder_source": None,
            "geocoder_place_id": None,
            "geocoder_confidence": None,
            "confidence_reason": None,
            "manual_review_status": "pending",
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
        })

    complexity_counts = Counter(row.get("location_complexity") for row in proposals)
    borough_counts = Counter(row.get("borough") for row in proposals)
    group_report = load_json_file(GROUP_REPORT_PATH, {})
    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2b_controlled_geocoding_proposal",
        "queue_items_loaded": len(queue),
        "safe_candidates_loaded": len(safe_candidates),
        "proposal_limit": limit,
        "proposal_count": len(proposals),
        "input_review_events": group_report.get("input_review_events") if isinstance(group_report, dict) else None,
        "unique_location_groups": group_report.get("unique_location_groups") if isinstance(group_report, dict) else None,
        "proposal_complexity_counts": dict(complexity_counts),
        "proposal_borough_counts": dict(borough_counts),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed_count": 0,
        "next_required_step": "Run a manual/API geocoder against gps_review_geocoding_proposals.json and write proposed_lat/proposed_lng plus source/confidence fields. Do not promote until manually approved.",
    }

    save_json_file(PROPOSALS_PATH, {"generated_at_utc": generated_at, "proposals": proposals})
    save_json_file(PROPOSAL_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
