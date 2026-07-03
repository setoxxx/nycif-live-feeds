#!/usr/bin/env python3
"""NYCIF XRI-G6 fixture-only mapping validator.

Validates embedded or approved sample fixture records against the XRI-G5 mapping contract.
No network calls. No SODA live fetch. No geocoding. No production writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "nycif.xri_g6.fixture_mapping_validator.v1"
DEFAULT_INPUT = Path("data/fixtures/xri-g6-mapping-validator.sample.json")
DEFAULT_REPORT = Path("data/reports/xri_g6_fixture_mapping_validator_report.json")
ALLOWED_INPUTS = {str(DEFAULT_INPUT)}
ALLOWED_OUTPUTS = {str(DEFAULT_REPORT)}
BLOCKED_PARTS = (
    "location_cache.json",
    "production",
    "public-map",
    "wordpress",
    ".github/workflows",
)
SUPPORTING_REFERENCE_ONLY = {"cpcm-i88g", "xtsw-fqvh"}

CONTRACT: dict[str, dict[str, Any]] = {
    "tvpp-9vvx": {
        "required": {"source_dataset_id", "source_name", "source_record_id", "title", "location_text", "event_start"},
        "optional": {"event_end", "borough", "category", "description", "source_url", "location_hint"},
        "ambiguity_flags": {"route_or_intersection_location", "time_missing", "borough_uncertain"},
        "role": "primary_event_source",
    },
    "fudw-fgrp": {
        "required": {"source_dataset_id", "source_name", "source_record_id", "title", "event_start"},
        "optional": {"event_end", "description", "category", "borough", "location_text", "source_url", "location_hint"},
        "ambiguity_flags": {"parks_location_reference_present", "location_missing"},
        "role": "primary_parks_event_source",
    },
    "cpcm-i88g": {
        "required": {"source_dataset_id", "source_name", "source_location_id", "location_display_name"},
        "optional": {"borough", "location_hint"},
        "ambiguity_flags": {"parks_location_reference_only", "parks_location_join_required_future_phase", "location_geometry_not_authorized"},
        "role": "supporting_location_reference_only",
    },
    "xtsw-fqvh": {
        "required": {"source_dataset_id", "source_name", "source_category_id", "category_display_name"},
        "optional": set(),
        "ambiguity_flags": {"parks_category_reference_only", "category_join_required_future_phase"},
        "role": "supporting_category_reference_only",
    },
    "6v4b-5gp4": {
        "required": {"source_dataset_id", "source_name", "source_record_id", "title", "event_start"},
        "optional": {"event_end", "description", "borough", "category", "location_text", "source_url", "location_hint"},
        "ambiguity_flags": {"agency_program_location_uncertain", "time_missing", "location_missing"},
        "role": "primary_event_source",
    },
    "3vyj-dkjt": {
        "required": {"source_dataset_id", "source_name", "source_record_id", "title", "event_start"},
        "optional": {"event_end", "description", "borough", "category", "location_text", "source_url"},
        "ambiguity_flags": {"safety_event_context_required", "location_missing", "time_missing", "sensitive_context_review_required"},
        "role": "primary_event_source",
    },
}

EMBEDDED_SAMPLE = {
    "schema": "nycif.xri_g6.mapping_validator.sample.v1",
    "production_allowed": False,
    "purpose": "embedded_fixture_only_validator_sample",
    "parks_relationship": {
        "future_layer": "one enriched Parks Events layer",
        "primary_event_source": "fudw-fgrp",
        "location_reference_source": "cpcm-i88g",
        "category_reference_source": "xtsw-fqvh",
        "live_joiner_created": False,
    },
    "records": [
        {
            "source_dataset_id": "tvpp-9vvx",
            "source_name": "NYC Permitted Event Information",
            "source_record_id": "embedded-tvpp-001",
            "title": "Embedded Street Event",
            "location_text": "Embedded route text",
            "event_start": "2026-07-20T10:00:00-04:00",
            "event_end": "2026-07-20T18:00:00-04:00",
            "ambiguity_flags": ["route_or_intersection_location"],
        },
        {
            "source_dataset_id": "fudw-fgrp",
            "source_name": "Parks Event Listing",
            "source_record_id": "embedded-parks-001",
            "title": "Embedded Park Program",
            "event_start": "2026-07-21T12:00:00-04:00",
            "event_end": "2026-07-21T14:00:00-04:00",
            "location_text": "Embedded Park Lawn",
            "ambiguity_flags": ["parks_location_reference_present"],
        },
        {
            "source_dataset_id": "cpcm-i88g",
            "source_name": "Parks Event Locations",
            "source_location_id": "embedded-location-001",
            "location_display_name": "Embedded Park Lawn",
            "borough": "Brooklyn",
            "ambiguity_flags": ["parks_location_reference_only"],
        },
        {
            "source_dataset_id": "xtsw-fqvh",
            "source_name": "Parks Event Categories",
            "source_category_id": "embedded-category-001",
            "category_display_name": "Embedded Category",
            "ambiguity_flags": ["parks_category_reference_only"],
        },
        {
            "source_dataset_id": "6v4b-5gp4",
            "source_name": "Public Programs Division Special Events",
            "source_record_id": "embedded-ppd-001",
            "title": "Embedded Public Program",
            "event_start": "2026-07-22T11:00:00-04:00",
            "location_text": "Embedded Plaza",
            "ambiguity_flags": ["agency_program_location_uncertain"],
        },
        {
            "source_dataset_id": "3vyj-dkjt",
            "source_name": "Safety Events",
            "source_record_id": "embedded-safety-001",
            "title": "Embedded Safety Event",
            "event_start": "2026-07-23T09:00:00-04:00",
            "ambiguity_flags": ["safety_event_context_required"],
        },
    ],
}


def repo_path(path: Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def has_blocked_part(value: str) -> bool:
    lowered = value.lower()
    return any(part in lowered for part in BLOCKED_PARTS)


def fail_closed_input(path: Path | None) -> None:
    if path is None:
        return
    value = repo_path(path)
    if value not in ALLOWED_INPUTS:
        raise SystemExit(f"blocked input path: {value}")
    if has_blocked_part(value):
        raise SystemExit(f"blocked input path: {value}")


def fail_closed_output(path: Path) -> None:
    value = repo_path(path)
    if value not in ALLOWED_OUTPUTS:
        raise SystemExit(f"blocked output path: {value}")
    if has_blocked_part(value):
        raise SystemExit(f"blocked output path: {value}")


def path_is_rejected_as_input(path: Path) -> bool:
    try:
        fail_closed_input(path)
    except SystemExit:
        return True
    return False


def path_is_rejected_as_output(path: Path) -> bool:
    try:
        fail_closed_output(path)
    except SystemExit:
        return True
    return False


def load_payload(path: Path | None) -> tuple[dict[str, Any], str]:
    fail_closed_input(path)
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8")), repo_path(path)
    return dict(EMBEDDED_SAMPLE), "embedded_sample"


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    source_id = str(record.get("source_dataset_id") or "")
    contract = CONTRACT.get(source_id)
    if contract is None:
        return {
            "source_dataset_id": source_id,
            "valid": False,
            "errors": ["unknown_source_dataset_id"],
            "warnings": [],
        }

    present = {key for key, value in record.items() if value not in (None, "", [])}
    required = contract["required"]
    optional = contract["optional"]
    allowed_flags = contract["ambiguity_flags"]
    supplied_flags = set(record.get("ambiguity_flags") or [])

    missing_required = sorted(required - present)
    unknown_flags = sorted(supplied_flags - allowed_flags)
    recognized_optional = sorted((present & optional))

    errors = []
    warnings = []
    if missing_required:
        errors.append({"missing_required": missing_required})
    if unknown_flags:
        errors.append({"unknown_ambiguity_flags": unknown_flags})
    if source_id in SUPPORTING_REFERENCE_ONLY and "event_start" in present:
        warnings.append("supporting_reference_source_should_not_require_event_time")

    return {
        "source_dataset_id": source_id,
        "role": contract["role"],
        "valid": not errors,
        "missing_required": missing_required,
        "recognized_optional": recognized_optional,
        "recognized_ambiguity_flags": sorted(supplied_flags & allowed_flags),
        "errors": errors,
        "warnings": warnings,
        "supporting_reference_only": source_id in SUPPORTING_REFERENCE_ONLY,
    }


def validate_parks_relationship(payload: dict[str, Any]) -> dict[str, Any]:
    rel = payload.get("parks_relationship") or {}
    checks = {
        "future_layer_one_enriched_parks_events": rel.get("future_layer") == "one enriched Parks Events layer",
        "primary_event_source_fudw_fgrp": rel.get("primary_event_source") == "fudw-fgrp",
        "location_reference_source_cpcm_i88g": rel.get("location_reference_source") == "cpcm-i88g",
        "category_reference_source_xtsw_fqvh": rel.get("category_reference_source") == "xtsw-fqvh",
        "live_joiner_not_created": rel.get("live_joiner_created") is False,
    }
    return {"valid": all(checks.values()), "checks": checks}


def build_report(payload: dict[str, Any], input_source: str) -> dict[str, Any]:
    records = list(payload.get("records", []))
    record_results = [validate_record(record) for record in records]
    parks_result = validate_parks_relationship(payload)
    safety = {
        "network_calls": False,
        "soda_live_fetch": False,
        "geocoding_api": False,
        "production_writes": False,
        "production_feed_files_modified": False,
        "public_map_runtime_modified": False,
        "wordpress_modified": False,
        "scheduled_workflows_modified": False,
        "location_cache_read_or_write": False,
        "candidate_approval": False,
        "candidate_promotion": False,
        "registry_database_created": False,
        "registry_importer_created": False,
        "xri_g12_started": False,
    }
    checks = {
        "production_allowed_false": payload.get("production_allowed") is False,
        "only_known_sources": all(result["source_dataset_id"] in CONTRACT for result in record_results),
        "all_records_valid": all(result["valid"] for result in record_results),
        "supporting_reference_sources_validated": SUPPORTING_REFERENCE_ONLY.issubset({r["source_dataset_id"] for r in record_results}),
        "parks_relationship_contract_only": parks_result["valid"],
        "allowed_input_guard": sorted(ALLOWED_INPUTS) == [str(DEFAULT_INPUT)],
        "allowed_output_guard": sorted(ALLOWED_OUTPUTS) == [str(DEFAULT_REPORT)],
        "rejects_location_cache_input": path_is_rejected_as_input(Path("data/location_cache.json")),
        "rejects_production_input": path_is_rejected_as_input(Path("data/production/events.json")),
        "rejects_arbitrary_input": path_is_rejected_as_input(Path("data/other.json")),
        "rejects_location_cache_output": path_is_rejected_as_output(Path("data/location_cache.json")),
        "rejects_production_output": path_is_rejected_as_output(Path("data/production/events.json")),
        "no_network_or_geocode_flags": safety["network_calls"] is False and safety["geocoding_api"] is False,
    }
    return {
        "schema": SCHEMA,
        "phase": "XRI-G6",
        "mode": "fixture_only_mapping_validator",
        "input_source": input_source,
        "production_allowed": False,
        "record_count": len(records),
        "records": record_results,
        "parks_relationship": parks_result,
        "safety_confirmations": safety,
        "checks": checks,
        "result": "pass" if all(checks.values()) else "fail",
        "allowed_inputs": sorted(ALLOWED_INPUTS),
        "allowed_outputs": sorted(ALLOWED_OUTPUTS),
        "next_recommended_phase_gate": "XRI-G7 can define fixture-only candidate normalization rules; still no live fetch, no geocoding, no production writes, no public map runtime changes, and no location_cache access.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="XRI-G6 fixture-only mapping validator")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    payload, source = load_payload(args.input)
    report = build_report(payload, source)
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
