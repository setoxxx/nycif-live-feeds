#!/usr/bin/env python3
"""Validate Phase 2D manual GPS approvals.

This validator allows the approval queue to contain pending rows. It fails only
when a row claims approval/promotion but does not meet the safety contract.

Outputs:
- data/gps_manual_approval_validation_report.json
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
APPROVAL_QUEUE_PATH = DATA_DIR / "gps_manual_approval_queue.json"
VALIDATION_REPORT_PATH = DATA_DIR / "gps_manual_approval_validation_report.json"

VALID_CONFIDENCE = {"high", "medium"}


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


def issue(severity: str, code: str, message: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "manual_review_status": row.get("manual_review_status"),
        "promotion_allowed": row.get("promotion_allowed"),
    }


def validate_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    status = row.get("manual_review_status")
    promotion_allowed = row.get("promotion_allowed") is True

    if status not in {"pending", "approved", "rejected"}:
        issues.append(issue("fail", "invalid_manual_review_status", "manual_review_status must be pending, approved, or rejected.", row))

    if promotion_allowed and status != "approved":
        issues.append(issue("fail", "promotion_without_approval", "promotion_allowed cannot be true unless manual_review_status is approved.", row))

    if status == "approved" or promotion_allowed:
        if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
            issues.append(issue("fail", "invalid_approved_coordinates", "Approved/promotable row must have valid NYC lat/lng.", row))
        if not row.get("geocoder_source"):
            issues.append(issue("fail", "missing_geocoder_source", "Approved/promotable row must document geocoder_source.", row))
        if row.get("geocoder_confidence") not in VALID_CONFIDENCE:
            issues.append(issue("fail", "invalid_geocoder_confidence", "Approved/promotable row must have high or medium geocoder_confidence.", row))
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

    return issues


def main() -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    rows = rows_from_payload(payload, "approval_queue")
    issues: list[dict[str, Any]] = []
    for row in rows:
        issues.extend(validate_row(row))

    fail_count = sum(1 for item in issues if item["severity"] == "fail")
    status_counts = Counter(row.get("manual_review_status") for row in rows)
    promotion_allowed_count = sum(1 for row in rows if row.get("promotion_allowed") is True)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "phase_2d_manual_approval_validation",
        "approval_queue_count": len(rows),
        "status_counts": dict(status_counts),
        "promotion_allowed_count": promotion_allowed_count,
        "fail_count": fail_count,
        "qa_pass": fail_count == 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "issues": issues[:100],
        "validation_rule": "Pending rows are allowed. Approved/promotable rows must have valid NYC coordinates, documented source/confidence, reviewer, review timestamp, and decision reason.",
    }
    save_json_file(VALIDATION_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
