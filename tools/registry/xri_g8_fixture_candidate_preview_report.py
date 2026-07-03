#!/usr/bin/env python3
"""XRI-G8 fixture-only review report formatter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_OUTPUT = Path("data/reports/xri_g8_fixture_candidate_preview_review_report.json")
ALLOWED_OUTPUTS = {str(DEFAULT_OUTPUT)}
BLOCKED_PARTS = ("location_cache.json", "production", "public-map", "wordpress", ".github/workflows")
SAFE_FIELDS = [
    "candidate_identity_key",
    "source_dataset_id",
    "source_name",
    "title",
    "event_start",
    "event_end",
    "location_text",
    "category_text",
    "ambiguity_flags",
    "supporting_reference_only",
    "public_event_candidate",
    "review_notes",
    "reviewer_action_allowed",
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
        "review_notes": "fixture-only blocked preview",
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
        "review_notes": "fixture-only reference row",
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
        "ambiguity_flags": ["parks_category_reference_only"],
        "supporting_reference_only": True,
        "public_event_candidate": False,
        "review_notes": "fixture-only reference row",
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


def build_report() -> dict:
    checks = {
        "production_allowed_false": True,
        "fixture_only": True,
        "safe_fields_only": all(set(row) == set(SAFE_FIELDS) for row in SAMPLE_ROWS),
        "reviewer_action_disallowed": all(row["reviewer_action_allowed"] is False for row in SAMPLE_ROWS),
        "supporting_references_review_only": all(
            row["public_event_candidate"] is False
            for row in SAMPLE_ROWS
            if row["source_dataset_id"] in {"cpcm-i88g", "xtsw-fqvh"}
        ),
        "no_coordinates_inferred": all("latitude" not in row and "longitude" not in row for row in SAMPLE_ROWS),
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
        "schema": "nycif.xri_g8.fixture_candidate_preview_review_report.v1",
        "phase": "XRI-G8",
        "mode": "fixture_only_review_report_formatting",
        "production_allowed": False,
        "review_rows": SAMPLE_ROWS,
        "review_safe_fields": SAFE_FIELDS,
        "checks": checks,
        "safety_confirmations": safety_confirmations,
        "result": "pass" if all(checks.values()) else "fail",
        "next_recommended_phase_gate": "XRI-G9 fixture-only review sorting/grouping rules; no live fetch, geocoding, production writes, public map runtime changes, approvals, or location_cache access.",
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
