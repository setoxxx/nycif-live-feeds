#!/usr/bin/env python3
"""NYCIF XRI-G7 fixture-only candidate normalizer.

Turns validated sample mapping records into blocked candidate-preview records.
No network calls. No SODA live fetch. No geocoding. No production writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA = "nycif.xri_g7.fixture_candidate_normalizer.v1"
DEFAULT_INPUT = Path("data/fixtures/xri-g7-candidate-normalizer.sample.json")
DEFAULT_OUTPUT = Path("data/reports/xri_g7_fixture_candidate_normalizer_report.json")
ALLOWED_INPUTS = {str(DEFAULT_INPUT)}
ALLOWED_OUTPUTS = {str(DEFAULT_OUTPUT)}
BLOCKED_PARTS = (
    "location_cache.json",
    "production",
    "public-map",
    "wordpress",
    ".github/workflows",
)
SUPPORTING_REFERENCE_ONLY = {"cpcm-i88g", "xtsw-fqvh"}
PRIMARY_EVENT_SOURCES = {"tvpp-9vvx", "fudw-fgrp", "6v4b-5gp4", "3vyj-dkjt"}

EMBEDDED_SAMPLE = {
    "schema": "nycif.xri_g7.candidate_normalizer.sample.v1",
    "production_allowed": False,
    "purpose": "embedded_fixture_only_candidate_normalizer_sample",
    "records": [
        {
            "source_dataset_id": "tvpp-9vvx",
            "source_name": "NYC Permitted Event Information",
            "source_record_id": "embedded-tvpp-001",
            "title": "Embedded Street Event",
            "location_text": "Embedded route text",
            "event_start": "2026-07-20T10:00:00-04:00",
            "ambiguity_flags": ["route_or_intersection_location"],
        },
        {
            "source_dataset_id": "fudw-fgrp",
            "source_name": "Parks Event Listing",
            "source_record_id": "embedded-parks-001",
            "title": "Embedded Park Program",
            "event_start": "2026-07-21T12:00:00-04:00",
            "location_text": "Embedded Park Lawn",
            "ambiguity_flags": ["parks_location_reference_present"],
        },
        {
            "source_dataset_id": "cpcm-i88g",
            "source_name": "Parks Event Locations",
            "source_location_id": "embedded-location-001",
            "location_display_name": "Embedded Park Lawn",
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


def slug(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "missing"


def load_payload(path: Path | None) -> tuple[dict[str, Any], str]:
    fail_closed_input(path)
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8")), repo_path(path)
    return dict(EMBEDDED_SAMPLE), "embedded_sample"


def stable_source_key(record: dict[str, Any]) -> str:
    for key in ("source_record_id", "source_location_id", "source_category_id"):
        if record.get(key):
            return str(record[key])
    return slug(record.get("title") or record.get("location_display_name") or record.get("category_display_name"))


def candidate_identity_key(record: dict[str, Any]) -> str:
    basis = [
        str(record.get("source_dataset_id") or ""),
        stable_source_key(record),
        slug(record.get("title") or record.get("location_display_name") or record.get("category_display_name")),
        slug(record.get("event_start")),
        slug(record.get("location_text") or record.get("location_display_name")),
    ]
    digest = hashlib.sha256("|".join(basis).encode("utf-8")).hexdigest()[:16]
    return f"xri-g7:{basis[0]}:{digest}"


def normalize_candidate(record: dict[str, Any]) -> dict[str, Any]:
    source_id = str(record.get("source_dataset_id") or "")
    supporting_reference_only = source_id in SUPPORTING_REFERENCE_ONLY
    preview_type = "supporting_reference_only" if supporting_reference_only else "event_candidate_preview"
    title = record.get("title") or record.get("location_display_name") or record.get("category_display_name") or "Untitled sample"
    return {
        "candidate_id": candidate_identity_key(record),
        "candidate_identity_key": candidate_identity_key(record),
        "preview_type": preview_type,
        "source_dataset_id": source_id,
        "source_name": record.get("source_name"),
        "source_owned_key": stable_source_key(record),
        "title": title,
        "event_start": record.get("event_start"),
        "event_end": record.get("event_end"),
        "location_text": record.get("location_text") or record.get("location_display_name"),
        "category_text": record.get("category") or record.get("category_display_name"),
        "ambiguity_flags": list(record.get("ambiguity_flags") or []),
        "supporting_reference_only": supporting_reference_only,
        "public_event_candidate": not supporting_reference_only,
        "production_allowed": False,
        "approval_status": "candidate_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
    }


def build_report(payload: dict[str, Any], input_source: str) -> dict[str, Any]:
    records = list(payload.get("records", []))
    previews = [normalize_candidate(record) for record in records]
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
    supporting_previews = [preview for preview in previews if preview["source_dataset_id"] in SUPPORTING_REFERENCE_ONLY]
    checks = {
        "production_allowed_false": payload.get("production_allowed") is False,
        "all_previews_blocked": all(
            preview["production_allowed"] is False
            and preview["approval_status"] == "candidate_only"
            and preview["geocode_status"] == "not_geocoded"
            and preview["promotion_status"] == "blocked"
            for preview in previews
        ),
        "deterministic_identity_keys_present": all(preview["candidate_identity_key"] for preview in previews),
        "source_location_text_preserved": all(
            preview["source_dataset_id"] in SUPPORTING_REFERENCE_ONLY or preview.get("location_text") is not None
            for preview in previews
        ),
        "ambiguity_flags_preserved": all(isinstance(preview.get("ambiguity_flags"), list) for preview in previews),
        "supporting_references_not_public_candidates": all(
            preview["public_event_candidate"] is False and preview["preview_type"] == "supporting_reference_only"
            for preview in supporting_previews
        ),
        "primary_sources_are_candidate_previews": all(
            preview["preview_type"] == "event_candidate_preview"
            for preview in previews
            if preview["source_dataset_id"] in PRIMARY_EVENT_SOURCES
        ),
        "allowed_input_guard": sorted(ALLOWED_INPUTS) == [str(DEFAULT_INPUT)],
        "allowed_output_guard": sorted(ALLOWED_OUTPUTS) == [str(DEFAULT_OUTPUT)],
        "rejects_location_cache_input": path_is_rejected_as_input(Path("data/location_cache.json")),
        "rejects_production_input": path_is_rejected_as_input(Path("data/production/events.json")),
        "rejects_arbitrary_input": path_is_rejected_as_input(Path("data/other.json")),
        "rejects_location_cache_output": path_is_rejected_as_output(Path("data/location_cache.json")),
        "rejects_production_output": path_is_rejected_as_output(Path("data/production/events.json")),
        "no_network_or_geocode_flags": safety["network_calls"] is False and safety["geocoding_api"] is False,
    }
    return {
        "schema": SCHEMA,
        "phase": "XRI-G7",
        "mode": "fixture_only_candidate_normalizer",
        "input_source": input_source,
        "production_allowed": False,
        "record_count": len(records),
        "candidate_preview_count": len(previews),
        "candidate_previews": previews,
        "safety_confirmations": safety,
        "checks": checks,
        "result": "pass" if all(checks.values()) else "fail",
        "allowed_inputs": sorted(ALLOWED_INPUTS),
        "allowed_outputs": sorted(ALLOWED_OUTPUTS),
        "next_recommended_phase_gate": "XRI-G8 can define fixture-only candidate preview review report formatting; still no live fetch, no geocoding, no production writes, no public map runtime changes, and no location_cache access.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="XRI-G7 fixture-only candidate normalizer")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
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
