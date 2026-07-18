#!/usr/bin/env python3
"""Apply targeted supplemental queue row corrections from a small JSON patch file.

Used for dedupe, GPS fixes, title decoding, and overlap_key repairs without
editing the full approval queue by hand.

Does NOT modify location_cache.json or set promotion_allowed=true.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
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
CORRECTIONS_PATH = DATA_DIR / "supplemental_row_corrections.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_row_corrections_report.json"

PATCHABLE_FIELDS = {
    "title",
    "overlap_key",
    "display_location",
    "borough",
    "proposed_lat",
    "proposed_lng",
    "start_date_time",
    "end_date_time",
    "geocoder_source",
    "geocoder_confidence",
    "confidence_reason",
    "manual_review_status",
    "manual_review_notes",
    "approval_decision_reason",
    "manual_reviewer",
    "manual_reviewed_at_utc",
}


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def correction_keys(correction: dict[str, Any]) -> list[tuple[str, Any]]:
    keys: list[tuple[str, Any]] = []
    if correction.get("review_rank") is not None:
        keys.append(("review_rank", int(correction["review_rank"])))
    if correction.get("source_event_id"):
        keys.append(("source_event_id", str(correction["source_event_id"])))
    match_overlap_key = correction.get("match_overlap_key")
    if match_overlap_key:
        keys.append(("overlap_key", str(match_overlap_key)))
    if not keys:
        raise ValueError("Each correction needs review_rank, source_event_id, or match_overlap_key")
    return keys


def row_keys(row: dict[str, Any]) -> list[tuple[str, Any]]:
    keys: list[tuple[str, Any]] = []
    if row.get("overlap_key"):
        keys.append(("overlap_key", row["overlap_key"]))
    if row.get("review_rank") is not None:
        keys.append(("review_rank", int(row["review_rank"])))
    if row.get("source_event_id"):
        keys.append(("source_event_id", str(row["source_event_id"])))
    return keys


def apply_correction(row: dict[str, Any], correction: dict[str, Any], reviewed_at_utc: str) -> dict[str, Any]:
    out = dict(row)
    for field in PATCHABLE_FIELDS:
        if field in correction and correction[field] is not None:
            out[field] = correction[field]

    status = str(out.get("manual_review_status") or row.get("manual_review_status") or "approved").lower()
    if status in {"approved", "rejected"}:
        out["manual_reviewer"] = str(
            correction.get("manual_reviewer") or out.get("manual_reviewer") or "supplemental_row_corrections"
        )
        out["manual_reviewed_at_utc"] = reviewed_at_utc

    if valid_nyc_lat_lng(out.get("proposed_lat"), out.get("proposed_lng")):
        out["has_coordinates"] = True

    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    out["promotion_allowed"] = False
    out["production_feed"] = False
    return out


def run(*, corrections_path: Path = CORRECTIONS_PATH, dry_run: bool = False) -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(payload, "approval_queue")
    if not queue:
        print(json.dumps({"error": "approval queue empty or missing"}, indent=2))
        return 1

    corrections_payload = load_json_file(corrections_path, {})
    corrections = corrections_payload.get("corrections") if isinstance(corrections_payload, dict) else None
    if not isinstance(corrections, list) or not corrections:
        print(json.dumps({"error": "no corrections to apply"}, indent=2))
        return 1

    reviewed_at_utc = utc_now_iso()
    indexed: dict[tuple[str, Any], dict[str, Any]] = {}
    for correction in corrections:
        if not isinstance(correction, dict):
            continue
        for key in correction_keys(correction):
            if key in indexed:
                raise ValueError(f"Duplicate correction key: {key}")
            indexed[key] = correction

    applied: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    updated_queue: list[dict[str, Any]] = []
    for row in queue:
        matched_correction = None
        for key in row_keys(row):
            if key in indexed:
                matched_correction = indexed[key]
                break
        if matched_correction:
            updated = apply_correction(row, matched_correction, reviewed_at_utc)
            applied.append(
                {
                    "review_rank": row.get("review_rank"),
                    "overlap_key_before": row.get("overlap_key"),
                    "overlap_key_after": updated.get("overlap_key"),
                    "title_after": updated.get("title"),
                    "proposed_lat": updated.get("proposed_lat"),
                    "proposed_lng": updated.get("proposed_lng"),
                    "manual_review_status": updated.get("manual_review_status"),
                }
            )
            updated_queue.append(updated)
        else:
            updated_queue.append(row)

    matched_keys = set()
    for row in queue:
        for key in row_keys(row):
            if key in indexed:
                matched_keys.add(key)
    for key in indexed:
        if key not in matched_keys:
            unmatched.append({"correction_key": key, "correction": indexed[key]})

    approved_before = sum(
        1 for row in queue if str(row.get("manual_review_status") or "").lower() == "approved"
    )
    approved_after = sum(
        1 for row in updated_queue if str(row.get("manual_review_status") or "").lower() == "approved"
    )

    report = {
        "artifact_type": "supplemental_row_corrections_report",
        "generated_at_utc": reviewed_at_utc,
        "corrections_path": repo_relative(corrections_path),
        "queue_path": repo_relative(APPROVAL_QUEUE_PATH),
        "dry_run": dry_run,
        "qa_pass": not unmatched,
        "applied_count": len(applied),
        "unmatched_count": len(unmatched),
        "approved_count_before": approved_before,
        "approved_count_after": approved_after,
        "applied": applied,
        "unmatched": unmatched,
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
    }

    if not dry_run:
        if isinstance(payload, dict):
            payload["approval_queue"] = updated_queue
            save_json_file(APPROVAL_QUEUE_PATH, payload)
        else:
            save_json_file(APPROVAL_QUEUE_PATH, {"approval_queue": updated_queue})
        save_json_file(REPORT_PATH, report)

    print(json.dumps(report, indent=2))
    return 0 if report["qa_pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply supplemental row corrections patch.")
    parser.add_argument("--corrections", type=Path, default=CORRECTIONS_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return run(corrections_path=args.corrections, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
