#!/usr/bin/env python3
"""Incremental supplemental intake — preserve queue disposition, append net-new rows.

Rebuilds coverage queues and staging feed (with memory auto-fill), then merges
only net-new overlap_keys into supplemental_manual_approval_queue.json.

Does NOT modify location_cache.json or public map feeds.

Outputs:
- data/supplemental_manual_approval_queue.json (merged in place)
- data/supplemental_approved_export_feed.json
- data/reports/incremental_supplemental_intake_report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Any

try:
    from scripts.build_supplemental_approved_export_feed import build_export_payload
    from scripts.build_supplemental_manual_approval_queue import (
        APPROVAL_QUEUE_PATH,
        approval_item,
        events_from_feed,
        review_priority,
    )
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from build_supplemental_approved_export_feed import build_export_payload
    from build_supplemental_manual_approval_queue import (
        APPROVAL_QUEUE_PATH,
        approval_item,
        events_from_feed,
        review_priority,
    )
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )

STAGING_FEED_PATH = DATA_DIR / "supplemental_events_staging_feed.json"
EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
REPORT_PATH = DATA_DIR / "reports" / "incremental_supplemental_intake_report.json"
QUEUE_REPORT_PATH = DATA_DIR / "supplemental_manual_approval_queue_report.json"


def queue_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("approval_queue"), list):
        return [row for row in payload["approval_queue"] if isinstance(row, dict)]
    return []


def merge_incremental_queue(
    existing_queue: list[dict[str, Any]],
    staging_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    existing_keys = {
        str(row.get("overlap_key") or "").strip() for row in existing_queue if str(row.get("overlap_key") or "").strip()
    }
    before_by_rank = {int(row["review_rank"]): row for row in existing_queue if row.get("review_rank") is not None}

    staging_by_key: dict[str, dict[str, Any]] = {}
    for event in staging_events:
        key = str(event.get("overlap_key") or "").strip()
        if key:
            staging_by_key[key] = event

    net_new_keys = sorted(set(staging_by_key) - existing_keys)
    stale_keys = sorted(existing_keys - set(staging_by_key))

    net_new_events = [staging_by_key[key] for key in net_new_keys]
    net_new_events.sort(key=review_priority)
    net_new_items = [approval_item(event, 0) for event in net_new_events]

    for item, event in zip(net_new_items, net_new_events, strict=True):
        for field in ("auto_resolved", "fill_method", "memory_location_key"):
            if field in event:
                item[field] = event[field]
        if event.get("auto_resolved"):
            item["source_phase"] = "m11_incremental_supplemental_intake_memory"

    max_rank = max((int(row.get("review_rank") or 0) for row in existing_queue), default=0)
    for index, item in enumerate(net_new_items, start=1):
        item["review_rank"] = max_rank + index

    merged = [dict(row) for row in existing_queue] + net_new_items

    after_by_rank = {int(row["review_rank"]): row for row in merged if row.get("review_rank") in before_by_rank}
    disposition_preserved = len(after_by_rank) == len(before_by_rank) and all(
        after_by_rank[rank].get("manual_review_status") == before_by_rank[rank].get("manual_review_status")
        for rank in before_by_rank
    )

    net_new_auto = sum(1 for item in net_new_items if item.get("auto_resolved"))
    net_new_with_coords = sum(
        1 for item in net_new_items if valid_nyc_lat_lng(item.get("proposed_lat"), item.get("proposed_lng"))
    )
    net_new_needs_review = sum(
        1
        for item in net_new_items
        if str(item.get("manual_review_status") or "pending") == "pending"
        and not valid_nyc_lat_lng(item.get("proposed_lat"), item.get("proposed_lng"))
    )

    stats = {
        "existing_queue_count": len(existing_queue),
        "existing_unique_overlap_key_count": len(existing_keys),
        "staging_event_count": len(staging_events),
        "preserved_row_count": len(existing_queue),
        "net_new_row_count": len(net_new_items),
        "stale_queue_key_count": len(stale_keys),
        "net_new_auto_resolved_count": net_new_auto,
        "net_new_with_coordinates_count": net_new_with_coords,
        "net_new_needing_human_review_count": net_new_needs_review,
        "net_new_auto_resolved_pct": round((net_new_auto / len(net_new_items)) * 100.0, 2) if net_new_items else 0.0,
        "net_new_with_coordinates_pct": round((net_new_with_coords / len(net_new_items)) * 100.0, 2)
        if net_new_items
        else 0.0,
        "disposition_preserved": disposition_preserved,
        "stale_overlap_keys_sample": stale_keys[:10],
        "net_new_overlap_keys_sample": net_new_keys[:10],
    }
    return merged, stats


def rebuild_upstream(*, skip_rebuild: bool = False) -> None:
    if skip_rebuild:
        return
    root = DATA_DIR.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts import build_supplemental_coverage_review_queues as coverage_mod
    from scripts import build_supplemental_events_staging_feed as staging_mod

    coverage_mod.main()
    staging_mod.main()


def run(*, skip_rebuild: bool = False, dry_run: bool = False) -> dict[str, Any]:
    existing_payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    existing_queue = queue_rows_from_payload(existing_payload)
    before_counts = Counter(row.get("manual_review_status") for row in existing_queue)

    rebuild_upstream(skip_rebuild=skip_rebuild)

    staging_feed = load_json_file(STAGING_FEED_PATH, {})
    staging_events = events_from_feed(staging_feed)
    merged_queue, merge_stats = merge_incremental_queue(existing_queue, staging_events)

    after_counts = Counter(row.get("manual_review_status") for row in merged_queue)
    generated_at = utc_now_iso()

    export_payload, export_report = build_export_payload(merged_queue)

    report = {
        "artifact_type": "incremental_supplemental_intake_report",
        "generated_at_utc": generated_at,
        "phase": "m11_incremental_supplemental_intake",
        "dry_run": dry_run,
        "skip_rebuild": skip_rebuild,
        "before_status_counts": dict(before_counts),
        "after_status_counts": dict(after_counts),
        "merge": merge_stats,
        "scale_benefit": {
            "net_new_rows_on_this_sync": merge_stats["net_new_row_count"],
            "memory_auto_fill_on_net_new_pct": merge_stats["net_new_auto_resolved_pct"],
            "net_new_still_needing_human_review": merge_stats["net_new_needing_human_review_count"],
        },
        "export": {
            "path": repo_relative(EXPORT_PATH),
            "export_event_count": export_report.get("export_event_count"),
            "skipped_approved_without_coordinates": export_report.get("skipped_approved_without_coordinates"),
        },
        "qa_pass": merge_stats["disposition_preserved"],
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Run validate_supplemental_manual_approvals.py. Review net-new pending rows only."
        ),
    }

    if not dry_run:
        save_json_file(APPROVAL_QUEUE_PATH, {"generated_at_utc": generated_at, "approval_queue": merged_queue})
        intake_counts = Counter(row.get("intake_type") for row in merged_queue)
        with_coords = sum(1 for row in merged_queue if row.get("has_coordinates"))
        queue_report = {
            "generated_at_utc": generated_at,
            "phase": "m11_incremental_supplemental_manual_approval_queue",
            "source_feed": repo_relative(STAGING_FEED_PATH),
            "approval_queue_count": len(merged_queue),
            "calendar_only_count": intake_counts.get("calendar_only", 0),
            "parks_only_count": intake_counts.get("parks_only", 0),
            "with_coordinates_count": with_coords,
            "without_coordinates_count": len(merged_queue) - with_coords,
            "approved_count": after_counts.get("approved", 0),
            "rejected_count": after_counts.get("rejected", 0),
            "pending_count": after_counts.get("pending", 0),
            "promotion_allowed_count": 0,
            "status_counts": dict(after_counts),
            "intake_counts": dict(intake_counts),
            "incremental_net_new_count": merge_stats["net_new_row_count"],
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
            "qa_pass": merge_stats["disposition_preserved"],
            "next_required_step": report["next_required_step"],
        }
        save_json_file(QUEUE_REPORT_PATH, queue_report)
        save_json_file(EXPORT_PATH, export_payload)
        save_json_file(DATA_DIR / "reports" / "supplemental_approved_export_feed_report.json", export_report)

    save_json_file(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental supplemental intake with disposition preservation.")
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Skip coverage queue and staging feed rebuild; merge using current staging feed.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only; do not write queue or export feed.")
    args = parser.parse_args()
    report = run(skip_rebuild=args.skip_rebuild, dry_run=args.dry_run)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("qa_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
