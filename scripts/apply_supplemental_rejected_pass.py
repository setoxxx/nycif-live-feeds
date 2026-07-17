#!/usr/bin/env python3
"""Apply M11 supplemental rejected-row re-review pass (coordinate fill + re-decide).

Reads rejected rows in a review_rank range, attempts conservative coordinate fill
via NYC location gazetteer / Parks references, updates queue coordinates, and
replaces matching entries in supplemental_manual_approval_decisions.json.

Does NOT set promotion_allowed=true or modify location_cache.json.

Outputs:
- data/supplemental_manual_approval_queue.json (coordinate patches)
- data/supplemental_manual_approval_decisions.json (updated decisions)
- data/supplemental_rejected_pass_fill_report.json
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
        overlap_key,
        repo_relative,
        row_coords,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from scripts.nyc_location_gazetteer import (
        GAZETTEER_PATH,
        NYCLocationGazetteer,
        build_gazetteer_index,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        overlap_key,
        repo_relative,
        row_coords,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
    from nyc_location_gazetteer import (
        GAZETTEER_PATH,
        NYCLocationGazetteer,
        build_gazetteer_index,
    )

APPROVAL_QUEUE_PATH = DATA_DIR / "supplemental_manual_approval_queue.json"
DECISIONS_PATH = DATA_DIR / "supplemental_manual_approval_decisions.json"
FILL_REPORT_PATH = DATA_DIR / "supplemental_rejected_pass_fill_report.json"
PARKS_SNAPSHOT_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"

PERMANENT_REJECT_PREFIXES = (
    "Canceled event in title",
    "Online-only event",
    "Canceled per ",
)


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def is_permanent_reject(reason: str) -> bool:
    return any(str(reason or "").startswith(prefix) for prefix in PERMANENT_REJECT_PREFIXES)


def ensure_gazetteer() -> NYCLocationGazetteer:
    if not GAZETTEER_PATH.exists() or GAZETTEER_PATH.stat().st_size < 1000:
        save_json_file(GAZETTEER_PATH, build_gazetteer_index())
    return NYCLocationGazetteer.from_file(GAZETTEER_PATH)


def build_parks_overlap_index() -> dict[str, dict[str, Any]]:
    payload = load_json_file(PARKS_SNAPSHOT_PATH, {})
    events = payload.get("events", payload) if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in events:
        if not isinstance(row, dict):
            continue
        title = row.get("title") or ""
        start = row.get("start_date_time") or ""
        if not title or not start:
            continue
        key = overlap_key(title, start)
        lat, lng = row_coords(row)
        if valid_nyc_lat_lng(lat, lng):
            index[key] = row
    return index


def resolve_coordinates(
    row: dict[str, Any],
    gazetteer: NYCLocationGazetteer,
    parks_overlap: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    overlap = str(row.get("overlap_key") or "")
    if overlap and overlap in parks_overlap:
        hit = parks_overlap[overlap]
        lat, lng = row_coords(hit)
        if valid_nyc_lat_lng(lat, lng):
            return {
                "proposed_lat": float(lat),
                "proposed_lng": float(lng),
                "geocoder_source": "nyc_parks_bigapps_events_snapshot",
                "geocoder_confidence": "high",
                "confidence_reason": (
                    "Rejected-pass fill: Parks BigApps title+date match coordinates for manual review only."
                ),
                "fill_method": "parks_overlap_key",
            }

    display = str(row.get("display_location") or "")
    borough = row.get("borough")
    hit = gazetteer.lookup_display(display, borough)
    if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
        confidence = str(hit.get("confidence") or "medium")
        if confidence not in {"high", "medium"}:
            confidence = "medium"
        return {
            "proposed_lat": float(hit["lat"]),
            "proposed_lng": float(hit["lng"]),
            "geocoder_source": str(hit.get("source") or "nyc_location_gazetteer"),
            "geocoder_confidence": confidence,
            "confidence_reason": (
                f"Rejected-pass fill: {hit.get('confidence_reason') or 'Gazetteer location match'} "
                "for manual review only."
            ),
            "fill_method": "location_gazetteer",
        }
    return None


def patch_queue_row(row: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["proposed_lat"] = fill["proposed_lat"]
    out["proposed_lng"] = fill["proposed_lng"]
    out["geocoder_source"] = fill["geocoder_source"]
    out["geocoder_confidence"] = fill["geocoder_confidence"]
    out["confidence_reason"] = fill["confidence_reason"]
    out["has_coordinates"] = True
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    out["promotion_allowed"] = False
    return out


def approval_reason(row: dict[str, Any], fill: dict[str, Any]) -> str:
    intake = row.get("intake_type") or ""
    if intake == "parks_only":
        return "Rejected-pass approved; NYC coordinates and pin URL verified"
    if fill.get("fill_method") == "parks_overlap_key":
        return "Rejected-pass approved; Calendar+Parks title/date match; NYC pin verified"
    return "Rejected-pass approved; NYC coordinates filled from official reference; pin verified"


def run(
    *,
    start_rank: int,
    end_rank: int,
    batch_notes: str,
    dry_run: bool = False,
) -> int:
    queue_payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    queue = rows_from_payload(queue_payload, "approval_queue")
    if not queue:
        print(json.dumps({"error": "approval queue empty or missing"}, indent=2))
        return 1

    decisions_payload = load_json_file(DECISIONS_PATH, {})
    if not isinstance(decisions_payload, dict) or not isinstance(decisions_payload.get("decisions"), list):
        print(json.dumps({"error": "decisions file missing decisions array"}, indent=2))
        return 1

    decisions: list[dict[str, Any]] = decisions_payload["decisions"]
    decision_by_rank = {
        int(item["review_rank"]): item
        for item in decisions
        if isinstance(item, dict) and item.get("review_rank") is not None
    }

    gazetteer = ensure_gazetteer()
    parks_overlap = build_parks_overlap_index()

    queue_by_rank = {int(row["review_rank"]): row for row in queue if row.get("review_rank") is not None}
    outcomes: list[dict[str, Any]] = []
    approved = 0
    rejected = 0
    skipped = 0

    for rank in range(start_rank, end_rank + 1):
        row = queue_by_rank.get(rank)
        decision = decision_by_rank.get(rank)
        if row is None or decision is None:
            outcomes.append({"review_rank": rank, "outcome": "missing_row_or_decision"})
            skipped += 1
            continue
        if row.get("manual_review_status") != "rejected":
            outcomes.append({"review_rank": rank, "outcome": "skipped_not_rejected"})
            skipped += 1
            continue
        reason = str(decision.get("approval_decision_reason") or "")
        if is_permanent_reject(reason):
            outcomes.append({"review_rank": rank, "outcome": "skipped_permanent_reject", "reason": reason})
            skipped += 1
            continue

        fill = resolve_coordinates(row, gazetteer, parks_overlap)
        if fill:
            queue_by_rank[rank] = patch_queue_row(row, fill)
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "approved",
                "approval_decision_reason": approval_reason(row, fill),
                "manual_review_notes": batch_notes,
            }
            outcomes.append(
                {
                    "review_rank": rank,
                    "outcome": "approved",
                    "fill_method": fill["fill_method"],
                    "geocoder_source": fill["geocoder_source"],
                    "proposed_lat": fill["proposed_lat"],
                    "proposed_lng": fill["proposed_lng"],
                }
            )
            approved += 1
        else:
            decision_by_rank[rank] = {
                "review_rank": rank,
                "manual_review_status": "rejected",
                "approval_decision_reason": (
                    "Rejected-pass: no resolvable GPS after gazetteer and Parks reference fill"
                ),
                "manual_review_notes": batch_notes,
            }
            outcomes.append({"review_rank": rank, "outcome": "rejected_no_fill"})
            rejected += 1

    updated_queue = []
    for row in queue:
        rank = row.get("review_rank")
        if rank is not None and int(rank) in queue_by_rank:
            updated_queue.append(queue_by_rank[int(rank)])
        else:
            updated_queue.append(row)

    updated_decisions = []
    seen: set[int] = set()
    for item in decisions:
        rank = item.get("review_rank")
        if rank is not None and int(rank) in decision_by_rank:
            updated_decisions.append(decision_by_rank[int(rank)])
            seen.add(int(rank))
        else:
            updated_decisions.append(item)
    for rank, item in decision_by_rank.items():
        if start_rank <= rank <= end_rank and rank not in seen:
            updated_decisions.append(item)

    report = {
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_rejected_pass",
        "start_rank": start_rank,
        "end_rank": end_rank,
        "batch_notes": batch_notes,
        "approved_count": approved,
        "rejected_count": rejected,
        "skipped_count": skipped,
        "outcomes": outcomes,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "next_required_step": (
            "Run apply_supplemental_manual_approval_decisions.py, "
            "validate_supplemental_manual_approvals.py, and supplemental tests."
        ),
    }

    if not dry_run:
        save_json_file(
            APPROVAL_QUEUE_PATH,
            {"generated_at_utc": report["generated_at_utc"], "approval_queue": updated_queue},
        )
        decisions_payload["decisions"] = updated_decisions
        save_json_file(DECISIONS_PATH, decisions_payload)
    save_json_file(FILL_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply supplemental rejected-row re-review pass.")
    parser.add_argument("--start-rank", type=int, required=True)
    parser.add_argument("--end-rank", type=int, required=True)
    parser.add_argument("--batch-notes", required=True, help="manual_review_notes for this rejected pass batch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.end_rank < args.start_rank:
        print(json.dumps({"error": "end-rank must be >= start-rank"}, indent=2))
        return 1
    return run(
        start_rank=args.start_rank,
        end_rank=args.end_rank,
        batch_notes=args.batch_notes,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
