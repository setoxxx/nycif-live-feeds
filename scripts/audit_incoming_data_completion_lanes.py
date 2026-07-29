#!/usr/bin/env python3
"""Protected completion-lane audit for incoming data residuals.

This is a second-stage artifact builder for the residual audit. It turns the
left-behind source rows into action lanes so a future 3 AM updater can refresh
candidate artifacts without promoting unresolved rows to production.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_incoming_data_residuals import (  # noqa: E402
    CALENDAR,
    DISPOSITION,
    LOCATION_CACHE,
    OUTPUT_DIR,
    PARKS,
    PROJECTED_FEAST,
    RAW_OPEN_DATA,
    SAFETY_ASSERTIONS,
    SEASON_END,
    SEASON_START,
    STAGED,
    SUPPLEMENTAL,
    SUPPLEMENTAL_QUEUE,
    count_reason,
    describe_leftover,
    load_rows,
    overlaps_window,
    rejected_identity_sets,
    sha256_file,
    source_key,
    utc_now,
)
from occurrence_identity_contract import occurrence_key, occurrence_key_set  # noqa: E402

LANE_ORDER = [
    "ready_review_public_candidate",
    "needs_coordinate_review",
    "needs_classification_review",
    "needs_parent_grouping_or_list_only",
    "exclude_or_keep_list_only_non_public",
    "needs_date_window_review",
    "needs_manual_review",
]

LANE_OUTPUTS = {
    "ready_review_public_candidate": "incoming_data_ready_review_public_candidates.json",
    "needs_coordinate_review": "incoming_data_coordinate_backlog_queue.json",
    "needs_classification_review": "incoming_data_classification_review_queue.json",
    "needs_parent_grouping_or_list_only": "incoming_data_parent_grouping_queue.json",
    "exclude_or_keep_list_only_non_public": "incoming_data_non_public_exclusion_queue.json",
    "needs_date_window_review": "incoming_data_date_window_repair_queue.json",
    "needs_manual_review": "incoming_data_manual_review_queue.json",
}

OUTPUT_FILENAMES = {
    "incoming_data_completion_queues.json",
    "incoming_data_completion_plan.md",
    "incoming_data_completion_lane_index.json",
    *LANE_OUTPUTS.values(),
}

LANE_ACTIONS = {
    "ready_review_public_candidate": "queue_for_manual_review_feed_candidate",
    "needs_coordinate_review": "geocode_or_keep_list_only_until_resolved",
    "needs_classification_review": "manual_category_and_role_review",
    "needs_parent_grouping_or_list_only": "attach_to_public_parent_or_force_list_only",
    "exclude_or_keep_list_only_non_public": "exclude_from_public_markers_and_keep_documented",
    "needs_date_window_review": "fix_event_date_or_exclude_from_daily_update_window",
    "needs_manual_review": "manual_review_before_auto_update",
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


def write_json(output_dir: Path, filename: str, payload: Any) -> None:
    output_path(output_dir, filename).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(output_dir: Path, filename: str, text: str) -> None:
    output_path(output_dir, filename).write_text(text, encoding="utf-8")


def completion_lane(item: dict[str, Any]) -> str:
    reasons = set(item.get("left_behind_reasons") or [])
    if "not_public_event_marker" in reasons:
        return "exclude_or_keep_list_only_non_public"
    if "supporting_record_needs_parent_or_list_only" in reasons:
        return "needs_parent_grouping_or_list_only"
    if "missing_or_unparseable_event_date" in reasons or not item.get("within_audit_window", True):
        return "needs_date_window_review"
    if "missing_or_invalid_coordinates" in reasons:
        return "needs_coordinate_review"
    if "low_classification_confidence" in reasons:
        return "needs_classification_review"
    if item.get("map_ready") and item.get("event_role") == "public_event":
        return "ready_review_public_candidate"
    return "needs_manual_review"


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    lane = item.get("completion_lane") or completion_lane(item)
    return {
        "lane": lane,
        "source_family": item.get("source_family"),
        "layer": item.get("layer"),
        "dataset": item.get("dataset"),
        "source_event_id": item.get("source_event_id"),
        "occurrence_key": item.get("occurrence_key"),
        "title": item.get("title"),
        "event_date": item.get("event_date"),
        "end_date": item.get("end_date"),
        "within_audit_window": item.get("within_audit_window", True),
        "borough": item.get("borough"),
        "location": item.get("location"),
        "coordinates": item.get("coordinates"),
        "category": item.get("category"),
        "event_role": item.get("event_role"),
        "classification_confidence": item.get("classification_confidence"),
        "left_behind_reasons": item.get("left_behind_reasons"),
        "recommended_action": LANE_ACTIONS[lane],
    }


def residual_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_rows = load_rows(RAW_OPEN_DATA)
    staged_rows = load_rows(STAGED)
    calendar_rows = load_rows(CALENDAR)
    parks_rows = load_rows(PARKS)
    supplemental_rows = load_rows(SUPPLEMENTAL)
    supplemental_queue_rows = load_rows(SUPPLEMENTAL_QUEUE)
    disposition_rows = load_rows(DISPOSITION)
    projected_rows = load_rows(PROJECTED_FEAST)

    staged_occurrences = occurrence_key_set(staged_rows)
    supplemental_occurrences = occurrence_key_set(supplemental_rows)
    supplemental_sources = {source_key(row) for row in supplemental_rows}
    rejected_sources, rejected_occurrences = rejected_identity_sets(disposition_rows + supplemental_queue_rows)

    open_counts: Counter[str] = Counter()
    residuals: list[dict[str, Any]] = []
    for row in raw_rows:
        occ = occurrence_key(row)
        src = source_key(row)
        if occ in staged_occurrences:
            open_counts["represented_by_staged_occurrence"] += 1
            continue
        if occ in rejected_occurrences:
            open_counts["documented_rejected_occurrence"] += 1
            continue
        if src in rejected_sources:
            open_counts["documented_rejected_source_fallback"] += 1
            continue
        if not overlaps_window(row):
            open_counts["outside_audited_window_or_undated"] += 1
            continue
        open_counts["unstaged_in_window_occurrence"] += 1
        residuals.append(describe_leftover(row, "raw_open_data", "unstaged_in_window_open_data"))

    calparks_counts: Counter[str] = Counter()
    for source_family, rows in (("citywide_calendar", calendar_rows), ("parks_bigapps", parks_rows)):
        for row in rows:
            src = source_key(row)
            occ = occurrence_key(row)
            if occ in supplemental_occurrences or src in supplemental_sources:
                calparks_counts[f"{source_family}_represented_by_supplemental"] += 1
                continue
            if src in rejected_sources or occ in rejected_occurrences:
                calparks_counts[f"{source_family}_documented_rejected"] += 1
                continue
            if not overlaps_window(row):
                calparks_counts[f"{source_family}_outside_audited_window_or_undated"] += 1
                continue
            calparks_counts[f"{source_family}_unlinked"] += 1
            residuals.append(describe_leftover(row, source_family, "unlinked_calendar_or_parks"))

    source_total = len(raw_rows) + len(calendar_rows) + len(parks_rows)
    reconciliation = {
        "source_total": source_total,
        "source_rows": {
            "raw_open_data": len(raw_rows),
            "citywide_calendar": len(calendar_rows),
            "parks_bigapps": len(parks_rows),
            "supplemental_review_feed": len(supplemental_rows),
            "projected_reference_rows": len(projected_rows),
        },
        "open_data_counts": dict(open_counts),
        "calendar_parks_counts": dict(calparks_counts),
        "residuals_count_after_window_filter": len(residuals),
        "generated_or_reference_rows_counted_as_raw": False,
    }
    return residuals, reconciliation


def build_completion_queues(residuals: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in residuals:
        lane = completion_lane(item)
        item["completion_lane"] = lane
        item["recommended_action"] = LANE_ACTIONS[lane]
        buckets[lane].append(compact_item(item))

    lane_counts = {lane: len(buckets.get(lane, [])) for lane in LANE_ORDER}
    auto_promotion_blockers = (
        lane_counts["needs_classification_review"]
        + lane_counts["needs_parent_grouping_or_list_only"]
        + lane_counts["exclude_or_keep_list_only_non_public"]
        + lane_counts["needs_date_window_review"]
        + lane_counts["needs_manual_review"]
    )
    queue_samples = {
        lane: buckets.get(lane, [])[:200]
        for lane in LANE_ORDER
        if buckets.get(lane)
    }
    completion = {
        "artifact_type": "incoming_data_completion_queues",
        "generated_at_utc": utc_now(),
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "lane_counts": lane_counts,
        "reason_counts": count_reason(residuals),
        "queue_samples": queue_samples,
        "lane_artifacts": LANE_OUTPUTS,
        "completion_policy": {
            "ready_review_public_candidate": "Queue into manual review feed candidates only; do not auto-promote to production.",
            "needs_coordinate_review": "Keep list-only until geocoded; this can coexist with a safe artifact refresh.",
            "needs_classification_review": "Requires category/role confidence before automatic promotion.",
            "needs_parent_grouping_or_list_only": "Attach to public parent or force list-only.",
            "exclude_or_keep_list_only_non_public": "Must not become a public map marker.",
            "needs_date_window_review": "Fix event date or exclude from daily update window.",
            "needs_manual_review": "Manual inspection required before automation.",
        },
        "daily_update_implication": {
            "safe_candidate_review_queue_count": lane_counts["ready_review_public_candidate"],
            "coordinate_backlog_can_be_list_only": lane_counts["needs_coordinate_review"],
            "must_be_resolved_before_auto_promotion": auto_promotion_blockers,
            "production_promotion_allowed": False,
            "schedule_enabled": False,
        },
        "safety": SAFETY_ASSERTIONS | {"location_cache_sha256": sha256_file(LOCATION_CACHE)},
    }
    return completion, {lane: buckets.get(lane, []) for lane in LANE_ORDER}


def make_lane_payload(lane: str, items: list[dict[str, Any]], completion: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "incoming_data_completion_lane",
        "lane": lane,
        "generated_at_utc": completion["generated_at_utc"],
        "repository": completion["repository"],
        "repository_sha": completion["repository_sha"],
        "season_start": completion["season_start"],
        "season_end": completion["season_end"],
        "count": len(items),
        "recommended_action": LANE_ACTIONS[lane],
        "production_promotion_allowed": False,
        "schedule_enabled": False,
        "items": items,
    }


def make_lane_index(completion: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "incoming_data_completion_lane_index",
        "generated_at_utc": completion["generated_at_utc"],
        "repository_sha": completion["repository_sha"],
        "lane_counts": completion["lane_counts"],
        "lane_artifacts": completion["lane_artifacts"],
        "daily_update_implication": completion["daily_update_implication"],
        "safety": completion["safety"],
    }


def make_plan(completion: dict[str, Any], reconciliation: dict[str, Any]) -> str:
    counts = completion["lane_counts"]
    return f"""# Incoming data completion plan

