#!/usr/bin/env python3
"""Verify supplemental export feed and Phase 2E dry-run readiness.

Fails if approved export or dry-run report does not show full promotion readiness
(blocked_from_promotion must be 0; all approved rows would pass except promotion_allowed).

Does NOT promote or modify protected feeds.
"""

from __future__ import annotations

import json
import sys

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, valid_nyc_lat_lng
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, valid_nyc_lat_lng

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
DRY_RUN_PATH = DATA_DIR / "reports" / "supplemental_phase2e_promotion_dry_run_report.json"


def verify_export(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("artifact_type") != "supplemental_approved_export_feed":
        errors.append("export artifact_type mismatch")
    if payload.get("production_feed") is True:
        errors.append("export production_feed=true")
    if payload.get("promotion_allowed") is True:
        errors.append("export promotion_allowed=true")

    events = payload.get("events")
    if not isinstance(events, list):
        return errors + ["export missing events array"]

    export_count = payload.get("export_event_count")
    if export_count != len(events):
        errors.append(f"export_event_count={export_count!r} != len(events)={len(events)}")

    missing_borough = 0
    missing_coords = 0
    for row in events:
        if not str(row.get("borough") or "").strip():
            missing_borough += 1
        if not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
            missing_coords += 1

    if missing_borough:
        errors.append(f"export events missing borough: {missing_borough}")
    if missing_coords:
        errors.append(f"export events missing NYC coordinates: {missing_coords}")
    return errors


def verify_dry_run(report: dict, *, expected_approved: int | None = None) -> list[str]:
    errors: list[str] = []
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    blocked = int(summary.get("blocked_from_promotion") or 0)
    ready = int(summary.get("would_pass_if_promotion_authorized") or 0)
    approved = int(report.get("approved_queue_count") or 0)
    export_count = int(report.get("export_event_count") or 0)

    if report.get("dry_run_only") is not True:
        errors.append("dry_run_only is not true")
    if report.get("promotion_performed") is True:
        errors.append("promotion_performed is true")
    if blocked != 0:
        errors.append(f"blocked_from_promotion={blocked}")
    if ready != approved:
        errors.append(f"would_pass_if_promotion_authorized={ready} != approved_queue_count={approved}")
    if export_count != approved:
        errors.append(f"export_event_count={export_count} != approved_queue_count={approved}")
    if expected_approved is not None and approved != expected_approved:
        errors.append(f"approved_queue_count={approved} != expected={expected_approved}")
    if report.get("all_rows_ready_for_promotion") is not True:
        errors.append("all_rows_ready_for_promotion is not true")
    return errors


def main() -> int:
    export = load_json_file(EXPORT_PATH, {})
    dry_run = load_json_file(DRY_RUN_PATH, {})

    errors = verify_export(export if isinstance(export, dict) else {})
    errors.extend(verify_dry_run(dry_run if isinstance(dry_run, dict) else {}))

    result = {
        "artifact_type": "supplemental_phase2e_readiness_verification",
        "qa_pass": not errors,
        "export_event_count": export.get("export_event_count") if isinstance(export, dict) else None,
        "would_pass_if_promotion_authorized": (
            dry_run.get("summary", {}).get("would_pass_if_promotion_authorized")
            if isinstance(dry_run, dict)
            else None
        ),
        "blocked_from_promotion": (
            dry_run.get("summary", {}).get("blocked_from_promotion")
            if isinstance(dry_run, dict)
            else None
        ),
        "errors": errors,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
