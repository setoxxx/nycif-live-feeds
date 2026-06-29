#!/usr/bin/env python3
"""Build Phase 2D GPS manual approval staging candidates.

This script reads Claude/Howard reviewed GPS findings and the manual review
sheet, then creates a staging-only approval-candidate artifact.

It does not approve rows, does not set promotion_allowed true, does not update
location_cache.json, does not update the staged feed, and does not publish to
the public map.

Inputs:
- data/gps_manual_approval_review_sheet.json
- data/gps_manual_approval_review_findings.json

Outputs:
- data/gps_manual_approval_staging_candidates.json
- data/gps_manual_approval_staging_report.json
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
REVIEW_SHEET_PATH = DATA_DIR / "gps_manual_approval_review_sheet.json"
FINDINGS_PATH = DATA_DIR / "gps_manual_approval_review_findings.json"
STAGING_PATH = DATA_DIR / "gps_manual_approval_staging_candidates.json"
REPORT_PATH = DATA_DIR / "gps_manual_approval_staging_report.json"


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


def finding_lookup(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    output: dict[int, dict[str, Any]] = {}
    for item in items:
        try:
            rank = int(item.get("review_rank"))
        except Exception:
            continue
        output[rank] = item
    return output


def make_candidate(row: dict[str, Any], review_source: str) -> dict[str, Any]:
    return {
        "review_rank": row.get("review_rank"),
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "event_count": row.get("event_count"),
        "priority_score": row.get("priority_score"),
        "proposed_lat": row.get("proposed_lat"),
        "proposed_lng": row.get("proposed_lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "review_source": review_source,
        "reviewer_source": review_source,
        "recommended_action": "approval_candidate_pending_human_confirmation",
        "candidate_reason": "Claude manual GPS review recommended this row for approval. Human approval still required before any promotion.",
        "manual_review_status": "pending",
        "manual_reviewer": "",
        "manual_reviewed_at_utc": "",
        "manual_review_notes": "Recommended approval candidate from reviewed findings; not approved in Phase 2D staging.",
        "approval_decision_reason": "",
        "approval_candidate": True,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def make_excluded(row: dict[str, Any], reason: str, correction: dict[str, Any] | None, hard_error: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "review_rank": row.get("review_rank"),
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "event_count": row.get("event_count"),
        "current_lat": row.get("proposed_lat"),
        "current_lng": row.get("proposed_lng"),
        "excluded_reason": reason,
        "correction_issue": (correction or {}).get("issue"),
        "corrected_lat": (correction or {}).get("corrected_lat"),
        "corrected_lng": (correction or {}).get("corrected_lng"),
        "hard_error_issue": (hard_error or {}).get("issue"),
        "recommended_action": (correction or hard_error or {}).get("recommended_action") or "do_not_approve_in_current_staging",
        "manual_review_status": "pending",
        "approval_candidate": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def main() -> int:
    review_sheet_payload = load_json_file(REVIEW_SHEET_PATH, {})
    findings = load_json_file(FINDINGS_PATH, {})
    review_rows = rows_from_payload(review_sheet_payload, "review_sheet")

    rows_by_rank: dict[int, dict[str, Any]] = {}
    for row in review_rows:
        try:
            rank = int(row.get("review_rank"))
        except Exception:
            continue
        rows_by_rank[rank] = row

    approve_ranks = [int(rank) for rank in findings.get("recommended_approve_rows", [])]
    reject_ranks = [int(rank) for rank in findings.get("do_not_approve_rows", [])]
    correction_by_rank = finding_lookup(rows_from_payload(findings, "corrections_needed"))
    hard_error_by_rank = finding_lookup(rows_from_payload(findings, "hard_errors"))
    review_source = findings.get("review_source") or "manual GPS review findings"

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    missing_approve_rows: list[int] = []
    missing_reject_rows: list[int] = []

    for rank in approve_ranks:
        row = rows_by_rank.get(rank)
        if not row:
            missing_approve_rows.append(rank)
            continue
        candidate = make_candidate(row, review_source)
        if not valid_nyc_lat_lng(candidate.get("proposed_lat"), candidate.get("proposed_lng")):
            excluded.append(make_excluded(row, "invalid_nyc_coordinates", None, None))
            continue
        candidates.append(candidate)

    for rank in reject_ranks:
        row = rows_by_rank.get(rank)
        if not row:
            missing_reject_rows.append(rank)
            continue
        correction = correction_by_rank.get(rank)
        hard_error = hard_error_by_rank.get(rank)
        reason = "do_not_approve_from_reviewed_findings"
        if hard_error:
            reason = "hard_error_excluded_from_approval_staging"
        elif correction:
            reason = "correction_needed_excluded_from_approval_staging"
        excluded.append(make_excluded(row, reason, correction, hard_error))

    generated_at = datetime.now(timezone.utc).isoformat()
    borough_counts = Counter(row.get("borough") or "unknown" for row in candidates)
    confidence_counts = Counter(row.get("geocoder_confidence") or "unknown" for row in candidates)
    staging_payload = {
        "generated_at_utc": generated_at,
        "phase": "phase_2d_approval_staging",
        "review_source": review_source,
        "approval_candidates": candidates,
        "excluded_rows": excluded,
        "safety_contract": {
            "manual_review_status_set_to_approved": False,
            "promotion_allowed_set_true": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "promotion_performed": False,
        },
    }
    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2d_approval_staging",
        "review_source": review_source,
        "review_sheet_rows_loaded": len(review_rows),
        "recommended_approve_rows_from_findings": len(approve_ranks),
        "do_not_approve_rows_from_findings": len(reject_ranks),
        "approval_candidate_count": len(candidates),
        "excluded_row_count": len(excluded),
        "hard_error_excluded_count": len(hard_error_by_rank),
        "correction_needed_excluded_count": len(correction_by_rank),
        "missing_approve_rows": missing_approve_rows,
        "missing_reject_rows": missing_reject_rows,
        "candidate_borough_counts": dict(borough_counts),
        "candidate_confidence_counts": dict(confidence_counts),
        "manual_review_status_set_to_approved": False,
        "promotion_allowed_count": 0,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "promotion_performed": False,
        "ready_for_phase_2e_promotion_count": 0,
        "qa_pass": len(candidates) == 25 and len(excluded) == 17 and not missing_approve_rows and not missing_reject_rows,
        "next_required_step": "Inspect this staging artifact. Only after human confirmation should a separate approval patch mark selected rows approved; do not run Phase 2E promotion yet.",
    }

    save_json_file(STAGING_PATH, staging_payload)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
