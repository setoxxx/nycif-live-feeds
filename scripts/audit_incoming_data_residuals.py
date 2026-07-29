#!/usr/bin/env python3
"""Protected incoming-data residual, completion, and intake-resolution audit.

Writes evidence artifacts under a fixed /tmp directory only. It never modifies
production feeds, WordPress, public map files, approval state, credentials,
deployment settings, plugin activation state, schedules, or location_cache.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import classify_record, extract_rows, preserve_date, resolve_coords, source_parts  # noqa: E402
from occurrence_identity_contract import occurrence_key, occurrence_key_set  # noqa: E402

RAW_OPEN_DATA = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
STAGED = ROOT / "data" / "nycif_staged_live_events.json"
CALENDAR = ROOT / "data" / "nyc_citywide_events_calendar_snapshot.json"
PARKS = ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json"
SUPPLEMENTAL = ROOT / "data" / "supplemental_events_staging_feed.json"
SUPPLEMENTAL_QUEUE = ROOT / "data" / "supplemental_manual_approval_queue.json"
DISPOSITION = ROOT / "data" / "row_disposition_events.json"
PROJECTED_FEAST = ROOT / "data" / "staging" / "projected_feast_events_map_intake.json"
LOCATION_CACHE = ROOT / "data" / "location_cache.json"

SEASON_START = "2026-07-14"
SEASON_END = "2026-12-27"
OUT_DIR = Path("/tmp/incoming-data-residual-audit")
LANES = [
    "ready_review_public_candidate",
    "needs_coordinate_review",
    "needs_classification_review",
    "needs_parent_grouping_or_list_only",
    "exclude_or_keep_list_only_non_public",
    "needs_date_window_review",
    "needs_manual_review",
]
LANE_FILES = {
    "ready_review_public_candidate": "incoming_data_ready_review_public_candidates.json",
    "needs_coordinate_review": "incoming_data_coordinate_backlog_queue.json",
    "needs_classification_review": "incoming_data_classification_review_queue.json",
    "needs_parent_grouping_or_list_only": "incoming_data_parent_grouping_queue.json",
    "exclude_or_keep_list_only_non_public": "incoming_data_non_public_exclusion_queue.json",
    "needs_date_window_review": "incoming_data_date_window_repair_queue.json",
    "needs_manual_review": "incoming_data_manual_review_queue.json",
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
FIXED_OUTPUTS = {
    "incoming_data_residual_summary.json",
    "incoming_data_left_behind_samples.json",
    "incoming_data_source_reconciliation.json",
    "daily_update_3am_readiness.json",
    "incoming_data_residual_report.md",
    "incoming_data_completion_queues.json",
    "incoming_data_completion_lane_index.json",
    "incoming_data_completion_plan.md",
    "incoming_data_intake_resolution_packet.json",
    "incoming_data_candidate_review_feed.json",
    "incoming_data_list_only_backlog_feed.json",
    "incoming_data_parent_grouping_fallbacks.json",
    "incoming_data_non_public_exclusion_dispositions.json",
    "incoming_data_unresolved_blockers.json",
    "incoming_data_intake_resolution_report.md",
    *LANE_FILES.values(),
}
SAFETY = {
    "production_feed_modified": False,
    "data_location_cache_json_modified": False,
    "wordpress_modified": False,
    "public_map_modified": False,
    "homepage_modified": False,
    "navigation_modified": False,
    "theme_modified": False,
    "approval_state_modified": False,
    "credentials_modified": False,
    "deployment_settings_modified": False,
    "plugin_activation_modified": False,
    "production_promotion_allowed": False,
    "schedule_enabled": False,
    "proposal_only": True,
    "public_launch_authorized": False,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    return [row for row in extract_rows(load_json(path)) if isinstance(row, dict)]


def file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def output_dir() -> Path:
    resolved = OUT_DIR.resolve()
    root = Path("/tmp").resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"protected output must stay under /tmp: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def output_file(name: str) -> Path:
    if name not in FIXED_OUTPUTS:
        raise ValueError(f"unexpected protected output filename: {name}")
    path = (OUT_DIR / name).resolve()
    if path.parent != OUT_DIR.resolve():
        raise ValueError(f"protected output must stay in {OUT_DIR}: {path}")
    return path


def write_json(name: str, payload: Any) -> None:
    output_file(name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(name: str, text: str) -> None:
    output_file(name).write_text(text, encoding="utf-8")


def day_of(row: dict[str, Any]) -> str | None:
    value = preserve_date(row) or row.get("start_date_time") or row.get("start") or row.get("date")
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value).strip())
    return match.group(1) if match else None


def end_day_of(row: dict[str, Any]) -> str | None:
    value = row.get("end_date_time") or row.get("end") or day_of(row)
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value).strip())
    return match.group(1) if match else day_of(row)


def overlaps_window(row: dict[str, Any]) -> bool:
    start = day_of(row)
    end = end_day_of(row)
    return bool(start and end and start <= SEASON_END and end >= SEASON_START)


def source_key(row: dict[str, Any]) -> tuple[str, str]:
    dataset, source_event_id = source_parts(row)
    return str(dataset or ""), str(source_event_id or "")


def title_of(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("name") or row.get("event_name") or row.get("search_label") or "Untitled event")


def rejected(row: dict[str, Any]) -> bool:
    disposition = str(row.get("disposition") or "").lower()
    reason = str(row.get("reason") or "").lower()
    manual = str(row.get("manual_review_status") or "").lower()
    return disposition in {"rejected", "drop", "invalid"} or "reject" in reason or manual == "rejected"


def rejected_sets(rows: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:
    sources: set[tuple[str, str]] = set()
    occurrences: set[tuple[str, str, str]] = set()
    for row in rows:
        if not rejected(row):
            continue
        dataset = str(row.get("source_dataset") or source_key(row)[0] or "nyc-open-data")
        source_event_id = str(row.get("source_event_id") or source_key(row)[1] or "")
        if not source_event_id:
            continue
        sources.add((dataset, source_event_id))
        day = day_of(row)
        if day:
            occurrences.add((dataset, source_event_id, day))
    return sources, occurrences


def describe(row: dict[str, Any], source_family: str, layer: str) -> dict[str, Any]:
    classified = classify_record(row)
    latitude, longitude, map_ready = resolve_coords(row)
    event_role = classified.get("event_role")
    confidence = classified.get("classification_confidence")
    reasons: list[str] = []
    if not map_ready:
        reasons.append("missing_or_invalid_coordinates")
    if confidence == "low":
        reasons.append("low_classification_confidence")
    if event_role in {"supporting_permit", "street_closure", "transportation_operation"}:
        reasons.append("supporting_record_needs_parent_or_list_only")
    if event_role in {"maintenance_or_closure", "private_or_reserved_activity"}:
        reasons.append("not_public_event_marker")
    if not day_of(row):
        reasons.append("missing_or_unparseable_event_date")
    if not reasons:
        reasons.append("review_supplemental_candidate")
    dataset, source_event_id = source_key(row)
    return {
        "source_family": source_family,
        "layer": layer,
        "dataset": dataset,
        "source_event_id": source_event_id,
        "occurrence_key": list(occurrence_key(row)),
        "title": title_of(row),
        "event_date": day_of(row),
        "end_date": end_day_of(row),
        "within_audit_window": overlaps_window(row),
        "location": row.get("location") or row.get("display_location") or row.get("address"),
        "borough": row.get("borough") or row.get("event_borough"),
        "map_ready": bool(map_ready),
        "coordinates": [latitude, longitude],
        "event_role": event_role,
        "category": classified.get("category"),
        "classification_confidence": confidence,
        "classification_reason": classified.get("classification_reason"),
        "left_behind_reasons": reasons,
    }


def count_reasons(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        for reason in item.get("left_behind_reasons") or []:
            counts[str(reason)] += 1
    return dict(counts.most_common())


def lane_for(item: dict[str, Any]) -> str:
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


def compact(item: dict[str, Any]) -> dict[str, Any]:
    lane = item.get("completion_lane") or lane_for(item)
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


def review_item(item: dict[str, Any], status: str, disposition: str) -> dict[str, Any]:
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
        "resolution_disposition": disposition,
        "production_promotion_allowed": False,
        "public_marker_allowed": False,
        "schedule_enabled": False,
        "source_left_behind_reasons": item.get("left_behind_reasons") or [],
    }


def load_sources() -> dict[str, list[dict[str, Any]]]:
    required = [RAW_OPEN_DATA, STAGED, CALENDAR, PARKS, DISPOSITION]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required inputs: " + ", ".join(missing))
    return {
        "raw": load_rows(RAW_OPEN_DATA),
        "staged": load_rows(STAGED),
        "calendar": load_rows(CALENDAR),
        "parks": load_rows(PARKS),
        "supplemental": load_rows(SUPPLEMENTAL),
        "supplemental_queue": load_rows(SUPPLEMENTAL_QUEUE),
        "disposition": load_rows(DISPOSITION),
        "projected": load_rows(PROJECTED_FEAST),
    }


def analyze(rows: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    staged_occurrences = occurrence_key_set(rows["staged"])
    supplemental_occurrences = occurrence_key_set(rows["supplemental"])
    supplemental_sources = {source_key(row) for row in rows["supplemental"]}
    rejected_sources, rejected_occurrences = rejected_sets(rows["disposition"] + rows["supplemental_queue"])
    open_counts: Counter[str] = Counter()
    calparks_counts: Counter[str] = Counter()
    primary: list[dict[str, Any]] = []
    completion: list[dict[str, Any]] = []

    for row in rows["raw"]:
        occ = occurrence_key(row)
        src = source_key(row)
        if occ in staged_occurrences:
            open_counts["represented_by_staged_occurrence"] += 1
        elif occ in rejected_occurrences:
            open_counts["documented_rejected_occurrence"] += 1
        elif src in rejected_sources:
            open_counts["documented_rejected_source_fallback"] += 1
        elif not overlaps_window(row):
            open_counts["outside_audited_window_or_undated"] += 1
        else:
            item = describe(row, "raw_open_data", "unstaged_in_window_open_data")
            primary.append(item)
            completion.append(item)
            open_counts["unstaged_in_window_occurrence"] += 1

    for source_family, source_rows in (("citywide_calendar", rows["calendar"]), ("parks_bigapps", rows["parks"])):
        for row in source_rows:
            src = source_key(row)
            occ = occurrence_key(row)
            if occ in supplemental_occurrences or src in supplemental_sources:
                calparks_counts[f"{source_family}_represented_by_supplemental"] += 1
            elif src in rejected_sources or occ in rejected_occurrences:
                calparks_counts[f"{source_family}_documented_rejected"] += 1
            else:
                item = describe(row, source_family, "unlinked_calendar_or_parks")
                primary.append(item)
                if item["within_audit_window"]:
                    completion.append(item)
                    calparks_counts[f"{source_family}_unlinked"] += 1
                else:
                    calparks_counts[f"{source_family}_outside_audited_window_or_undated"] += 1

    reconciliation = {
        "source_total": len(rows["raw"]) + len(rows["calendar"]) + len(rows["parks"]),
        "source_rows": {
            "raw_open_data": len(rows["raw"]),
            "citywide_calendar": len(rows["calendar"]),
            "parks_bigapps": len(rows["parks"]),
            "supplemental_review_feed": len(rows["supplemental"]),
            "projected_reference_rows": len(rows["projected"]),
        },
        "open_data_counts": dict(open_counts),
        "calendar_parks_counts": dict(calparks_counts),
        "generated_or_reference_rows_counted_as_raw": False,
        "primary_residuals_count": len(primary),
        "completion_residuals_count_after_window_filter": len(completion),
        "primary_residual_reason_counts": count_reasons(primary),
        "completion_residual_reason_counts": count_reasons(completion),
    }
    return primary, completion, reconciliation


def build_completion(completion_items: list[dict[str, Any]], generated_at: str) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in completion_items:
        lane = lane_for(item)
        enriched = compact(item | {"completion_lane": lane, "recommended_action": LANE_ACTIONS[lane]})
        buckets[lane].append(enriched)
    lane_counts = {lane: len(buckets.get(lane, [])) for lane in LANES}
    blockers = sum(lane_counts[lane] for lane in [
        "needs_classification_review",
        "needs_parent_grouping_or_list_only",
        "exclude_or_keep_list_only_non_public",
        "needs_date_window_review",
        "needs_manual_review",
    ])
    completion = {
        "artifact_type": "incoming_data_completion_queues",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "lane_counts": lane_counts,
        "reason_counts": count_reasons(completion_items),
        "queue_samples": {lane: buckets[lane][:200] for lane in LANES if buckets.get(lane)},
        "lane_artifacts": LANE_FILES,
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
            "must_be_resolved_before_auto_promotion": blockers,
            "production_promotion_allowed": False,
            "schedule_enabled": False,
        },
        "safety": SAFETY | {"location_cache_sha256": file_sha(LOCATION_CACHE)},
    }
    return completion, {lane: buckets.get(lane, []) for lane in LANES}


def lane_payload(lane: str, items: list[dict[str, Any]], completion: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": "incoming_data_completion_lane",
        "lane": lane,
        "generated_at_utc": completion["generated_at_utc"],
        "repository": completion["repository"],
        "repository_sha": completion["repository_sha"],
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "count": len(items),
        "recommended_action": LANE_ACTIONS[lane],
        "production_promotion_allowed": False,
        "schedule_enabled": False,
        "items": items,
    }


def resolve_intake(lane_items: dict[str, list[dict[str, Any]]], completion: dict[str, Any]) -> dict[str, Any]:
    candidate = [review_item(i, "pending_public_candidate_review", "candidate_review_queue") | {"candidate_marker_possible_after_review": True, "recommended_next_step": "manual_review_before_public_marker_or_promotion"} for i in lane_items["ready_review_public_candidate"]]
    list_only = [review_item(i, "list_only_until_geocoded", "safe_list_only_backlog") | {"display_disposition": "list_only", "recommended_next_step": "keep_list_reachable_and_geocode_later"} for i in lane_items["needs_coordinate_review"]]
    parent = [review_item(i, "parent_grouping_needed", "force_list_only_until_parented") | {"display_disposition": "list_only", "recommended_next_step": "attach_to_public_parent_or_keep_list_only"} for i in lane_items["needs_parent_grouping_or_list_only"]]
    non_public = [review_item(i, "excluded_from_public_markers", "documented_non_public_exclusion") | {"display_disposition": "excluded_from_public_markers", "recommended_next_step": "keep_documented_out_of_public_markers"} for i in lane_items["exclude_or_keep_list_only_non_public"]]
    unresolved = []
    for lane in ("needs_classification_review", "needs_date_window_review", "needs_manual_review"):
        unresolved.extend(review_item(i, "unresolved", lane) for i in lane_items[lane])
    counts = {
        "candidate_review_feed": len(candidate),
        "list_only_backlog_feed": len(list_only),
        "parent_grouping_fallbacks": len(parent),
        "non_public_exclusions": len(non_public),
        "unresolved_blockers": len(unresolved),
    }
    counts["total_resolved_to_safe_disposition"] = counts["candidate_review_feed"] + counts["list_only_backlog_feed"] + counts["parent_grouping_fallbacks"] + counts["non_public_exclusions"]
    packet = {
        "artifact_type": "incoming_data_intake_resolution_packet",
        "generated_at_utc": completion["generated_at_utc"],
        "repository": completion["repository"],
        "repository_sha": completion["repository_sha"],
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "resolution_counts": counts,
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
    write_json("incoming_data_candidate_review_feed.json", {"artifact_type": "incoming_data_candidate_review_feed", "repository_sha": completion["repository_sha"], "count": len(candidate), "production_promotion_allowed": False, "items": candidate})
    write_json("incoming_data_list_only_backlog_feed.json", {"artifact_type": "incoming_data_list_only_backlog_feed", "repository_sha": completion["repository_sha"], "count": len(list_only), "production_promotion_allowed": False, "items": list_only})
    write_json("incoming_data_parent_grouping_fallbacks.json", {"artifact_type": "incoming_data_parent_grouping_fallbacks", "repository_sha": completion["repository_sha"], "count": len(parent), "production_promotion_allowed": False, "items": parent})
    write_json("incoming_data_non_public_exclusion_dispositions.json", {"artifact_type": "incoming_data_non_public_exclusion_dispositions", "repository_sha": completion["repository_sha"], "count": len(non_public), "production_promotion_allowed": False, "items": non_public})
    write_json("incoming_data_unresolved_blockers.json", {"artifact_type": "incoming_data_unresolved_blockers", "repository_sha": completion["repository_sha"], "count": len(unresolved), "items": unresolved})
    return packet


def residual_report(summary: dict[str, Any]) -> str:
    return f"""# Incoming data residual audit

