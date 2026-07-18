#!/usr/bin/env python3
"""Apply supplemental overlap_key coordinate conflict audit recommendations.

Reads data/reports/supplemental_overlap_key_coord_conflict_audit_report.json and:
- rejects weaker duplicate rows for 70 merge/dedupe pairs
- rekeys both rows for 5 split pairs with location-aware overlap_keys
- holds 3 manual_review pairs for human decision (notes only)

Does NOT modify location_cache.json, staged feeds, the public map, or promotion_allowed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        simplified_place,
        utc_now_iso,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        simplified_place,
        utc_now_iso,
    )

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
AUDIT_REPORT_PATH = DATA_DIR / "reports" / "supplemental_overlap_key_coord_conflict_audit_report.json"
APPLY_REPORT_PATH = DATA_DIR / "reports" / "supplemental_overlap_key_coord_conflict_apply_report.json"

DEDUPE_RECOMMENDATIONS = {
    "dedupe_keep_higher_confidence",
    "merge_dedupe_keep_better_geocode",
    "dedupe_drop_bad_geocode",
}
SPLIT_RECOMMENDATION = "split_overlap_key_keep_both_pins"
MANUAL_RECOMMENDATION = "manual_review"
DEFAULT_REVIEWER = "overlap_key_coord_conflict_audit"


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def coord_key(lat: Any, lng: Any) -> tuple[float, float] | None:
    try:
        if lat is None or lng is None:
            return None
        return (round(float(lat), 6), round(float(lng), 6))
    except (TypeError, ValueError):
        return None


def row_coords(row: dict[str, Any]) -> tuple[float, float] | None:
    lat = row.get("proposed_lat", row.get("lat"))
    lng = row.get("proposed_lng", row.get("lng"))
    return coord_key(lat, lng)


def snapshot_coords(snapshot: dict[str, Any]) -> tuple[float, float] | None:
    return coord_key(snapshot.get("lat"), snapshot.get("lng"))


def location_aware_overlap_key(base_overlap_key: str, row: dict[str, Any]) -> str:
    borough = str(row.get("borough") or "").strip()
    place = simplified_place(str(row.get("display_location") or ""))
    source_event_id = str(row.get("source_event_id") or "").strip()
    if borough and place:
        return f"{base_overlap_key}|{borough}|{place}"
    if source_event_id:
        return f"{base_overlap_key}|{source_event_id}"
    return base_overlap_key


def match_row(
    queue_row: dict[str, Any],
    snapshot: dict[str, Any],
    overlap_key: str,
) -> bool:
    if str(queue_row.get("overlap_key") or "") != overlap_key:
        return False
    snapshot_event_id = str(snapshot.get("source_event_id") or "").strip()
    if snapshot_event_id and str(queue_row.get("source_event_id") or "") == snapshot_event_id:
        return True
    queue_coords = row_coords(queue_row)
    snapshot_coord = snapshot_coords(snapshot)
    return queue_coords is not None and queue_coords == snapshot_coord


def reject_row(
    row: dict[str, Any],
    *,
    reason: str,
    reviewed_at_utc: str,
    overlap_key: str,
) -> dict[str, Any]:
    out = dict(row)
    out["manual_review_status"] = "rejected"
    out["manual_reviewer"] = DEFAULT_REVIEWER
    out["manual_reviewed_at_utc"] = reviewed_at_utc
    out["approval_decision_reason"] = (
        f"Overlap_key coord conflict audit dedupe ({overlap_key}): {reason}"
    )
    out["manual_review_notes"] = (
        "Rejected by supplemental_overlap_key_coord_conflict_audit apply script — weaker duplicate geocode."
    )
    out["promotion_allowed"] = False
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    return out


def rekey_row(
    row: dict[str, Any],
    *,
    base_overlap_key: str,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    out = dict(row)
    old_key = str(out.get("overlap_key") or "")
    new_key = location_aware_overlap_key(base_overlap_key, out)
    out["overlap_key"] = new_key
    out["manual_review_notes"] = (
        f"Rekeyed by overlap_key coord conflict audit: {old_key} -> {new_key}"
    )
    out["manual_reviewed_at_utc"] = reviewed_at_utc
    out["promotion_allowed"] = False
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    return out


def hold_row(
    row: dict[str, Any],
    *,
    reason: str,
    reviewed_at_utc: str,
    overlap_key: str,
) -> dict[str, Any]:
    out = dict(row)
    out["manual_review_notes"] = (
        f"Held for human decision — overlap_key coord conflict audit ({overlap_key}): {reason}"
    )
    out["manual_reviewed_at_utc"] = reviewed_at_utc
    out["promotion_allowed"] = False
    return out


def apply_finding(
    queue: list[dict[str, Any]],
    finding: dict[str, Any],
    *,
    reviewed_at_utc: str,
    applied: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    overlap_key = str(finding.get("overlap_key") or "")
    recommendation = str(finding.get("recommendation") or "")
    reason = str(finding.get("reason") or "")
    updated: list[dict[str, Any]] = []

    if recommendation in DEDUPE_RECOMMENDATIONS:
        drop_snapshot = finding.get("alternate_row") or {}
        touched = 0
        for row in queue:
            if match_row(row, drop_snapshot, overlap_key):
                updated.append(
                    reject_row(row, reason=reason, reviewed_at_utc=reviewed_at_utc, overlap_key=overlap_key)
                )
                touched += 1
                applied.append(
                    {
                        "action": "reject_duplicate",
                        "overlap_key": overlap_key,
                        "recommendation": recommendation,
                        "source_event_id": drop_snapshot.get("source_event_id"),
                    }
                )
            else:
                updated.append(row)
        if touched != 1:
            unmatched.append({"finding": overlap_key, "action": "reject_duplicate", "snapshot": drop_snapshot})
        return updated

    if recommendation == SPLIT_RECOMMENDATION:
        snapshots = [finding.get("row_a") or {}, finding.get("row_b") or {}]
        touched = 0
        for row in queue:
            matched_snapshot = None
            for snapshot in snapshots:
                if match_row(row, snapshot, overlap_key):
                    matched_snapshot = snapshot
                    break
            if matched_snapshot is not None:
                old_key = row.get("overlap_key")
                new_row = rekey_row(row, base_overlap_key=overlap_key, reviewed_at_utc=reviewed_at_utc)
                updated.append(new_row)
                touched += 1
                applied.append(
                    {
                        "action": "rekey",
                        "overlap_key": overlap_key,
                        "old_overlap_key": old_key,
                        "new_overlap_key": new_row.get("overlap_key"),
                        "source_event_id": matched_snapshot.get("source_event_id"),
                    }
                )
            else:
                updated.append(row)
        if touched != 2:
            unmatched.append(
                {
                    "finding": overlap_key,
                    "action": "rekey_both",
                    "expected": 2,
                    "touched": touched,
                }
            )
        return updated

    if recommendation == MANUAL_RECOMMENDATION:
        snapshots = [finding.get("row_a") or {}, finding.get("row_b") or {}]
        touched = 0
        for row in queue:
            matched = any(match_row(row, snapshot, overlap_key) for snapshot in snapshots)
            if matched:
                updated.append(
                    hold_row(row, reason=reason, reviewed_at_utc=reviewed_at_utc, overlap_key=overlap_key)
                )
                touched += 1
                applied.append(
                    {
                        "action": "hold_manual_review",
                        "overlap_key": overlap_key,
                        "source_event_id": row.get("source_event_id"),
                    }
                )
            else:
                updated.append(row)
        if touched != 2:
            unmatched.append(
                {
                    "finding": overlap_key,
                    "action": "hold_manual_review",
                    "expected": 2,
                    "touched": touched,
                }
            )
        return updated

    unmatched.append({"finding": overlap_key, "action": "unknown_recommendation", "recommendation": recommendation})
    return queue


def verify_export_counts(events: list[dict[str, Any]]) -> dict[str, Any]:
    overlap_keys = [str(row.get("overlap_key") or "") for row in events if row.get("overlap_key")]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        key = str(row.get("overlap_key") or "")
        if key:
            grouped.setdefault(key, []).append(row)

    remaining_conflicts = 0
    for key, rows in grouped.items():
        if len(rows) != 2:
            continue
        coords = {
            (round(float(r["lat"]), 6), round(float(r["lng"]), 6))
            for r in rows
            if r.get("lat") is not None and r.get("lng") is not None
        }
        if len(coords) > 1:
            remaining_conflicts += 1

    return {
        "export_event_count": len(events),
        "unique_overlap_key_count": len(set(overlap_keys)),
        "remaining_coord_conflict_pair_count": remaining_conflicts,
        "expected_export_event_count": 3493,
        "expected_unique_overlap_key_count": 2406,
        "export_event_count_match": len(events) == 3493,
        "unique_overlap_key_count_match": len(set(overlap_keys)) == 2336,
        "remaining_coord_conflict_pair_count_match": remaining_conflicts == 0,
    }


def run(*, dry_run: bool = False, audit_path: Path = AUDIT_REPORT_PATH) -> int:
    audit = load_json_file(audit_path, {})
    findings = audit.get("findings")
    if not isinstance(findings, list) or not findings:
        print(json.dumps({"error": "audit report missing findings"}, indent=2))
        return 1

    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(payload, "approval_queue")
    if not queue:
        print(json.dumps({"error": "approval queue empty or missing"}, indent=2))
        return 1

    reviewed_at_utc = utc_now_iso()
    applied: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    updated = queue
    for finding in findings:
        updated = apply_finding(
            updated,
            finding,
            reviewed_at_utc=reviewed_at_utc,
            applied=applied,
            unmatched=unmatched,
        )

    status_counts = Counter(row.get("manual_review_status") for row in updated)
    action_counts = Counter(item["action"] for item in applied)

    report: dict[str, Any] = {
        "artifact_type": "supplemental_overlap_key_coord_conflict_apply_report",
        "generated_at_utc": reviewed_at_utc,
        "phase": "m11_supplemental_overlap_key_coord_conflict_apply",
        "audit_report_path": repo_relative(audit_path),
        "approval_queue_path": repo_relative(APPROVAL_QUEUE_PATH),
        "findings_total": len(findings),
        "actions_applied": len(applied),
        "action_counts": dict(action_counts),
        "unmatched_count": len(unmatched),
        "unmatched": unmatched,
        "approval_queue_count": len(updated),
        "status_counts": dict(status_counts),
        "approved_count": status_counts.get("approved", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "promotion_performed": False,
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
        "applied": applied,
        "dry_run": dry_run,
    }

    if unmatched:
        report["qa_pass"] = False
        save_json_file(APPLY_REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    if not dry_run:
        save_json_file(
            APPROVAL_QUEUE_PATH,
            {"generated_at_utc": reviewed_at_utc, "approval_queue": updated},
        )

    report["qa_pass"] = True
    save_json_file(APPLY_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply supplemental overlap_key coordinate conflict audit."
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=AUDIT_REPORT_PATH,
        help="Audit report JSON path",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write queue.")
    args = parser.parse_args()
    return run(dry_run=args.dry_run, audit_path=args.audit)


if __name__ == "__main__":
    sys.exit(main())
