#!/usr/bin/env python3
"""Build Phase 2D GPS manual approval staging candidates.

This script reads Claude/Howard reviewed GPS findings and the manual review
sheet, then creates a staging-only approval-candidate artifact.

It uses stable identity matching. Rank-only findings are not trusted because
review_rank can shift when the review sheet regenerates.

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
import re
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


def norm_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_key(row: dict[str, Any]) -> str:
    group_key = str(row.get("group_key") or "").strip().lower()
    if group_key:
        return f"group:{group_key}"
    return f"display:{norm_text(row.get('display_location'))}"


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def build_finding_exclusions(findings: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Claude-reviewed rows that must not become approval candidates.

    The reviewed findings file records all 17 rejected/correction-needed rows
    in corrections_needed, with the two hard errors also duplicated in
    hard_errors. Use these stable display locations as the source of truth.
    """
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rows_from_payload(findings, "corrections_needed"):
        display_key = norm_text(item.get("display_location"))
        if not display_key or display_key in seen:
            continue
        seen.add(display_key)
        merged = dict(item)
        merged["stable_display_key"] = display_key
        merged["finding_source_section"] = "corrections_needed"
        output.append(merged)
    return output


def match_exclusion(row: dict[str, Any], exclusions: list[dict[str, Any]]) -> dict[str, Any] | None:
    row_display_key = norm_text(row.get("display_location"))
    for item in exclusions:
        item_display_key = item.get("stable_display_key") or norm_text(item.get("display_location"))
        if not item_display_key:
            continue
        if row_display_key == item_display_key:
            return item
    return None


def make_candidate(row: dict[str, Any], review_source: str) -> dict[str, Any]:
    return {
        "review_rank_current": row.get("review_rank"),
        "stable_identity_key": stable_key(row),
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
        "candidate_reason": "Not present in Claude's stable correction/reject list. Human approval still required before any promotion.",
        "manual_review_status": "pending",
        "manual_reviewer": "",
        "manual_reviewed_at_utc": "",
        "manual_review_notes": "Approval candidate by stable identity matching; not approved in Phase 2D staging.",
        "approval_decision_reason": "",
        "approval_candidate": True,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def make_excluded(row: dict[str, Any], finding: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "review_rank_current": row.get("review_rank"),
        "review_rank_original_from_findings": finding.get("review_rank"),
        "stable_identity_key": stable_key(row),
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "event_count": row.get("event_count"),
        "current_lat": row.get("proposed_lat"),
        "current_lng": row.get("proposed_lng"),
        "excluded_reason": reason,
        "correction_issue": finding.get("issue"),
        "corrected_lat": finding.get("corrected_lat"),
        "corrected_lng": finding.get("corrected_lng"),
        "recommended_action": finding.get("recommended_action") or "do_not_approve_in_current_staging",
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
    review_source = findings.get("review_source") or "manual GPS review findings"
    exclusions_from_findings = build_finding_exclusions(findings)

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    invalid_coordinate_rows: list[dict[str, Any]] = []

    for row in review_rows:
        finding = match_exclusion(row, exclusions_from_findings)
        if finding:
            reason = "stable_finding_exclusion"
            if finding.get("recommended_action", "").startswith("replace_with_correct"):
                reason = "stable_hard_or_correction_exclusion"
            excluded.append(make_excluded(row, finding, reason))
            continue

        candidate = make_candidate(row, review_source)
        if not valid_nyc_lat_lng(candidate.get("proposed_lat"), candidate.get("proposed_lng")):
            invalid_coordinate_rows.append(candidate)
            excluded.append(
                {
                    **candidate,
                    "excluded_reason": "invalid_nyc_coordinates",
                    "approval_candidate": False,
                }
            )
            continue
        candidates.append(candidate)

    excluded_display_keys = {norm_text(row.get("display_location")) for row in excluded}
    missing_stable_exclusions = [
        {
            "review_rank_original_from_findings": item.get("review_rank"),
            "display_location": item.get("display_location"),
            "stable_display_key": item.get("stable_display_key"),
        }
        for item in exclusions_from_findings
        if item.get("stable_display_key") not in excluded_display_keys
    ]
    baisley_in_candidates = any("baisley pond park" in norm_text(row.get("display_location")) for row in candidates)
    baisley_in_excluded = any("baisley pond park" in norm_text(row.get("display_location")) for row in excluded)
    generated_at = datetime.now(timezone.utc).isoformat()
    borough_counts = Counter(row.get("borough") or "unknown" for row in candidates)
    confidence_counts = Counter(row.get("geocoder_confidence") or "unknown" for row in candidates)

    qa_pass = (
        len(review_rows) == 42
        and len(candidates) == 25
        and len(excluded) == 17
        and len(exclusions_from_findings) == 17
        and not missing_stable_exclusions
        and not invalid_coordinate_rows
        and not baisley_in_candidates
        and baisley_in_excluded
    )

    staging_payload = {
        "generated_at_utc": generated_at,
        "phase": "phase_2d_approval_staging_stable_identity",
        "review_source": review_source,
        "identity_matching": "stable_display_location_from_review_findings; review_rank_current is informational only",
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
        "phase": "phase_2d_approval_staging_stable_identity",
        "review_source": review_source,
        "identity_matching": "stable_display_location_from_review_findings; review_rank_current is informational only",
        "review_sheet_rows_loaded": len(review_rows),
        "stable_exclusions_from_findings": len(exclusions_from_findings),
        "approval_candidate_count": len(candidates),
        "excluded_row_count": len(excluded),
        "missing_stable_exclusions": missing_stable_exclusions,
        "invalid_coordinate_count": len(invalid_coordinate_rows),
        "baisley_in_candidates": baisley_in_candidates,
        "baisley_in_excluded": baisley_in_excluded,
        "candidate_borough_counts": dict(borough_counts),
        "candidate_confidence_counts": dict(confidence_counts),
        "manual_review_status_set_to_approved": False,
        "promotion_allowed_count": 0,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "promotion_performed": False,
        "ready_for_phase_2e_promotion_count": 0,
        "qa_pass": qa_pass,
        "next_required_step": "Inspect this stable-identity staging artifact. Only after human confirmation should a separate approval patch mark selected rows approved; do not run Phase 2E promotion yet.",
    }

    save_json_file(STAGING_PATH, staging_payload)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