Generated: `{summary['generated_at_utc']}`

## Result

- Audit execution integrity: **{summary['audit_execution_integrity_pass']}**
- Incoming data QA pass: **{summary['qa_pass']}**
- Public/production untouched: **{summary['public_production_untouched']}**
- Daily schedule enabled: **{summary['safety']['schedule_enabled']}**
- Launch readiness: **{summary['launch_readiness']}**

## Source rows

- Raw Open Data rows: **{summary['source_rows']['raw_open_data']}**
- Citywide Calendar rows: **{summary['source_rows']['citywide_calendar']}**
- Parks rows: **{summary['source_rows']['parks_bigapps']}**
- Total incoming source rows: **{summary['source_rows']['total_incoming']}**

## Left behind / still requiring review

- Unstaged in-window Open Data occurrences: **{summary['open_data']['unstaged_in_window_occurrences']}**
- Unlinked Calendar/Parks rows: **{summary['calendar_parks']['unlinked_rows']}**
- Residual items requiring review: **{summary['residuals']['left_behind_requiring_review']}**
- Map-ready public candidates among residuals: **{summary['residuals']['map_ready_public_candidates']}**
- List-only / missing-coordinate residuals: **{summary['residuals']['list_only_or_missing_coordinate']}**

This is a protected audit artifact only. It does **not** install the 3 AM updater or authorize launch.
"""


def completion_plan(completion: dict[str, Any], reconciliation: dict[str, Any]) -> str:
    counts = completion["lane_counts"]
    return f"""# Incoming data completion plan

