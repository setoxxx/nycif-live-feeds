#!/usr/bin/env python3
"""Validate Phase 2E GPS promotion readiness without promoting.

This script is design/readiness only. It reads the Phase 2D reviewed approval
artifact and writes a readiness report. It does not modify location_cache.json,
does not modify the staged feed, does not publish anything to the public map,
and does not run Phase 2E promotion.

Inputs:
- data/gps_reviewed_approval_artifact.json
- data/gps_reviewed_approval_artifact_report.json

Output:
- data/gps_phase2e_promotion_readiness_report.json
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
ARTIFACT_PATH = DATA_DIR / "gps_reviewed_approval_artifact.json"
ARTIFACT_REPORT_PATH = DATA_DIR / "gps_reviewed_approval_artifact_report.json"
READINESS_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_readiness_report.json"
EXPECTED_APPROVED_COUNT = 25
EXPECTED_EXCLUDED_COUNT = 17
EXPECTED_REVIEWER = "Howard Weiss"


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


def missing_required_fields(row: dict[str, Any]) -> list[str]:
    required = [
        "stable_identity_key",
        "group_key",
        "display_location",
        "borough",
        "proposed_lat",
        "proposed_lng",
        "geocoder_source",
        "geocoder_confidence",
        "confidence_reason",
        "manual_reviewer",
        "manual_reviewed_at_utc",
        "approval_decision_reason",
    ]
    return [field for field in required if row.get(field) in (None, "")]


def validate_approved_row(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in missing_required_fields(row):
        issues.append(f"missing_required_field:{field}")
    if row.get("manual_review_status") != "approved":
        issues.append("manual_review_status_not_approved")
    if row.get("manual_reviewer") != EXPECTED_REVIEWER:
        issues.append("manual_reviewer_mismatch")
    if row.get("promotion_allowed") is not True:
        issues.append("promotion_allowed_not_true")
    if row.get("promotion_scope") != "reviewed_approval_artifact_only":
        issues.append("promotion_scope_invalid")
    if row.get("location_cache_modified") is not False:
        issues.append("location_cache_modified_not_false")
    if row.get("staged_feed_modified") is not False:
        issues.append("staged_feed_modified_not_false")
    if row.get("public_map_modified") is not False:
        issues.append("public_map_modified_not_false")
    if row.get("phase_2e_promotion_performed") is not False:
        issues.append("phase_2e_promotion_performed_not_false")
    if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
        issues.append("invalid_nyc_coordinates")
    return issues


def main() -> int:
    artifact = load_json_file(ARTIFACT_PATH, {})
    artifact_report = load_json_file(ARTIFACT_REPORT_PATH, {})
    approved_rows = rows_from_payload(artifact, "approved_rows")
    excluded_rows = rows_from_payload(artifact, "excluded_rows_carried_forward")
    generated_at = datetime.now(timezone.utc).isoformat()

    row_issues = []
    for index, row in enumerate(approved_rows, start=1):
        issues = validate_approved_row(row)
        if issues:
            row_issues.append(
                {
                    "row_index": index,
                    "stable_identity_key": row.get("stable_identity_key"),
                    "display_location": row.get("display_location"),
                    "issues": issues,
                }
            )

    approved_keys = {row.get("stable_identity_key") for row in approved_rows if row.get("stable_identity_key")}
    excluded_keys = {row.get("stable_identity_key") for row in excluded_rows if row.get("stable_identity_key")}
    duplicate_approved_keys = [
        key for key, count in Counter(row.get("stable_identity_key") for row in approved_rows).items() if key and count > 1
    ]
    overlap_with_excluded = sorted(approved_keys.intersection(excluded_keys))
    promotion_allowed_true_count = sum(1 for row in approved_rows if row.get("promotion_allowed") is True)
    borough_counts = Counter(row.get("borough") or "unknown" for row in approved_rows)
    confidence_counts = Counter(row.get("geocoder_confidence") or "unknown" for row in approved_rows)
    source_counts = Counter(row.get("geocoder_source") or "unknown" for row in approved_rows)

    top_level_checks = {
        "artifact_phase_ok": artifact.get("phase") == "phase_2d_reviewed_approval_artifact",
        "artifact_report_phase_ok": artifact_report.get("phase") == "phase_2d_reviewed_approval_artifact",
        "artifact_report_qa_pass": artifact_report.get("qa_pass") is True,
        "approved_count_ok": len(approved_rows) == EXPECTED_APPROVED_COUNT,
        "excluded_count_ok": len(excluded_rows) == EXPECTED_EXCLUDED_COUNT,
        "promotion_allowed_true_count_ok": promotion_allowed_true_count == EXPECTED_APPROVED_COUNT,
        "no_row_issues": len(row_issues) == 0,
        "no_duplicate_approved_keys": len(duplicate_approved_keys) == 0,
        "no_overlap_with_excluded": len(overlap_with_excluded) == 0,
        "source_not_marked_promoted": artifact_report.get("phase_2e_promotion_performed") is False,
        "location_cache_not_modified": artifact_report.get("location_cache_modified") is False,
        "staged_feed_not_modified": artifact_report.get("staged_feed_modified") is False,
        "public_map_not_modified": artifact_report.get("public_map_modified") is False,
    }
    readiness_pass = all(top_level_checks.values())

    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2e_promotion_readiness_validation",
        "readiness_pass": readiness_pass,
        "promotion_performed": False,
        "promotion_script_executed": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "input_artifact": str(ARTIFACT_PATH.relative_to(ROOT)),
        "input_report": str(ARTIFACT_REPORT_PATH.relative_to(ROOT)),
        "approved_count": len(approved_rows),
        "excluded_carried_forward_count": len(excluded_rows),
        "promotion_allowed_true_count": promotion_allowed_true_count,
        "duplicate_approved_keys": duplicate_approved_keys,
        "overlap_with_excluded": overlap_with_excluded,
        "row_issue_count": len(row_issues),
        "row_issues": row_issues,
        "top_level_checks": top_level_checks,
        "approved_borough_counts": dict(borough_counts),
        "approved_confidence_counts": dict(confidence_counts),
        "approved_source_counts": dict(source_counts),
        "next_required_step": "If readiness_pass is true, Phase 2E promotion may be designed or run only after Howard explicitly authorizes updating data/location_cache.json.",
    }

    save_json_file(READINESS_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if readiness_pass else 1


if __name__ == "__main__":
    sys.exit(main())
