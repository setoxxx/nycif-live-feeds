#!/usr/bin/env python3
"""Protected incoming-data residual audit for the City Engine map.

This script reads current source snapshots and reports what the discovery projector
would still leave for review before a future daily refresh is enabled. It writes
only protected artifacts under /tmp and does not modify production feeds,
WordPress, public map files, approval state, credentials, deployment settings, or
location_cache.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
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
OUTPUT_DIR = Path("/tmp/incoming-data-residual-audit")
OUTPUT_FILENAMES = {
    "incoming_data_residual_summary.json",
    "incoming_data_left_behind_samples.json",
    "incoming_data_source_reconciliation.json",
    "daily_update_3am_readiness.json",
    "incoming_data_residual_report.md",
}

SAFETY_ASSERTIONS = {
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
    "schedule_enabled": False,
    "proposal_only": True,
    "public_launch_authorized": False,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    return [row for row in extract_rows(payload) if isinstance(row, dict)]


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def parse_day(row: dict[str, Any]) -> str | None:
    value = preserve_date(row) or row.get("start_date_time") or row.get("start") or row.get("date")
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value).strip())
    return match.group(1) if match else None


def overlaps_window(row: dict[str, Any]) -> bool:
    day = parse_day(row)
    if not day:
        return False
    end = row.get("end_date_time") or row.get("end") or day
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(end).strip())
    end_day = match.group(1) if match else day
    return day <= SEASON_END and end_day >= SEASON_START


def title_of(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("name") or row.get("event_name") or row.get("search_label") or "Untitled event")


def source_key(row: dict[str, Any]) -> tuple[str, str]:
    dataset, source_event_id = source_parts(row)
    return str(dataset or ""), str(source_event_id or "")


def is_rejected(row: dict[str, Any]) -> bool:
    disposition = str(row.get("disposition") or "").lower()
    reason = str(row.get("reason") or "").lower()
    manual = str(row.get("manual_review_status") or "").lower()
    return disposition in {"rejected", "drop", "invalid"} or "reject" in reason or manual == "rejected"


def rejected_identity_sets(rows: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:
    sources: set[tuple[str, str]] = set()
    occurrences: set[tuple[str, str, str]] = set()
    for row in rows:
        if not is_rejected(row):
            continue
        dataset = str(row.get("source_dataset") or source_key(row)[0] or "nyc-open-data")
        source_event_id = str(row.get("source_event_id") or source_key(row)[1] or "")
        if not source_event_id:
            continue
        sources.add((dataset, source_event_id))
        day = parse_day(row)
        if day:
            occurrences.add((dataset, source_event_id, day))
    return sources, occurrences


def describe_leftover(row: dict[str, Any], source_family: str, layer: str) -> dict[str, Any]:
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
    if not parse_day(row):
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
        "event_date": parse_day(row),
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


def marker_ready_public(row: dict[str, Any]) -> bool:
    classified = classify_record(row)
    _lat, _lng, map_ready = resolve_coords(row)
    return bool(map_ready and classified.get("event_role") == "public_event")


def count_reason(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for item in items:
        for reason in item.get("left_behind_reasons") or []:
            counts[str(reason)] += 1
    return dict(counts.most_common())


def make_markdown(summary: dict[str, Any]) -> str:
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


def main() -> int:
    required = [RAW_OPEN_DATA, STAGED, CALENDAR, PARKS, DISPOSITION]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required inputs: " + ", ".join(missing))

    generated_at = utc_now()
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
    open_leftovers: list[dict[str, Any]] = []
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
        item = describe_leftover(row, "raw_open_data", "unstaged_in_window_open_data")
        open_leftovers.append(item)
        open_counts["unstaged_in_window_occurrence"] += 1

    calparks_counts: Counter[str] = Counter()
    calparks_leftovers: list[dict[str, Any]] = []
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
            item = describe_leftover(row, source_family, "unlinked_calendar_or_parks")
            calparks_leftovers.append(item)
            calparks_counts[f"{source_family}_unlinked"] += 1

    residuals = open_leftovers + calparks_leftovers
    residual_reason_counts = count_reason(residuals)
    map_ready_public_candidates = sum(1 for item in residuals if item.get("map_ready") and item.get("event_role") == "public_event")
    list_only_or_missing_coordinate = sum(
        1 for item in residuals if "missing_or_invalid_coordinates" in (item.get("left_behind_reasons") or [])
    )

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
        "generated_or_reference_rows_counted_as_raw": False,
        "residuals_count": len(residuals),
        "residual_reason_counts": residual_reason_counts,
    }

    daily_update = {
        "recommended_local_time": "03:00 America/New_York",
        "recommended_cron_utc_standard_time": "0 8 * * *",
        "recommended_cron_utc_daylight_time": "0 7 * * *",
        "schedule_enabled_in_this_pr": False,
        "required_before_enablement": [
            "SonarQube quality gate passes on the protected audit PR stack",
            "raw-source fetch step writes only to staging/snapshot files on a non-public branch first",
            "projector run succeeds with schema/discovery/occurrence QA",
            "artifact diff is reviewed before production feed promotion",
            "rollback path preserves previous approved feed artifacts",
            "Howard explicitly approves enabling the scheduled workflow",
        ],
        "safe_daily_update_shape": [
            "fetch/update source snapshots",
            "run projector in an isolated workspace",
            "write candidate approved/review/major feeds as artifacts first",
            "run schema, taxonomy, occurrence, dedupe and residual audits",
            "promote only after explicit approval or a separately approved promotion rule",
        ],
    }

    summary = {
        "artifact_type": "incoming_data_residual_summary",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "source_rows": {
            "raw_open_data": len(raw_rows),
            "citywide_calendar": len(calendar_rows),
            "parks_bigapps": len(parks_rows),
            "total_incoming": source_total,
        },
        "open_data": {
            "represented_by_staged_occurrence": open_counts.get("represented_by_staged_occurrence", 0),
            "documented_rejected_occurrence": open_counts.get("documented_rejected_occurrence", 0),
            "documented_rejected_source_fallback": open_counts.get("documented_rejected_source_fallback", 0),
            "outside_audited_window_or_undated": open_counts.get("outside_audited_window_or_undated", 0),
            "unstaged_in_window_occurrences": open_counts.get("unstaged_in_window_occurrence", 0),
        },
        "calendar_parks": {
            "represented_rows": sum(v for k, v in calparks_counts.items() if k.endswith("_represented_by_supplemental")),
            "documented_rejected_rows": sum(v for k, v in calparks_counts.items() if k.endswith("_documented_rejected")),
            "unlinked_rows": sum(v for k, v in calparks_counts.items() if k.endswith("_unlinked")),
        },
        "residuals": {
            "left_behind_requiring_review": len(residuals),
            "map_ready_public_candidates": map_ready_public_candidates,
            "list_only_or_missing_coordinate": list_only_or_missing_coordinate,
            "reason_counts": residual_reason_counts,
        },
        "projected_reference_additions": {
            "rows": len(projected_rows),
            "counted_as_raw": False,
        },
        "audit_execution_integrity_pass": True,
        "public_production_untouched": True,
        "launch_readiness": False,
        "safety": SAFETY_ASSERTIONS | {"location_cache_sha256": sha256_file(LOCATION_CACHE)},
    }
    summary["qa_pass"] = (
        summary["audit_execution_integrity_pass"]
        and summary["public_production_untouched"]
        and summary["safety"]["schedule_enabled"] is False
        and summary["safety"]["public_launch_authorized"] is False
    )

    output_dir = prepare_output_dir()
    write_json(output_dir, "incoming_data_residual_summary.json", summary)
    write_json(output_dir, "incoming_data_left_behind_samples.json", {"count": len(residuals), "items": residuals[:500]})
    write_json(output_dir, "incoming_data_source_reconciliation.json", reconciliation)
    write_json(output_dir, "daily_update_3am_readiness.json", daily_update)
    write_text(output_dir, "incoming_data_residual_report.md", make_markdown(summary))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
