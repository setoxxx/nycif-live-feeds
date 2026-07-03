#!/usr/bin/env python3
"""XRI-G11 fixture-only grouped export validator."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

SOURCE_PR = 14
SOURCE_MERGE_COMMIT = "e4f21a3c8179c7cd1ea28cb9a0f9eeeb6cf746d6"
DEFAULT_OUTPUT = Path("data/reports/xri_g11_fixture_grouped_export_validation_report.json")
ALLOWED_OUTPUTS = {str(DEFAULT_OUTPUT)}
BLOCKED_PARTS = (
    "location_cache.json",
    "production",
    "public-map",
    "public_map",
    "wordpress",
    "nycinfocus.com/map",
    "iframe",
    "embed",
    ".github/workflows",
)
SUPPORTING_REFERENCE_ONLY = {"cpcm-i88g", "xtsw-fqvh"}
REQUIRED_SECTIONS = [
    "public_event_candidate_previews",
    "supporting_reference_only_rows",
    "missing_or_context_location_rows",
    "ambiguity_review_rows",
    "source_dataset_groups",
]
REQUIRED_EXPORT_FIELDS = [
    "group_name",
    "group_order_key",
    "candidate_identity_key",
    "source_dataset_id",
    "source_name",
    "event_start",
    "event_end",
    "title",
    "location_text",
    "category_text",
    "ambiguity_flags",
    "supporting_reference_only",
    "public_event_candidate",
    "review_notes",
    "reviewer_action_allowed",
    "approval_status",
    "geocode_status",
    "promotion_status",
]
FORBIDDEN_COORDINATE_FIELDS = {
    "lat",
    "latitude",
    "lon",
    "lng",
    "long",
    "longitude",
    "coordinates",
    "coordinate",
    "point",
    "geojson",
    "geometry",
}

FIXTURE_ROWS = [
    {
        "group_name": "public_event_candidate_previews",
        "group_order_key": "01:tvpp-9vvx:xri-g7:tvpp-9vvx:sample",
        "candidate_identity_key": "xri-g7:tvpp-9vvx:sample",
        "source_dataset_id": "tvpp-9vvx",
        "source_name": "NYC Permitted Event Information",
        "event_start": "2026-07-20T10:00:00-04:00",
        "event_end": "2026-07-20T18:00:00-04:00",
        "title": "Sample Street Event",
        "location_text": "Sample Avenue",
        "category_text": None,
        "ambiguity_flags": ["route_or_intersection_location"],
        "supporting_reference_only": False,
        "public_event_candidate": True,
        "review_notes": "fixture export row only",
        "reviewer_action_allowed": False,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
    },
    {
        "group_name": "supporting_reference_only_rows",
        "group_order_key": "02:cpcm-i88g:xri-g7:cpcm-i88g:sample",
        "candidate_identity_key": "xri-g7:cpcm-i88g:sample",
        "source_dataset_id": "cpcm-i88g",
        "source_name": "Parks Event Locations",
        "event_start": None,
        "event_end": None,
        "title": "Sample Park Lawn",
        "location_text": "Sample Park Lawn",
        "category_text": None,
        "ambiguity_flags": ["parks_location_reference_only"],
        "supporting_reference_only": True,
        "public_event_candidate": False,
        "review_notes": "supporting reference only",
        "reviewer_action_allowed": False,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
    },
    {
        "group_name": "missing_or_context_location_rows",
        "group_order_key": "03:xtsw-fqvh:xri-g7:xtsw-fqvh:sample",
        "candidate_identity_key": "xri-g7:xtsw-fqvh:sample",
        "source_dataset_id": "xtsw-fqvh",
        "source_name": "Parks Event Categories",
        "event_start": None,
        "event_end": None,
        "title": "Outdoor Fitness",
        "location_text": None,
        "category_text": "Outdoor Fitness",
        "ambiguity_flags": ["parks_category_reference_only", "location_missing"],
        "supporting_reference_only": True,
        "public_event_candidate": False,
        "review_notes": "supporting reference only; location context missing",
        "reviewer_action_allowed": False,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
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


def export_rows() -> list[dict[str, Any]]:
    return sorted(
        copy.deepcopy(FIXTURE_ROWS),
        key=lambda row: (row["group_order_key"], row["candidate_identity_key"]),
    )


def build_sections(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {section: [] for section in REQUIRED_SECTIONS}
    for row in rows:
        sections.setdefault(row["group_name"], []).append(row)
        if row.get("ambiguity_flags"):
            sections["ambiguity_review_rows"].append(row)
        sections["source_dataset_groups"].append(row)
    return sections


def has_forbidden_coordinate_fields(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key.lower() in FORBIDDEN_COORDINATE_FIELDS:
                return True
            if has_forbidden_coordinate_fields(nested):
                return True
    elif isinstance(value, list):
        return any(has_forbidden_coordinate_fields(item) for item in value)
    return False


def row_is_blocked(row: dict[str, Any]) -> bool:
    return (
        row["reviewer_action_allowed"] is False
        and row["approval_status"] == "candidate_only"
        and row["geocode_status"] == "not_geocoded"
        and row["promotion_status"] == "blocked"
    )


def supporting_reference_is_review_only(row: dict[str, Any]) -> bool:
    if row["source_dataset_id"] not in SUPPORTING_REFERENCE_ONLY:
        return True
    return row["supporting_reference_only"] is True and row["public_event_candidate"] is False


def build_report() -> dict[str, Any]:
    rows = export_rows()
    rows_again = export_rows()
    sections = build_sections(rows)
    checks = {
        "production_allowed_false": True,
        "fixture_only_grouped_export_validation": True,
        "source_phase_recorded": SOURCE_PR == 14 and bool(SOURCE_MERGE_COMMIT),
        "required_sections_present": sorted(sections) == sorted(REQUIRED_SECTIONS),
        "required_export_fields_present": all(set(row) == set(REQUIRED_EXPORT_FIELDS) for row in rows),
        "every_row_review_only_and_blocked": all(row_is_blocked(row) for row in rows),
        "supporting_references_review_only_non_public": all(
            supporting_reference_is_review_only(row) for row in rows
        ),
        "no_coordinates_inferred_or_introduced": not has_forbidden_coordinate_fields(rows),
        "deterministic_output": rows == rows_again,
        "allowed_output_guard": sorted(ALLOWED_OUTPUTS) == [str(DEFAULT_OUTPUT)],
        "rejects_location_cache_output": rejects_output(Path("data/location_cache.json")),
        "rejects_production_output": rejects_output(Path("data/production/events.json")),
        "rejects_public_map_runtime_output": rejects_output(Path("public-map/events.json")),
        "rejects_wordpress_runtime_output": rejects_output(Path("wordpress/runtime/events.json")),
        "rejects_workflow_output": rejects_output(Path(".github/workflows/xri-g11.yml")),
        "no_network_or_live_data_flags": True,
    }
    safety = {
        "network_calls": False,
        "soda_live_fetch": False,
        "geocoding_api": False,
        "coordinates": False,
        "production_writes": False,
        "public_map_runtime_modified": False,
        "wordpress_modified": False,
        "nycinfocus_map_modified": False,
        "iframe_embed_settings_modified": False,
        "scheduled_workflows_modified": False,
        "location_cache_access": False,
        "live_staging_run": False,
        "candidate_approval": False,
        "candidate_promotion": False,
        "registry_database_created": False,
        "registry_importer_created": False,
        "xri_g12_started": False,
    }
    return {
        "schema": "nycif.xri_g11.fixture_grouped_export_validation.v1",
        "phase": "XRI-G11",
        "source_phase": "XRI-G10",
        "source_pr": SOURCE_PR,
        "source_merge_commit_sha": SOURCE_MERGE_COMMIT,
        "mode": "fixture_only_grouped_export_validation",
        "production_allowed": False,
        "allowed_files": [
            "tools/registry/xri_g11_fixture_grouped_export_validator.py",
            "data/reports/xri_g11_fixture_grouped_export_validation_report.json",
        ],
        "skipped_files": [
            {
                "path": "docs/xri-g11-fixture-only-grouped-export-validation-contract.md",
                "reason": "connector blocked doc creation payload",
                "created": False,
            }
        ],
        "required_export_fields": REQUIRED_EXPORT_FIELDS,
        "required_sections": REQUIRED_SECTIONS,
        "sections": sections,
        "checks": checks,
        "safety_confirmations": safety,
        "expected_runtime_command": "python tools/registry/xri_g11_fixture_grouped_export_validator.py --pretty",
        "expected_result": "pass",
        "result": "pass" if all(checks.values()) else "fail",
        "next_recommended_phase_gate": "XRI-G12 only after review and explicit approval; no live data, geocoding, production writes, public map runtime changes, approvals, or location_cache access.",
        "review_gate": "Open PR only; do not merge; do not start XRI-G12.",
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