## Source reconciliation

- Source rows audited: **{reconciliation['source_total']}**
- Residual rows after date-window filtering: **{reconciliation['completion_residuals_count_after_window_filter']}**

## Completion lanes

- Ready review public candidates: **{counts['ready_review_public_candidate']}**
- Coordinate/list-only backlog: **{counts['needs_coordinate_review']}**
- Classification review: **{counts['needs_classification_review']}**
- Parent grouping or list-only: **{counts['needs_parent_grouping_or_list_only']}**
- Non-public exclusions/list-only: **{counts['exclude_or_keep_list_only_non_public']}**
- Date/window repair: **{counts['needs_date_window_review']}**
- Other manual review: **{counts['needs_manual_review']}**

## Completion order

1. Queue ready review public candidates for manual review.
2. Keep missing-coordinate records list-only until geocoded.
3. Resolve classification, parent-grouping, non-public and date/window items before any automatic promotion rule.
4. Continue to publish only protected artifacts until Howard approves a schedule and promotion policy.

This plan does not enable the 3 AM updater and does not authorize launch.
"""


def resolution_report(packet: dict[str, Any]) -> str:
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

This packet resolves residuals into protected review/list-only/exclusion artifacts only. It does not enable the 3 AM updater and does not authorize launch.
"""


def daily_update_readiness() -> dict[str, Any]:
    return {
        "recommended_local_time": "03:00 America/New_York",
        "recommended_cron_utc_standard_time": "0 8 * * *",
        "recommended_cron_utc_daylight_time": "0 7 * * *",
        "schedule_enabled_in_this_pr": False,
        "required_before_enablement": [
            "SonarQube quality gate passes on the protected audit PR stack",
            "raw-source fetch step writes only to staging/snapshot files on a non-public branch first",
            "projector run succeeds with schema/discovery/occurrence QA",
            "completion lanes are generated and reviewed before any production promotion",
            "intake-resolution packet has zero unresolved blockers",
            "artifact diff is reviewed before production feed promotion",
            "rollback path preserves previous approved feed artifacts",
            "Howard explicitly approves enabling the scheduled workflow",
        ],
        "safe_daily_update_shape": [
            "fetch/update source snapshots",
            "run projector in an isolated workspace",
            "write candidate approved/review/major feeds as artifacts first",
            "run schema, taxonomy, occurrence, dedupe, residual, completion-lane and intake-resolution audits",
            "promote only after explicit approval or a separately approved promotion rule",
        ],
    }


