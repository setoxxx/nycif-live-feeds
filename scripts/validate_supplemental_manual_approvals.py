#!/usr/bin/env python3
"""Validate M11 supplemental manual approval queue.

Pending rows are allowed. Fails only when a row claims approval/promotion
without meeting the safety contract.

Outputs:
- data/supplemental_manual_approval_validation_report.json
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
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
VALIDATION_REPORT_PATH = DATA_DIR / "supplemental_manual_approval_validation_report.json"

VALID_CONFIDENCE = {"high", "medium", "low", None}


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def issue(severity: str, code: str, message: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "overlap_key": row.get("overlap_key"),
        "title": row.get("title"),
        "manual_review_status": row.get("manual_review_status"),
        "promotion_allowed": row.get("promotion_allowed"),
    }


def validate_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    status = row.get("manual_review_status")
    promotion_allowed = row.get("promotion_allowed") is True

    if status not in {"pending", "approved", "rejected"}:
        issues.append(
            issue("fail", "invalid_manual_review_status", "manual_review_status must be pending, approved, or rejected.", row)
        )

    if promotion_allowed and status != "approved":
        issues.append(
            issue("fail", "promotion_without_approval", "promotion_allowed cannot be true unless manual_review_status is approved.", row)
        )

    if status == "approved" or promotion_allowed:
        if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
            issues.append(issue("fail", "invalid_approved_coordinates", "Approved/promotable row must have valid NYC lat/lng.", row))
        if not row.get("geocoder_source"):
            issues.append(issue("fail", "missing_geocoder_source", "Approved/promotable row must document geocoder_source.", row))
        if row.get("geocoder_confidence") not in {"high", "medium"}:
            issues.append(
                issue("fail", "invalid_geocoder_confidence", "Approved/promotable row must have high or medium geocoder_confidence.", row)
            )
        if not row.get("confidence_reason"):
            issues.append(issue("fail", "missing_confidence_reason", "Approved/promotable row must have confidence_reason.", row))
        if not row.get("manual_reviewer"):
            issues.append(issue("fail", "missing_manual_reviewer", "Approved/promotable row must have manual_reviewer.", row))
        if not row.get("manual_reviewed_at_utc"):
            issues.append(issue("fail", "missing_manual_reviewed_at", "Approved/promotable row must have manual_reviewed_at_utc.", row))
        if not row.get("approval_decision_reason"):
            issues.append(issue("fail", "missing_approval_decision_reason", "Approved/promotable row must explain approval_decision_reason.", row))

    if status == "rejected" and promotion_allowed:
        issues.append(issue("fail", "rejected_row_promotable", "Rejected rows cannot be promotable.", row))

    if row.get("public_map_modified") or row.get("location_cache_modified") or row.get("staged_feed_modified"):
        issues.append(issue("fail", "unsafe_modified_flags", "Queue rows must not claim protected feed modifications.", row))

    return issues


def main() -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    rows = rows_from_payload(payload, "approval_queue")
    issues: list[dict[str, Any]] = []
    for row in rows:
        issues.extend(validate_row(row))

    fail_count = sum(1 for item in issues if item["severity"] == "fail")
    status_counts = Counter(row.get("manual_review_status") for row in rows)
    intake_counts = Counter(row.get("intake_type") for row in rows)
    promotion_allowed_count = sum(1 for row in rows if row.get("promotion_allowed") is True)
    report = {
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_manual_approval_validation",
        "approval_queue_count": len(rows),
        "status_counts": dict(status_counts),
        "intake_counts": dict(intake_counts),
        "promotion_allowed_count": promotion_allowed_count,
        "approved_count": status_counts.get("approved", 0),
        "pending_count": status_counts.get("pending", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "fail_count": fail_count,
        "qa_pass": fail_count == 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "issues": issues[:100],
        "validation_rule": (
            "Pending rows are allowed. Approved/promotable rows must have valid NYC coordinates, "
            "documented source/confidence, reviewer, review timestamp, and decision reason."
        ),
    }
    save_json_file(VALIDATION_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
