#!/usr/bin/env python3
"""Project staged + supplemental feeds into schema_version 1.0 envelopes.

Does not modify protected location_cache or rewrite staged feed files in place.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import (  # noqa: E402
    SCHEMA_VERSION,
    envelope,
    extract_events,
    project_event,
    reset_stable_id_registry,
    utc_now,
)

STAGED_PATH = ROOT / "data" / "nycif_staged_live_events.json"
SUPPLEMENTAL_PATH = ROOT / "data" / "supplemental_events_staging_feed.json"
OUT_STAGED = ROOT / "data" / "events_schema_v1_staged.json"
OUT_SUPP = ROOT / "data" / "events_schema_v1_supplemental_review.json"
OUT_REPORT = ROOT / "data" / "events_schema_v1_validation_report.json"


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def validate_event(event: dict, errors: list[str], prefix: str) -> None:
    required = [
        "id",
        "title",
        "category",
        "start_date_time",
        "end_date_time",
        "timezone",
        "borough",
        "location",
        "latitude",
        "longitude",
        "significance",
        "source",
    ]
    for key in required:
        if key not in event:
            errors.append(f"{prefix}: missing field {key}")
    source = event.get("source")
    if not isinstance(source, dict) or "dataset" not in source or "source_event_id" not in source:
        errors.append(f"{prefix}: source must include dataset and source_event_id")
    lat, lng = event.get("latitude"), event.get("longitude")
    if (lat is None) != (lng is None):
        errors.append(f"{prefix}: latitude/longitude must both be set or both null")
    if "lat" in event or "lng" in event:
        errors.append(f"{prefix}: legacy lat/lng leaked")
    nycif = event.get("nycif") or {}
    if nycif.get("data_layer") == "review_supplemental":
        if nycif.get("promotion_allowed") is True:
            errors.append(f"{prefix}: supplemental promotion_allowed true")
        if nycif.get("production_feed") is True:
            errors.append(f"{prefix}: supplemental production_feed true")
        if not str(event.get("id", "")).startswith("review_supplemental:"):
            errors.append(f"{prefix}: supplemental id not namespaced")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-write-feeds", action="store_true")
    args = parser.parse_args()

    generated_at = utc_now()
    staged_rows = extract_events(json.loads(STAGED_PATH.read_text(encoding="utf-8")))
    supplemental_rows = extract_events(json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8")))

    reset_stable_id_registry()
    staged_events = [
        project_event(row, index=i, data_layer="approved_staged", production_feed=True)
        for i, row in enumerate(staged_rows)
    ]
    reset_stable_id_registry()
    supplemental_events = [
        project_event(row, index=i, data_layer="review_supplemental", production_feed=False)
        for i, row in enumerate(supplemental_rows)
    ]

    staged_env = envelope(staged_events, generated_at_utc=generated_at, next_cursor=None)
    supp_env = envelope(supplemental_events, generated_at_utc=generated_at, next_cursor=None)

    errors: list[str] = []
    staged_ids = [e["id"] for e in staged_events]
    supp_ids = [e["id"] for e in supplemental_events]
    if len(staged_ids) != len(set(staged_ids)):
        errors.append("duplicate approved ids")
    if len(supp_ids) != len(set(supp_ids)):
        errors.append("duplicate supplemental ids")
    if set(staged_ids) & set(supp_ids):
        errors.append("approved/supplemental id collision")
    if len(staged_events) != len(staged_rows):
        errors.append("approved count mismatch")
    if len(supplemental_events) != len(supplemental_rows):
        errors.append("supplemental count mismatch")

    for i, event in enumerate(staged_events[:100] + staged_events[-50:]):
        validate_event(event, errors, f"staged[{i}]")
    for i, event in enumerate(supplemental_events):
        validate_event(event, errors, f"supplemental[{i}]")

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "qa_pass": len(errors) == 0,
        "error_count": len(errors),
        "errors_sample": errors[:40],
        "staged": {
            "input_path": "data/nycif_staged_live_events.json",
            "output_path": "data/events_schema_v1_staged.json",
            "input_count": len(staged_rows),
            "output_total": staged_env["total"],
            "map_ready_count": sum(
                1 for e in staged_events if e["nycif"]["coordinate_status"] == "map_ready"
            ),
            "sample_event": staged_events[0] if staged_events else None,
        },
        "supplemental_review": {
            "input_path": "data/supplemental_events_staging_feed.json",
            "output_path": "data/events_schema_v1_supplemental_review.json",
            "input_count": len(supplemental_rows),
            "output_total": supp_env["total"],
            "map_ready_count": sum(
                1 for e in supplemental_events if e["nycif"]["coordinate_status"] == "map_ready"
            ),
            "list_only_count": sum(
                1 for e in supplemental_events if e["nycif"]["coordinate_status"] == "list_only"
            ),
            "promotion_allowed_any": any(e["nycif"]["promotion_allowed"] for e in supplemental_events),
            "production_feed_any": any(e["nycif"]["production_feed"] for e in supplemental_events),
            "sample_event": supplemental_events[0] if supplemental_events else None,
        },
        "safety": {
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "protected_files_rewritten": False,
            "promotion_allowed": False,
        },
    }

    if not args.skip_write_feeds:
        write_json(OUT_STAGED, staged_env)
        write_json(OUT_SUPP, supp_env)
    write_json(OUT_REPORT, report)
    print(json.dumps({"qa_pass": report["qa_pass"], "report": str(OUT_REPORT)}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