## Source reconciliation

- Source rows audited: **{reconciliation['source_total']}**
- Residual rows after date-window filtering: **{reconciliation['residuals_count_after_window_filter']}**

## Completion lanes

- Ready review public candidates: **{counts.get('ready_review_public_candidate', 0)}**
- Coordinate/list-only backlog: **{counts.get('needs_coordinate_review', 0)}**
- Classification review: **{counts.get('needs_classification_review', 0)}**
- Parent grouping or list-only: **{counts.get('needs_parent_grouping_or_list_only', 0)}**
- Non-public exclusions/list-only: **{counts.get('exclude_or_keep_list_only_non_public', 0)}**
- Date/window repair: **{counts.get('needs_date_window_review', 0)}**
- Other manual review: **{counts.get('needs_manual_review', 0)}**

## Full lane artifacts

- `incoming_data_ready_review_public_candidates.json`
- `incoming_data_coordinate_backlog_queue.json`
- `incoming_data_classification_review_queue.json`
- `incoming_data_parent_grouping_queue.json`
- `incoming_data_non_public_exclusion_queue.json`
- `incoming_data_date_window_repair_queue.json`
- `incoming_data_manual_review_queue.json`

## Completion order

1. Queue ready review public candidates for manual review.
2. Keep missing-coordinate records list-only until geocoded.
3. Resolve classification, parent-grouping, non-public and date/window items before any automatic promotion rule.
4. Continue to publish only protected artifacts until Howard approves a schedule and promotion policy.

This plan does not enable the 3 AM updater and does not authorize launch.
"""


def main() -> int:
    residuals, reconciliation = residual_rows()
    completion, lane_items = build_completion_queues(residuals)
    output_dir = prepare_output_dir()
    write_json(output_dir, "incoming_data_completion_queues.json", completion)
    write_json(output_dir, "incoming_data_completion_lane_index.json", make_lane_index(completion))
    for lane, filename in LANE_OUTPUTS.items():
        write_json(output_dir, filename, make_lane_payload(lane, lane_items.get(lane, []), completion))
    write_text(output_dir, "incoming_data_completion_plan.md", make_plan(completion, reconciliation))
    print(json.dumps({"completion_lane_counts": completion["lane_counts"], **completion["daily_update_implication"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
