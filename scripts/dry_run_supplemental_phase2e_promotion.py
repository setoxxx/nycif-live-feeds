#!/usr/bin/env python3
"""Phase 2E supplemental promotion dry-run only.

Reads approved supplemental manual-approval queue rows and reports which rows
would pass Phase 2E promotion gates. Does NOT modify location_cache.json,
staged feeds, or the public map. Does NOT set promotion_allowed=true.

Outputs:
- data/reports/supplemental_phase2e_promotion_dry_run_report.json
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
VALIDATION_REPORT_PATH = DATA_DIR / "supplemental_manual_approval_validation_report.json"
EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_phase2e_promotion_dry_run_report.json"

REQUIRED_FIELDS = (
    "overlap_key",
    "title",
    "display_location",
    "borough",
    "proposed_lat",
    "proposed_lng",
    "geocoder_source",
    "geocoder_confidence",
    "confidence_reason",
    "manual_review_status",
    "manual_reviewer",
    "manual_reviewed_at_utc",
    "approval_decision_reason",
)


def queue_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("approval_queue"), list):
        return [row for row in payload["approval_queue"] if isinstance(row, dict)]
    return []


def row_issues(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    for field in REQUIRED_FIELDS:
        if row.get(field) in (None, ""):
            issues.append(f"missing_required_field:{field}")

    if str(row.get("manual_review_status") or "").lower() != "approved":
        issues.append("manual_review_status_not_approved")

    lat = row.get("proposed_lat", row.get("lat"))
    lng = row.get("proposed_lng", row.get("lng"))
    if not valid_nyc_lat_lng(lat, lng):
        issues.append("invalid_nyc_coordinates")

    if row.get("promotion_allowed") is not True:
        issues.append("promotion_allowed_not_true")

    if row.get("location_cache_modified") is not False:
        issues.append("location_cache_modified_not_false")
    if row.get("staged_feed_modified") is not False:
        issues.append("staged_feed_modified_not_false")
    if row.get("public_map_modified") is not False:
        issues.append("public_map_modified_not_false")
    if row.get("production_feed") is True:
        issues.append("production_feed_true")

    return issues


def would_pass_except_promotion_flag(row: dict[str, Any]) -> bool:
    return row_issues(row) == ["promotion_allowed_not_true"]


def classify_row(row: dict[str, Any]) -> str:
    issues = row_issues(row)
    if not issues:
        return "ready_all_gates_including_promotion_allowed"
    if would_pass_except_promotion_flag(row):
        return "would_pass_if_promotion_authorized"
    return "blocked"


def build_report() -> dict[str, Any]:
    queue = queue_rows(load_json_file(APPROVAL_QUEUE_PATH, {}))
    approved = [row for row in queue if str(row.get("manual_review_status") or "").lower() == "approved"]
    validation = load_json_file(VALIDATION_REPORT_PATH, {})
    export = load_json_file(EXPORT_PATH, {})

    classifications = Counter()
    issue_counts: Counter[str] = Counter()
    blocked_samples: list[dict[str, Any]] = []
    ready_if_authorized_samples: list[dict[str, Any]] = []

    for row in approved:
        bucket = classify_row(row)
        classifications[bucket] += 1
        issues = row_issues(row)
        for issue in issues:
            issue_counts[issue] += 1
        sample = {
            "overlap_key": row.get("overlap_key"),
            "title": row.get("title"),
            "borough": row.get("borough"),
            "geocoder_source": row.get("geocoder_source"),
            "issues": issues,
        }
        if bucket == "blocked" and len(blocked_samples) < 15:
            blocked_samples.append(sample)
        if bucket == "would_pass_if_promotion_authorized" and len(ready_if_authorized_samples) < 15:
            ready_if_authorized_samples.append(sample)

    ready_if_authorized = classifications.get("would_pass_if_promotion_authorized", 0)
    blocked = classifications.get("blocked", 0)
    fully_ready = classifications.get("ready_all_gates_including_promotion_allowed", 0)

    return {
        "artifact_type": "supplemental_phase2e_promotion_dry_run_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_phase2e_promotion_dry_run",
        "dry_run_only": True,
        "promotion_performed": False,
        "source_queue_path": repo_relative(APPROVAL_QUEUE_PATH),
        "source_export_path": repo_relative(EXPORT_PATH),
        "validation_report_path": repo_relative(VALIDATION_REPORT_PATH),
        "validation_qa_pass": bool(validation.get("qa_pass")),
        "approved_queue_count": len(approved),
        "export_event_count": export.get("export_event_count"),
        "summary": {
            "would_pass_if_promotion_authorized": ready_if_authorized,
            "ready_all_gates_including_promotion_allowed": fully_ready,
            "blocked_from_promotion": blocked,
            "blocked_pct": round((blocked / len(approved)) * 100.0, 2) if approved else 0.0,
            "ready_if_authorized_pct": round((ready_if_authorized / len(approved)) * 100.0, 2)
            if approved
            else 0.0,
        },
        "issue_counts": dict(issue_counts.most_common()),
        "blocked_samples": blocked_samples,
        "would_pass_if_promotion_authorized_samples": ready_if_authorized_samples,
        "qa_pass": validation.get("qa_pass") is True,
        "all_rows_ready_for_promotion": blocked == 0,
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
            "production_feed": False,
        },
        "next_required_step": (
            "Explicit Phase 2E authorization required before setting promotion_allowed=true "
            "or promoting supplemental rows to location_cache.json / public map."
        ),
    }


def main() -> int:
    report = build_report()
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