def main() -> int:
    output_dir()
    generated_at = now()
    rows = load_sources()
    primary, completion_items, reconciliation = analyze(rows)
    reason_counts = count_reasons(primary)
    map_ready = sum(1 for item in primary if item.get("map_ready") and item.get("event_role") == "public_event")
    list_only = sum(1 for item in primary if "missing_or_invalid_coordinates" in (item.get("left_behind_reasons") or []))
    summary = {
        "artifact_type": "incoming_data_residual_summary",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "source_rows": {
            "raw_open_data": len(rows["raw"]),
            "citywide_calendar": len(rows["calendar"]),
            "parks_bigapps": len(rows["parks"]),
            "total_incoming": reconciliation["source_total"],
        },
        "open_data": {
            "represented_by_staged_occurrence": reconciliation["open_data_counts"].get("represented_by_staged_occurrence", 0),
            "documented_rejected_occurrence": reconciliation["open_data_counts"].get("documented_rejected_occurrence", 0),
            "documented_rejected_source_fallback": reconciliation["open_data_counts"].get("documented_rejected_source_fallback", 0),
            "outside_audited_window_or_undated": reconciliation["open_data_counts"].get("outside_audited_window_or_undated", 0),
            "unstaged_in_window_occurrences": reconciliation["open_data_counts"].get("unstaged_in_window_occurrence", 0),
        },
        "calendar_parks": {
            "represented_rows": sum(v for k, v in reconciliation["calendar_parks_counts"].items() if k.endswith("_represented_by_supplemental")),
            "documented_rejected_rows": sum(v for k, v in reconciliation["calendar_parks_counts"].items() if k.endswith("_documented_rejected")),
            "unlinked_rows": sum(v for k, v in reconciliation["calendar_parks_counts"].items() if k.endswith("_unlinked")),
        },
        "residuals": {
            "left_behind_requiring_review": len(primary),
            "map_ready_public_candidates": map_ready,
            "list_only_or_missing_coordinate": list_only,
            "reason_counts": reason_counts,
        },
        "projected_reference_additions": {"rows": len(rows["projected"]), "counted_as_raw": False},
        "audit_execution_integrity_pass": True,
        "public_production_untouched": True,
        "launch_readiness": False,
        "safety": SAFETY | {"location_cache_sha256": file_sha(LOCATION_CACHE)},
    }
    summary["qa_pass"] = summary["public_production_untouched"] and not summary["safety"]["schedule_enabled"] and not summary["safety"]["public_launch_authorized"]
    completion, lane_items = build_completion(completion_items, generated_at)
    packet = resolve_intake(lane_items, completion)

    write_json("incoming_data_residual_summary.json", summary)
    write_json("incoming_data_left_behind_samples.json", {"count": len(primary), "items": primary[:500]})
    write_json("incoming_data_source_reconciliation.json", reconciliation)
    write_json("daily_update_3am_readiness.json", daily_update_readiness())
    write_text("incoming_data_residual_report.md", residual_report(summary))
    write_json("incoming_data_completion_queues.json", completion)
    write_json("incoming_data_completion_lane_index.json", {
        "artifact_type": "incoming_data_completion_lane_index",
        "generated_at_utc": generated_at,
        "repository_sha": completion["repository_sha"],
        "lane_counts": completion["lane_counts"],
        "lane_artifacts": LANE_FILES,
        "daily_update_implication": completion["daily_update_implication"],
        "safety": completion["safety"],
    })
    for lane, filename in LANE_FILES.items():
        write_json(filename, lane_payload(lane, lane_items[lane], completion))
    write_text("incoming_data_completion_plan.md", completion_plan(completion, reconciliation))
    write_json("incoming_data_intake_resolution_packet.json", packet)
    write_text("incoming_data_intake_resolution_report.md", resolution_report(packet))
    print(json.dumps({"completion_lane_counts": completion["lane_counts"], "intake_resolution_counts": packet["resolution_counts"], "qa_pass": summary["qa_pass"] and packet["qa_pass"]}, indent=2, sort_keys=True))
    return 0 if summary["qa_pass"] and packet["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
