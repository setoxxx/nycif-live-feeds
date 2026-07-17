#!/usr/bin/env python3
"""Apply M11 supplemental manual approval decisions from a small patch file.

Human reviewers (including ChatGPT via GitHub connector) must NOT edit the full
~110k-line supplemental_manual_approval_queue.json. Instead, append decisions to
data/supplemental_manual_approval_decisions.json (or a batch CSV) and run this
script locally or in CI.

Does NOT set promotion_allowed=true unless a decision explicitly requests it
(and even then, public map merge still requires separate authorization).

Outputs:
- data/supplemental_manual_approval_queue.json (patched in place)
- data/supplemental_manual_approval_decisions_report.json
"""

from __future__ import annotations

import argparse
import csv
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
        utc_now_iso,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
    )

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
DECISIONS_PATH = DATA_DIR / "supplemental_manual_approval_decisions.json"
DECISIONS_REPORT_PATH = DATA_DIR / "supplemental_manual_approval_decisions_report.json"

DEFAULT_REVIEWER = "Howard Weiss"


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def load_decisions_json(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = load_json_file(path, {})
    if not isinstance(payload, dict):
        return DEFAULT_REVIEWER, []
    reviewer = str(payload.get("manual_reviewer") or DEFAULT_REVIEWER).strip()
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return reviewer, []
    return reviewer, [row for row in decisions if isinstance(row, dict)]


def load_decisions_csv(path: Path) -> tuple[str, list[dict[str, Any]]]:
    decisions: list[dict[str, Any]] = []
    reviewer = DEFAULT_REVIEWER
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            status = (row.get("manual_review_status") or "").strip().lower()
            if status not in {"approved", "rejected", "pending"}:
                continue
            if row.get("manual_reviewer"):
                reviewer = str(row["manual_reviewer"]).strip()
            decision: dict[str, Any] = {
                "manual_review_status": status,
                "approval_decision_reason": (row.get("approval_decision_reason") or "").strip(),
                "manual_review_notes": (row.get("manual_review_notes") or "").strip(),
            }
            if row.get("review_rank", "").strip().isdigit():
                decision["review_rank"] = int(row["review_rank"])
            if row.get("overlap_key", "").strip():
                decision["overlap_key"] = row["overlap_key"].strip()
            if row.get("promotion_allowed", "").strip().lower() in {"true", "1", "yes"}:
                decision["promotion_allowed"] = True
            decisions.append(decision)
    return reviewer, decisions


def decision_key(decision: dict[str, Any]) -> tuple[str, Any]:
    if decision.get("overlap_key"):
        return ("overlap_key", decision["overlap_key"])
    if decision.get("review_rank") is not None:
        return ("review_rank", int(decision["review_rank"]))
    raise ValueError("Each decision must include overlap_key or review_rank.")


def index_decisions(decisions: list[dict[str, Any]]) -> dict[tuple[str, Any], dict[str, Any]]:
    indexed: dict[tuple[str, Any], dict[str, Any]] = {}
    for decision in decisions:
        key = decision_key(decision)
        if key in indexed:
            raise ValueError(f"Duplicate decision key: {key}")
        indexed[key] = decision
    return indexed


def row_lookup_keys(row: dict[str, Any]) -> list[tuple[str, Any]]:
    keys: list[tuple[str, Any]] = []
    if row.get("overlap_key"):
        keys.append(("overlap_key", row["overlap_key"]))
    if row.get("review_rank") is not None:
        keys.append(("review_rank", int(row["review_rank"])))
    return keys


def apply_decision(
    row: dict[str, Any],
    decision: dict[str, Any],
    default_reviewer: str,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    out = dict(row)
    status = str(decision.get("manual_review_status") or "pending").lower()
    if status not in {"approved", "rejected", "pending"}:
        raise ValueError(f"Invalid manual_review_status: {status}")

    reviewer = str(decision.get("manual_reviewer") or default_reviewer).strip()
    out["manual_review_status"] = status
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    out["promotion_allowed"] = bool(decision.get("promotion_allowed")) and status == "approved"

    coord_fields = (
        "proposed_lat",
        "proposed_lng",
        "geocoder_source",
        "geocoder_confidence",
        "confidence_reason",
        "fill_method",
    )
    for field in coord_fields:
        if field in decision and decision[field] is not None:
            out[field] = decision[field]
    try:
        from scripts.coverage_gap_utils import valid_nyc_lat_lng
    except ModuleNotFoundError:  # pragma: no cover
        from coverage_gap_utils import valid_nyc_lat_lng
    if valid_nyc_lat_lng(out.get("proposed_lat"), out.get("proposed_lng")):
        out["has_coordinates"] = True

    if status in {"approved", "rejected"}:
        out["manual_reviewer"] = reviewer
        out["manual_reviewed_at_utc"] = reviewed_at_utc
        out["approval_decision_reason"] = (
            decision.get("approval_decision_reason")
            or (
                "Rejected during M11 supplemental manual review."
                if status == "rejected"
                else "Approved during M11 supplemental manual review."
            )
        )
        notes = decision.get("manual_review_notes")
        out["manual_review_notes"] = notes if notes else None
    elif status == "pending":
        out["manual_reviewer"] = None
        out["manual_reviewed_at_utc"] = None
        out["approval_decision_reason"] = None
        out["manual_review_notes"] = decision.get("manual_review_notes") or None

    return out


def run(
    *,
    decisions_path: Path = DECISIONS_PATH,
    csv_path: Path | None = None,
    dry_run: bool = False,
) -> int:
    payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(payload, "approval_queue")
    if not queue:
        print(json.dumps({"error": "approval queue empty or missing"}, indent=2))
        return 1

    if csv_path:
        default_reviewer, decisions = load_decisions_csv(csv_path)
    else:
        default_reviewer, decisions = load_decisions_json(decisions_path)

    if not decisions:
        print(json.dumps({"error": "no decisions to apply"}, indent=2))
        return 1

    indexed = index_decisions(decisions)
    reviewed_at_utc = utc_now_iso()
    applied_keys: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []

    for row in queue:
        match_key = None
        for key in row_lookup_keys(row):
            if key in indexed:
                match_key = key
                break
        if match_key is None:
            updated.append(row)
            continue
        decision = indexed.pop(match_key)
        updated.append(apply_decision(row, decision, default_reviewer, reviewed_at_utc))
        applied_keys.append({"match": list(match_key), "status": decision.get("manual_review_status")})

    for key, decision in indexed.items():
        unmatched.append({"match": list(key), "decision": decision})

    status_counts = Counter(row.get("manual_review_status") for row in updated)
    report = {
        "generated_at_utc": reviewed_at_utc,
        "phase": "m11_supplemental_manual_approval_decisions_applied",
        "decisions_source": repo_relative(csv_path) if csv_path else repo_relative(decisions_path),
        "decisions_requested": len(decisions),
        "decisions_applied": len(applied_keys),
        "decisions_unmatched": len(unmatched),
        "approval_queue_count": len(updated),
        "status_counts": dict(status_counts),
        "approved_count": status_counts.get("approved", 0),
        "rejected_count": status_counts.get("rejected", 0),
        "pending_count": status_counts.get("pending", 0),
        "promotion_allowed_count": sum(1 for row in updated if row.get("promotion_allowed") is True),
        "applied": applied_keys,
        "unmatched": unmatched,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": "Run validate_supplemental_manual_approvals.py. Public map merge still requires explicit authorization.",
    }

    if unmatched:
        report["qa_pass"] = False
        save_json_file(DECISIONS_REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    if not dry_run:
        save_json_file(APPROVAL_QUEUE_PATH, {"generated_at_utc": reviewed_at_utc, "approval_queue": updated})
    save_json_file(DECISIONS_REPORT_PATH, report)
    report["qa_pass"] = True
    report["dry_run"] = dry_run
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply supplemental manual approval decisions patch.")
    parser.add_argument(
        "--decisions",
        type=Path,
        default=DECISIONS_PATH,
        help="Small JSON decisions file (default: data/supplemental_manual_approval_decisions.json)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Optional CSV batch with review_rank/overlap_key and manual_review_status.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write queue.")
    args = parser.parse_args()
    return run(decisions_path=args.decisions, csv_path=args.csv, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
