#!/usr/bin/env python3
"""Protected intake-resolution packet for incoming data residuals.

This script consumes the completion-lane artifacts already written under /tmp and
assigns every leftover row to a safe intake disposition. It creates reviewable
artifacts only. It does not write repository data files, production feeds,
WordPress, public map files, approval state, credentials, deployment settings,
plugin activation state, schedules, or data/location_cache.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path("/tmp/incoming-data-residual-audit")
OUTPUT_FILENAMES = {
    "incoming_data_intake_resolution_packet.json",
    "incoming_data_candidate_review_feed.json",
    "incoming_data_list_only_backlog_feed.json",
    "incoming_data_parent_grouping_fallbacks.json",
    "incoming_data_non_public_exclusion_dispositions.json",
    "incoming_data_unresolved_blockers.json",
    "incoming_data_intake_resolution_report.md",
}

LANE_FILES = {
    "ready_review_public_candidate": "incoming_data_ready_review_public_candidates.json",
    "needs_coordinate_review": "incoming_data_coordinate_backlog_queue.json",
    "needs_parent_grouping_or_list_only": "incoming_data_parent_grouping_queue.json",
    "exclude_or_keep_list_only_non_public": "incoming_data_non_public_exclusion_queue.json",
    "needs_classification_review": "incoming_data_classification_review_queue.json",
    "needs_date_window_review": "incoming_data_date_window_repair_queue.json",
    "needs_manual_review": "incoming_data_manual_review_queue.json",
}


def prepare_output_dir() -> Path:
    resolved = OUTPUT_DIR.resolve()
    tmp = Path("/tmp").resolve()
    if resolved != tmp and tmp not in resolved.parents:
        raise ValueError(f"protected output must remain under /tmp: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def output_path(output_dir: Path, filename: str) -> Path:
    if filename not in OUTPUT_FILENAMES:
        raise ValueError(f"unexpected protected output filename: {filename}")
    path = (output_dir / filename).resolve()
    if path.parent != output_dir.resolve():
        raise ValueError(f"protected output must stay in {output_dir}: {path}")
    return path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(output_dir: Path, filename: str, payload: Any) -> None:
    output_path(output_dir, filename).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(output_dir: Path, filename: str, text: str) -> None:
    output_path(output_dir, filename).write_text(text, encoding="utf-8")


def items_for_lane(output_dir: Path, lane: str) -> list[dict[str, Any]]:
    payload = load_json(output_dir / LANE_FILES[lane])
    items = payload.get("items") or []
    if not isinstance(items, list):
        raise TypeError(f"lane items must be a list: {lane}")
    return [item for item in items if isinstance(item, dict)]


def review_feed_item(item: dict[str, Any], status: str, resolution: str) -> dict[str, Any]:
    return {
        "source_family": item.get("source_family"),
        "dataset": item.get("dataset"),
        "source_event_id": item.get("source_event_id"),
        "occurrence_key": item.get("occurrence_key"),
        "title": item.get("title"),
        "event_date": item.get("event_date"),
        "borough": item.get("borough"),
        "location": item.get("location"),
        "coordinates": item.get("coordinates"),
        "category": item.get("category"),
        "event_role": item.get("event_role"),
        "classification_confidence": item.get("classification_confidence"),
        "manual_review_status": status,
        "resolution_disposition": resolution,
        "production_promotion_allowed": False,
        "public_marker_allowed": False,
        "schedule_enabled": False,
        "source_left_behind_reasons": item.get("left_behind_reasons") or [],
    }


def candidate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        review_feed_item(item, "pending_public_candidate_review", "candidate_review_queue")
        | {
            "public_marker_allowed": False,
            "candidate_marker_possible_after_review": True,
            "recommended_next_step": "manual_review_before_public_marker_or_promotion",
        }
        for item in items
    ]


def list_only_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        review_feed_item(item, "list_only_until_geocoded", "safe_list_only_backlog")
        | {
            "display_disposition": "list_only",
            "recommended_next_step": "keep_list_reachable_and_geocode_later",
        }
        for item in items
    ]


def parent_fallback_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        review_feed_item(item, "parent_grouping_needed", "force_list_only_until_parented")
        | {
            "display_disposition": "list_only",
            "public_marker_allowed": False,
            "recommended_next_step": "attach_to_public_parent_or_keep_list_only",
        }
        for item in items
    ]


def non_public_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        review_feed_item(item, "excluded_from_public_markers", "documented_non_public_exclusion")
        | {
            "display_disposition": "excluded_from_public_markers",
            "public_marker_allowed": False,
            "recommended_next_step": "keep_documented_out_of_public_markers",
        }
        for item in items
    ]


def make_report(packet: dict[str, Any]) -> str:
    counts = packet["resolution_counts"]
    return f"""# Incoming data intake resolution packet

## Result

- Total residual rows resolved into safe dispositions: **{counts['total_resolved_to_safe_disposition']}**
- Candidate review feed: **{counts['candidate_review_feed']}**
- List-only backlog feed: **{counts['list_only_backlog_feed']}**
- Parent/list-only fallbacks: **{counts['parent_grouping_fallbacks']}**
- Non-public exclusions: **{counts['non_public_exclusions']}**
- Unresolved blockers: **{counts['unresolved_blockers']}**

