#!/usr/bin/env python3
"""Build Phase 2D reviewed GPS approval artifact.

This script reads stable approval-staging candidates and writes a reviewed
approval artifact for the 25 stable candidates only.

This is not Phase 2E promotion. It does not write to location_cache.json, does
not modify the staged feed, and does not publish anything to the public map.

Inputs:
- data/gps_manual_approval_staging_candidates.json
- data/gps_manual_approval_staging_report.json

Outputs:
- data/gps_reviewed_approval_artifact.json
- data/gps_reviewed_approval_artifact_report.json
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
STAGING_PATH = DATA_DIR / "gps_manual_approval_staging_candidates.json"
STAGING_REPORT_PATH = DATA_DIR / "gps_manual_approval_staging_report.json"
APPROVAL_PATH = DATA_DIR / "gps_reviewed_approval_artifact.json"
REPORT_PATH = DATA_DIR / "gps_reviewed_approval_artifact_report.json"
MANUAL_REVIEWER = "Howard Weiss"


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


def approval_row(candidate: dict[str, Any], reviewed_at_utc: str) -> dict[str, Any]:
    reason = candidate.get("candidate_reason") or "Stable Phase 2D approval candidate; human reviewed for approval artifact."
    return {
        "stable_identity_key": candidate.get("stable_identity_key"),
        "group_key": candidate.get("group_key"),
        "display_location": candidate.get("display_location"),
        "borough": candidate.get("borough"),
        "event_count": candidate.get("event_count"),
        "priority_score": candidate.get("priority_score"),
        "proposed_lat": candidate.get("proposed_lat"),
        "proposed_lng": candidate.get("proposed_lng"),
        "geocoder_source": candidate.get("geocoder_source"),
        "geocoder_confidence": candidate.get("geocoder_confidence"),
        "confidence_reason": candidate.get("confidence_reason"),
        "manual_review_status": "approved",
        "manual_reviewer": MANUAL_REVIEWER,
        "manual_reviewed_at_utc": reviewed_at_utc,
        "manual_review_notes": "Approved in Phase 2D reviewed approval artifact from stable approval-staging candidates. This is not promotion.",
        "approval_decision_reason": reason,
        "approval_candidate": True,
        "promotion_allowed": True,
        "promotion_scope": "reviewed_approval_artifact_only",
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "phase_2e_promotion_performed": False,
    }


def main() -> int:
    staging = load_json_file(STAGING_PATH, {})
    staging_report = load_json_file(STAGING_REPORT_PATH, {})
    candidates = rows_from_payload(staging, "approval_candidates")
    excluded = rows_from_payload(staging, "excluded_rows")
    reviewed_at_utc = datetime.now(timezone.utc).isoformat()

    approved_rows = [approval_row(candidate, reviewed_at_utc) for candidate in candidates]
    invalid_approved_rows = [
        row for row in approved_rows if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))
    ]
    missing_required_rows = [
        row
        for row in approved_rows
        if not row.get("stable_identity_key")
        or not row.get("display_location")
        or not row.get("geocoder_source")
        or not row.get("confidence_reason")
        or row.get("manual_review_status") != "approved"
        or row.get("manual_reviewer") != MANUAL_REVIEWER
        or not row.get("manual_reviewed_at_utc")
        or not row.get("approval_decision_reason")
        or row.get("promotion_allowed") is not True
    ]
    approved_identity_keys = {row.get("stable_identity_key") for row in approved_rows}
    excluded_identity_keys = {row.get("stable_identity_key") for row in excluded}
    overlap_with_excluded = sorted(key for key in approved_identity_keys.intersection(excluded_identity_keys) if key)
    borough_counts = Counter(row.get("borough") or "unknown" for row in approved_rows)
    confidence_counts = Counter(row.get("geocoder_confidence") or "unknown" for row in approved_rows)
    source_counts = Counter(row.get("geocoder_source") or "unknown" for row in approved_rows)

    qa_pass = (
        staging_report.get("qa_pass") is True
        and staging_report.get("phase") == "phase_2d_approval_staging_stable_identity"
        and len(approved_rows) == 25
        and len(excluded) == 17
        and len(invalid_approved_rows) == 0
        and len(missing_required_rows) == 0
        and len(overlap_with_excluded) == 0
    )

    payload = {
        "generated_at_utc": reviewed_at_utc,
        "phase": "phase_2d_reviewed_approval_artifact",
        "review_source": staging.get("review_source"),
        "manual_reviewer": MANUAL_REVIEWER,
        "manual_reviewed_at_utc": reviewed_at_utc,
        "approved_rows": approved_rows,
        "excluded_rows_carried_forward": excluded,
        "safety_contract": {
            "promotion_allowed_true_scope": "approved_rows inside gps_reviewed_approval_artifact.json only",
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "phase_2e_promotion_performed": False,
        },
    }
    report = {
        "generated_at_utc": reviewed_at_utc,
        "phase": "phase_2d_reviewed_approval_artifact",
        "manual_reviewer": MANUAL_REVIEWER,
        "manual_reviewed_at_utc": reviewed_at_utc,
        "staging_report_phase": staging_report.get("phase"),
        "staging_report_qa_pass": staging_report.get("qa_pass"),
        "approved_count": len(approved_rows),
        "excluded_carried_forward_count": len(excluded),
        "promotion_allowed_true_count": sum(1 for row in approved_rows if row.get("promotion_allowed") is True),
        "promotion_allowed_scope": "reviewed_approval_artifact_only",
        "invalid_approved_count": len(invalid_approved_rows),
        "missing_required_count": len(missing_required_rows),
        "overlap_with_excluded_count": len(overlap_with_excluded),
        "overlap_with_excluded": overlap_with_excluded,
        "approved_borough_counts": dict(borough_counts),
        "approved_confidence_counts": dict(confidence_counts),
        "approved_source_counts": dict(source_counts),
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "phase_2e_promotion_performed": False,
        "ready_for_phase_2e_input_count": len(approved_rows) if qa_pass else 0,
        "qa_pass": qa_pass,
        "next_required_step": "Inspect this reviewed approval artifact. Phase 2E promotion remains separate and must not run until explicitly authorized.",
    }

    save_json_file(APPROVAL_PATH, payload)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
