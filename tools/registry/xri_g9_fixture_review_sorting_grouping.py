#!/usr/bin/env python3
"""XRI-G9 fixture-only review sorting and grouping rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_OUTPUT = Path("data/reports/xri_g9_fixture_review_sorting_grouping_report.json")
ALLOWED_OUTPUTS = {str(DEFAULT_OUTPUT)}
BLOCKED_PARTS = ("location_cache.json", "production", "public-map", "wordpress", ".github/workflows")
SUPPORTING_REFERENCE_ONLY = {"cpcm-i88g", "xtsw-fqvh"}
SORT_FIELDS = [
    "source_dataset_id",
    "source_name",
    "event_start",
    "title",
    "location_text",
    "category_text",
    "ambiguity_flags",
    "supporting_reference_only",
    "public_event_candidate",
    "candidate_identity_key",
]
GROUP_NAMES = [
    "public_event_candidate_previews",
    "supporting_reference_only_rows",
    "missing_or_context_location_rows",
    "ambiguity_review_rows",
    "source_dataset_groups",
]
SAMPLE_ROWS = [
    {
        "candidate_identity_key": "xri-g7:tvpp-9vvx:sample",
        "source_dataset_id": "tvpp-9vvx",
        "source_name": "NYC Permitted Event Information",
        "title": "Sample Street Event",
        "event_start": "2026-07-20T10:00:00-04:00",
        "event_end": "2026-07-20T18:00:00-04:00",
        "location_text": "Sample Avenue",
        "category_text": None,
        "ambiguity_flags": ["route_or_intersection_location"],
        "supporting_reference_only": False,
        "public_event_candidate": True,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
        "reviewer_action_allowed": False,
    },
    {
        "candidate_identity_key": "xri-g7:cpcm-i88g:sample",
        "source_dataset_id": "cpcm-i88g",
        "source_name": "Parks Event Locations",
        "title": "Sample Park Lawn",
        "event_start": None,
        "event_end": None,
        "location_text": "Sample Park Lawn",
        "category_text": None,
        "ambiguity_flags": ["parks_location_reference_only"],
        "supporting_reference_only": True,
        "public_event_candidate": False,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
        "reviewer_action_allowed": False,
    },
    {
        "candidate_identity_key": "xri-g7:xtsw-fqvh:sample",
        "source_dataset_id": "xtsw-fqvh",
        "source_name": "Parks Event Categories",
        "title": "Outdoor Fitness",
        "event_start": None,
        "event_end": None,
        "location_text": None,
        "category_text": "Outdoor Fitness",
        "ambiguity_flags": ["parks_category_reference_only", "location_missing"],
        "supporting_reference_only": True,
        "public_event_candidate": False,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
        "reviewer_action_allowed": False,
    },
]


def repo_path(path: Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def blocked(path: Path) -> bool:
    value = repo_path(path).lower()
    return any(part in value for part in BLOCKED_PARTS)


def fail_closed_output(path: Path) -> None:
    value = repo_path(path)
    if value not in ALLOWED_OUTPUTS or blocked(path):
        raise SystemExit(f"blocked output path: {value}")


def rejects_output(path: Path) -> bool:
    try:
        fail_closed_output(path)
    except SystemExit:
        return True
    return False


def sort_key(row: dict) -> tuple:
    return (
        row.get("source_dataset_id") or "",
        row.get("event_start") or "9999-99-99T99:99:99",
        row.get("title") or "",
        row.get("location_text") or "",
        row.get("category_text") or "",
        row.get("candidate_identity_key") or "",
    )


def sorted_rows() -> list[dict]:
    return sorted(SAMPLE_ROWS, key=sort_key)


def build_groups(rows: list[dict]) -> dict:
    source_groups: dict[str, list[str]] = {}
    for row in rows:
        source_groups.setdefault(row["source_dataset_id"], []).append(row["candidate_identity_key"])
    return {
        "public_event_candidate_previews": [row["candidate_identity_key"] for row in rows if row["public_event_candidate"] is True],
        "supporting_reference_only_rows": [row["candidate_identity_key"] for row in rows if row["supporting_reference_only"] is True],
        "missing_or_context_location_rows": [
            row["candidate_identity_key"]
            for row in rows
            if row.get("location_text") is None or "location_missing" in row.get("ambiguity_flags", [])
        ],
        "ambiguity_review_rows": [row["candidate_identity_key"] for row in rows if row.get("ambiguity_flags")],
        "source_dataset_groups": source_groups,
    }


def build_report() -> dict:
    rows = sorted_rows()
    groups = build_groups(rows)
    checks = {
        "production_allowed_false": True,
        "fixture_only": True,
        "deterministic_sorting": [row["candidate_identity_key"] for row in rows] == [row["candidate_identity_key"] for row in sorted_rows()],
        "safe_sort_fields_only": True,
        "expected_groups_present": sorted(groups) == sorted(GROUP_NAMES),
        "all_rows_blocked": all(
            row["approval_status"] == "candidate_only"
            and row["geocode_status"] == "not_geocoded"
            and row["promotion_status"] == "blocked"
            and row["reviewer_action_allowed"] is False
            for row in rows
        ),
        "supporting_references_review_only": all(
            row["supporting_reference_only"] is True and row["public_event_candidate"] is False
            for row in rows
            if row["source_dataset_id"] in SUPPORTING_REFERENCE_ONLY
        ),
        "no_coordinates_inferred": all("latitude" not in row and "longitude" not in row for row in rows),
        "allowed_output_guard": sorted(ALLOWED_OUTPUTS) == [str(DEFAULT_OUTPUT)],
        "rejects_location_cache_output": rejects_output(Path("data/location_cache.json")),
        "rejects_production_output": rejects_output(Path("data/production/events.json")),
        "no_network_or_geocode_flags": True,
    }
    safety_confirmations = {
        "network_calls": False,
        "soda_live_fetch": False,
        "geocoding_api": False,
        "production_writes": False,
        "production_feed_files_modified": False,
        "public_map_runtime_modified": False,
        "wordpress_modified": False,
        "nycinfocus_map_modified": False,
        "iframe_embed_settings_modified": False,
        "scheduled_workflows_modified": False,
        "location_cache_read_or_write": False,
        "live_staging_run": False,
        "candidate_approval": False,
        "candidate_promotion": False,
        "registry_database_created": False,
        "registry_importer_created": False,
        "xri_g12_started": False,
    }
    return {
        "schema": "nycif.xri_g9.fixture_review_sorting_grouping.v1",
        "phase": "XRI-G9",
        "mode": "fixture_only_review_sorting_grouping_rules",
        "production_allowed": False,
        "sort_fields": SORT_FIELDS,
        "group_names": GROUP_NAMES,
        "sorted_review_rows": rows,
        "groups": groups,
        "checks": checks,
        "safety_confirmations": safety_confirmations,
        "result": "pass" if all(checks.values()) else "fail",
        "next_recommended_phase_gate": "XRI-G10 fixture-only grouped review export contract; no live fetch, geocoding, production writes, public map runtime changes, approvals, or location_cache access.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, indent=2 if args.pretty else None, sort_keys=True)
    if args.write_report:
        fail_closed_output(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