## Safety

- Production promotion allowed: **{packet['safety']['production_promotion_allowed']}**
- Schedule enabled: **{packet['safety']['schedule_enabled']}**
- Public launch authorized: **{packet['safety']['public_launch_authorized']}**

This packet resolves the residuals into protected review/list-only/exclusion artifacts only. It does not enable the 3 AM updater and does not authorize launch.
"""


def main() -> int:
    output_dir = prepare_output_dir()
    index = load_json(output_dir / "incoming_data_completion_lane_index.json")
    repository_sha = index.get("repository_sha") or os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA")
    generated_at = index.get("generated_at_utc")

    ready = candidate_items(items_for_lane(output_dir, "ready_review_public_candidate"))
    coordinate = list_only_items(items_for_lane(output_dir, "needs_coordinate_review"))
    parent = parent_fallback_items(items_for_lane(output_dir, "needs_parent_grouping_or_list_only"))
    non_public = non_public_items(items_for_lane(output_dir, "exclude_or_keep_list_only_non_public"))

    unresolved = []
    for lane in ("needs_classification_review", "needs_date_window_review", "needs_manual_review"):
        for item in items_for_lane(output_dir, lane):
            unresolved.append(review_feed_item(item, "unresolved", lane))

    resolution_counts = {
        "candidate_review_feed": len(ready),
        "list_only_backlog_feed": len(coordinate),
        "parent_grouping_fallbacks": len(parent),
        "non_public_exclusions": len(non_public),
        "unresolved_blockers": len(unresolved),
    }
    resolution_counts["total_resolved_to_safe_disposition"] = (
        resolution_counts["candidate_review_feed"]
        + resolution_counts["list_only_backlog_feed"]
        + resolution_counts["parent_grouping_fallbacks"]
        + resolution_counts["non_public_exclusions"]
    )

    packet = {
        "artifact_type": "incoming_data_intake_resolution_packet",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": repository_sha,
        "season_start": index.get("season_start"),
        "season_end": index.get("season_end"),
        "resolution_counts": resolution_counts,
        "artifact_files": {
            "candidate_review_feed": "incoming_data_candidate_review_feed.json",
            "list_only_backlog_feed": "incoming_data_list_only_backlog_feed.json",
            "parent_grouping_fallbacks": "incoming_data_parent_grouping_fallbacks.json",
            "non_public_exclusion_dispositions": "incoming_data_non_public_exclusion_dispositions.json",
            "unresolved_blockers": "incoming_data_unresolved_blockers.json",
        },
        "policy": {
            "ready_public_candidates": "manual review queue only; no automatic public marker",
            "coordinate_backlog": "safe list-only backlog until geocoded",
            "parent_grouping": "force list-only unless attached to a public parent",
            "non_public": "documented exclusion from public markers",
            "unresolved": "must remain zero before any future automatic promotion rule",
        },
        "safety": {
            "production_promotion_allowed": False,
            "schedule_enabled": False,
            "public_launch_authorized": False,
            "wordpress_modified": False,
            "public_map_modified": False,
            "data_location_cache_json_modified": False,
        },
        "qa_pass": len(unresolved) == 0,
    }

    write_json(output_dir, "incoming_data_candidate_review_feed.json", {
        "artifact_type": "incoming_data_candidate_review_feed",
        "repository_sha": repository_sha,
        "count": len(ready),
        "production_promotion_allowed": False,
        "items": ready,
    })
    write_json(output_dir, "incoming_data_list_only_backlog_feed.json", {
        "artifact_type": "incoming_data_list_only_backlog_feed",
        "repository_sha": repository_sha,
        "count": len(coordinate),
        "production_promotion_allowed": False,
        "items": coordinate,
    })
    write_json(output_dir, "incoming_data_parent_grouping_fallbacks.json", {
        "artifact_type": "incoming_data_parent_grouping_fallbacks",
        "repository_sha": repository_sha,
        "count": len(parent),
        "production_promotion_allowed": False,
        "items": parent,
    })
    write_json(output_dir, "incoming_data_non_public_exclusion_dispositions.json", {
        "artifact_type": "incoming_data_non_public_exclusion_dispositions",
        "repository_sha": repository_sha,
        "count": len(non_public),
        "production_promotion_allowed": False,
        "items": non_public,
    })
    write_json(output_dir, "incoming_data_unresolved_blockers.json", {
        "artifact_type": "incoming_data_unresolved_blockers",
        "repository_sha": repository_sha,
        "count": len(unresolved),
        "items": unresolved,
    })
    write_json(output_dir, "incoming_data_intake_resolution_packet.json", packet)
    write_text(output_dir, "incoming_data_intake_resolution_report.md", make_report(packet))
    print(json.dumps({"intake_resolution_counts": resolution_counts, "qa_pass": packet["qa_pass"]}, indent=2, sort_keys=True))
    return 0 if packet["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
