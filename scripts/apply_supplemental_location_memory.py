#!/usr/bin/env python3
"""Apply supplemental location memory to staging intake events.

Reads supplemental_events_staging_feed.json and fills missing/low-confidence
coordinates from supplemental_location_memory.json and the gazetteer overlay.

Does NOT approve rows, modify location_cache.json, or publish to the public map.

Outputs:
- updates data/supplemental_events_staging_feed.json (unless --dry-run)
- data/reports/supplemental_memory_auto_resolution_report.json
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
    from scripts.supplemental_location_memory_utils import (
        MEMORY_PATH,
        apply_memory_to_events,
        load_memory_entries,
        needs_memory_fill,
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
    from supplemental_location_memory_utils import (
        MEMORY_PATH,
        apply_memory_to_events,
        load_memory_entries,
        needs_memory_fill,
    )

FEED_PATH = DATA_DIR / "supplemental_events_staging_feed.json"
MANIFEST_PATH = DATA_DIR / "supplemental_events_staging_manifest.json"
STAGING_REPORT_PATH = DATA_DIR / "supplemental_events_staging_report.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_memory_auto_resolution_report.json"


def events_from_feed(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def before_stats(events: list[dict[str, Any]]) -> dict[str, Any]:
    without_coords = sum(
        1 for row in events if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng"))
    )
    needs_fill = sum(1 for row in events if needs_memory_fill(row))
    return {
        "event_count": len(events),
        "with_coordinates_count": len(events) - without_coords,
        "without_coordinates_count": without_coords,
        "needs_memory_fill_count": needs_fill,
    }


def apply_memory_to_staging_feed(
    *,
    feed_path: Any = FEED_PATH,
    dry_run: bool = False,
    write_report: bool = True,
) -> dict[str, Any]:
    feed = load_json_file(feed_path, {})
    events = events_from_feed(feed)
    prior = before_stats(events)
    memory_entries = load_memory_entries()
    updated_events, fill_stats = apply_memory_to_events(events, memory_entries=memory_entries)
    after = before_stats(updated_events)

    generated_at = utc_now_iso()
    report = {
        "artifact_type": "supplemental_memory_auto_resolution_report",
        "generated_at_utc": generated_at,
        "phase": "m11_supplemental_memory_auto_resolution",
        "dry_run": dry_run,
        "source_feed": repo_relative(feed_path),
        "memory_path": repo_relative(MEMORY_PATH),
        "before": prior,
        "after": after,
        "fill": fill_stats,
        "net_new_coordinates_from_memory": after["with_coordinates_count"] - prior["with_coordinates_count"],
        "qa_pass": fill_stats["memory_filled_count"] > 0 or prior["needs_memory_fill_count"] == 0,
        "safety": {
            "location_cache_modified": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "staged_feed_modified": False,
            "manual_review_status": "pending",
        },
        "next_required_step": (
            "Rows remain pending manual review. build_supplemental_manual_approval_queue.py "
            "will include memory-filled coordinates but does not auto-approve."
        ),
    }

    if not dry_run:
        feed_out = dict(feed) if isinstance(feed, dict) else {}
        feed_out["generated_at_utc"] = generated_at
        feed_out["events"] = updated_events
        feed_out["memory_auto_resolution"] = {
            "applied_at_utc": generated_at,
            "memory_filled_count": fill_stats["memory_filled_count"],
            "still_without_coordinates_count": fill_stats["still_without_coordinates_count"],
        }
        save_json_file(feed_path, feed_out)
        _refresh_staging_sidecars(feed_out, fill_stats, generated_at)

    if write_report:
        save_json_file(REPORT_PATH, report)
    return report


def _refresh_staging_sidecars(feed: dict[str, Any], fill_stats: dict[str, Any], generated_at: str) -> None:
    events = events_from_feed(feed)
    with_coords = sum(1 for row in events if valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")))
    manifest = load_json_file(MANIFEST_PATH, {})
    if isinstance(manifest, dict):
        manifest.update(
            {
                "generated_at_utc": generated_at,
                "with_proposed_coordinates_count": with_coords,
                "without_coordinates_count": len(events) - with_coords,
                "memory_auto_filled_count": fill_stats.get("memory_filled_count", 0),
            }
        )
        save_json_file(MANIFEST_PATH, manifest)

    staging_report = load_json_file(STAGING_REPORT_PATH, {})
    if isinstance(staging_report, dict):
        staging_report.update(
            {
                "generated_at_utc": generated_at,
                "with_proposed_coordinates_count": with_coords,
                "without_coordinates_count": len(events) - with_coords,
                "memory_auto_filled_count": fill_stats.get("memory_filled_count", 0),
                "memory_auto_resolution_report": repo_relative(REPORT_PATH),
            }
        )
        save_json_file(STAGING_REPORT_PATH, staging_report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply supplemental location memory to staging intake.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute report only; do not rewrite supplemental_events_staging_feed.json.",
    )
    parser.add_argument(
        "--feed-path",
        type=Path,
        default=FEED_PATH,
        help="Staging feed JSON path (default: data/supplemental_events_staging_feed.json).",
    )
    args = parser.parse_args()
    feed_path = args.feed_path if args.feed_path.is_absolute() else DATA_DIR.parent / args.feed_path
    report = apply_memory_to_staging_feed(
        feed_path=feed_path,
        dry_run=args.dry_run,
        write_report=True,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("qa_pass") else 1


if __name__ == "__main__":
    sys.exit(main())
