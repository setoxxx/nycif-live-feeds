#!/usr/bin/env python3
"""Apply Phase 2D manual GPS approval decisions to the approval queue.

This script updates review metadata on queue rows. It does NOT promote to
location_cache.json, does NOT modify the staged feed, and does NOT publish
to the public map unless promotion_allowed is explicitly set elsewhere with
Phase 2E authorization.

Default policy applied when no CSV override is provided:
- approve: nyc_parks_bigapps + high confidence (excluding known-bad group_keys)
- reject: known coordinate/borough mismatch rows
- pending: existing_location_cache_place_memory + medium confidence

Outputs:
- data/gps_manual_approval_queue.json (updated)
- data/gps_manual_approval_decisions_report.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APPROVAL_QUEUE_PATH = DATA_DIR / "gps_manual_approval_queue.json"
DECISIONS_REPORT_PATH = DATA_DIR / "gps_manual_approval_decisions_report.json"

MANUAL_REVIEWER = "Howard Weiss"

REJECT_GROUP_KEYS = {
    "bronx|al qui ones playground basketball 04",
    "manhattan|jackie robinson park sidewalk",
    "brooklyn|prospect park grand army plaza safety zone west",
    "brooklyn|prospect park drummer s grove",
    "brooklyn|prospect park drummer s grove market place",
    "brooklyn|prospect park 3rd street entrance prospect park park drive whole drive",
    "brooklyn|knickerbocker avenue between starr street and suydam street",
}

REJECT_REASONS = {
    "bronx|al qui ones playground basketball 04": "Rejected: proposed coordinates fall in Manhattan/Lower East Side, not Bronx.",
    "manhattan|jackie robinson park sidewalk": "Rejected: Parks BigApps facility ID maps to Brooklyn (B294), borough mismatch.",
    "brooklyn|prospect park grand army plaza safety zone west": "Rejected: proposed coordinates are in the Bronx, not Brooklyn Prospect Park.",
    "brooklyn|prospect park drummer s grove": "Rejected: proposed coordinates are in the Bronx, not Brooklyn Prospect Park.",
    "brooklyn|prospect park drummer s grove market place": "Rejected: proposed coordinates are in the Bronx, not Brooklyn Prospect Park.",
    "brooklyn|prospect park 3rd street entrance prospect park park drive whole drive": "Rejected: proposed coordinates are in the Bronx, not Brooklyn Prospect Park.",
    "brooklyn|knickerbocker avenue between starr street and suydam street": "Rejected: street-segment location_cache match; needs manual geocoding before approval.",
}

APPROVE_REASON = (
    "Approved after Phase 2D review: official NYC Parks BigApps facility coordinates "
    "with high confidence; spot-check batch accepted for queue staging only."
)
PENDING_REASON = (
    "Pending second-pass review: location_cache broad place-name match (medium confidence) "
    "requires individual pin verification before approval."
)


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def load_csv_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    overrides: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            group_key = (row.get("group_key") or "").strip()
            status = (row.get("manual_review_status") or "").strip().lower()
            if not group_key or status not in {"approved", "rejected", "pending"}:
                continue
            overrides[group_key] = {
                "manual_review_status": status,
                "approval_decision_reason": (row.get("approval_decision_reason") or "").strip(),
                "manual_review_notes": (row.get("manual_review_notes") or "").strip(),
                "manual_reviewer": (row.get("manual_reviewer") or MANUAL_REVIEWER).strip(),
            }
    return overrides


def default_decision(row: dict[str, Any]) -> tuple[str, str, str]:
    group_key = str(row.get("group_key") or "")
    if group_key in REJECT_GROUP_KEYS:
        return "rejected", REJECT_REASONS[group_key], "Known bad pin flagged during Phase 2D review."
    source = row.get("geocoder_source")
    confidence = row.get("geocoder_confidence")
    if source == "nyc_parks_bigapps" and confidence == "high":
        return "approved", APPROVE_REASON, "Tier A Parks BigApps high-confidence batch approval."
    return "pending", "", PENDING_REASON


def apply_row(row: dict[str, Any], reviewed_at_utc: str, override: dict[str, str] | None) -> dict[str, Any]:
    out = dict(row)
    if override:
        status = override["manual_review_status"]
        reason = override.get("approval_decision_reason") or ""
        notes = override.get("manual_review_notes") or ""
        reviewer = override.get("manual_reviewer") or MANUAL_REVIEWER
    else:
        status, reason, notes = default_decision(row)
        reviewer = MANUAL_REVIEWER

    out["manual_review_status"] = status
    out["promotion_allowed"] = False
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False

    if status in {"approved", "rejected"}:
        out["manual_reviewer"] = reviewer
        out["manual_reviewed_at_utc"] = reviewed_at_utc
        out["approval_decision_reason"] = reason or (
            "Rejected during Phase 2D manual review." if status == "rejected" else "Approved during Phase 2D manual review."
        )
        out["manual_review_notes"] = notes or None
    else:
        out["manual_reviewer"] = None
        out["manual_reviewed_at_utc"] = None
        out["approval_decision_reason"] = None
        out["manual_review_notes"] = notes or None

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply Phase 2D GPS manual approval decisions.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional reviewed CSV with manual_review_status per group_key.",
    )
    args = parser.parse_args()

    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(payload, "approval_queue")
    overrides = load_csv_overrides(args.csv) if args.csv else {}
    reviewed_at_utc = datetime.now(timezone.utc).isoformat()

    updated: list[dict[str, Any]] = []
    for row in queue:
        group_key = str(row.get("group_key") or "")
        updated.append(apply_row(row, reviewed_at_utc, overrides.get(group_key)))

    status_counts = Counter(row.get("manual_review_status") for row in updated)
    report = {
        "generated_at_utc": reviewed_at_utc,
        "phase": "phase_2d_manual_approval_decisions_applied",
        "manual_reviewer_default": MANUAL_REVIEWER,
        "csv_override_path": str(args.csv) if args.csv else None,
        "csv_override_count": len(overrides),
        "approval_queue_count": len(updated),
        "status_counts": dict(status_counts),
        "approved_count": status_counts.get("approved", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "pending_count": status_counts.get("pending", 0),
        "promotion_allowed_count": 0,
        "rejected_group_keys": sorted(REJECT_GROUP_KEYS),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": "Run validate_gps_manual_approvals.py and build_gps_manual_review_sheet.py. Phase 2E promotion requires explicit authorization.",
    }

    save_json_file(APPROVAL_QUEUE_PATH, {"generated_at_utc": reviewed_at_utc, "approval_queue": updated})
    save_json_file(DECISIONS_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
