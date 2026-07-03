#!/usr/bin/env python3
"""NYCIF XRI-G4 read-only candidate extractor prototype.

Sample-only. Dry-run by default. No network calls. No geocoding.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "nycif.xri_g4.registry_candidate_extractor_prototype.v1"
DEFAULT_INPUT = Path("data/fixtures/registry-candidate-extractor.sample.json")
DEFAULT_REPORT = Path("data/reports/registry_candidate_extractor_prototype_report.json")
ALLOWED_OUTPUTS = {str(DEFAULT_REPORT)}
BLOCKED_PARTS = (
    "location_cache.json",
    "production",
    "public-map",
    "wordpress",
    ".github/workflows",
)

EMBEDDED_SAMPLE = [
    {
        "source_dataset_id": "tvpp-9vvx",
        "source_record_id": "embedded-001",
        "title": "Embedded Sample Event One",
        "borough": "Manhattan",
        "location_text": "Sample location text",
        "event_start": "2026-07-15T10:00:00-04:00",
        "event_end": "2026-07-15T18:00:00-04:00",
    },
    {
        "source_dataset_id": "fudw-fgrp",
        "source_record_id": "embedded-002",
        "title": "Embedded Sample Event Two",
        "borough": "Brooklyn",
        "location_text": "Sample location text",
        "event_start": "2026-07-16T19:00:00-04:00",
        "event_end": "2026-07-16T21:00:00-04:00",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fail_closed_output(path: Path) -> None:
    value = str(path).replace("\\", "/")
    if value not in ALLOWED_OUTPUTS:
        raise SystemExit(f"blocked output path: {value}")
    lowered = value.lower()
    if any(part in lowered for part in BLOCKED_PARTS):
        raise SystemExit(f"blocked output path: {value}")


def load_rows(path: Path | None) -> tuple[list[dict[str, Any]], str]:
    if path and path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("items", [])), str(path)
    return list(EMBEDDED_SAMPLE), "embedded_sample"


def make_candidate(row: dict[str, Any]) -> dict[str, Any]:
    source_dataset_id = str(row.get("source_dataset_id") or "unknown")
    source_record_id = str(row.get("source_record_id") or "unknown")
    return {
        "candidate_id": f"xri-g4::{source_dataset_id}::{source_record_id}",
        "source_dataset_id": source_dataset_id,
        "source_record_id": source_record_id,
        "title": row.get("title"),
        "borough": row.get("borough"),
        "location_text": row.get("location_text"),
        "event_start": row.get("event_start"),
        "event_end": row.get("event_end"),
        "production_allowed": False,
        "approval_status": "prototype_only",
        "geocode_status": "not_geocoded",
        "promotion_status": "blocked",
        "confidence": "not_scored",
        "notes": [
            "sample-only candidate preview",
            "no geocode generated",
            "not eligible for production publishing",
        ],
    }


def build_report(rows: list[dict[str, Any]], input_source: str) -> dict[str, Any]:
    candidates = [make_candidate(row) for row in rows]
    return {
        "schema": SCHEMA,
        "generated_at": utc_now(),
        "phase": "XRI-G4",
        "mode": "read_only_prototype",
        "input_source": input_source,
        "candidate_count": len(candidates),
        "production_allowed": False,
        "safety": {
            "network_calls": False,
            "soda_live_fetch": False,
            "geocoding_api": False,
            "production_feed_writes": False,
            "public_map_runtime_changes": False,
            "wordpress_changes": False,
            "scheduled_workflow_changes": False,
            "location_cache_read_or_write": False,
            "candidate_approval": False,
            "candidate_promotion": False,
            "registry_database_created": False,
            "xri_g12_started": False,
        },
        "allowed_outputs": sorted(ALLOWED_OUTPUTS),
        "candidates": candidates,
    }


def self_check() -> dict[str, Any]:
    rows, source = load_rows(None)
    report = build_report(rows, source)
    checks = {
        "production_allowed_false": report["production_allowed"] is False,
        "all_candidates_blocked": all(
            item["production_allowed"] is False and item["promotion_status"] == "blocked"
            for item in report["candidates"]
        ),
        "allowed_output_guard": sorted(ALLOWED_OUTPUTS) == [str(DEFAULT_REPORT)],
        "no_network_or_geocode_flags": report["safety"]["network_calls"] is False
        and report["safety"]["geocoding_api"] is False,
    }
    return {
        "result": "pass" if all(checks.values()) else "fail",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="XRI-G4 read-only candidate extractor prototype")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    if args.self_check:
        print(json.dumps(self_check(), indent=2, sort_keys=True))
        return 0

    rows, source = load_rows(args.input)
    report = build_report(rows, source)
    text = json.dumps(report, indent=2 if args.pretty else None, sort_keys=True)

    if args.write_report:
        fail_closed_output(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
