#!/usr/bin/env python3
"""Project staged + supplemental feeds into schema_version 1.0 envelopes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from enigma.shadow2.location_evidence import classify_location_evidence  # noqa: E402
from nycif.normalize.facility_resolver import resolve_facility_anchor  # noqa: E402
from nycif.normalize.park_geometry import load_park_lookup  # noqa: E402
from schema_v1_common import (  # noqa: E402
    SCHEMA_VERSION,
    envelope,
    extract_events,
    project_event,
    reset_stable_id_registry,
    write_repo_json,
    utc_now,
)

STAGED_PATH = ROOT / "data" / "nycif_staged_live_events.json"
SUPPLEMENTAL_PATH = ROOT / "data" / "supplemental_events_staging_feed.json"
OUT_STAGED = ROOT / "data" / "events_schema_v1_staged.json"
OUT_SUPP = ROOT / "data" / "events_schema_v1_supplemental_review.json"
OUT_REPORT = ROOT / "data" / "events_schema_v1_validation_report.json"
REQUIRED_EVENT_FIELDS = [
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


def validate_required_fields(event: dict, errors: list[str], prefix: str) -> None:
    for key in REQUIRED_EVENT_FIELDS:
        if key not in event:
            errors.append(f"{prefix}: missing field {key}")


def validate_source_block(event: dict, errors: list[str], prefix: str) -> None:
    source = event.get("source")
    if not isinstance(source, dict) or "dataset" not in source or "source_event_id" not in source:
        errors.append(f"{prefix}: source must include dataset and source_event_id")


def validate_coordinates(event: dict, errors: list[str], prefix: str) -> None:
    lat, lng = event.get("latitude"), event.get("longitude")
    if (lat is None) != (lng is None):
        errors.append(f"{prefix}: latitude/longitude must both be set or both null")
    if "lat" in event or "lng" in event:
        errors.append(f"{prefix}: legacy lat/lng leaked")


def validate_supplemental_checks(event: dict, errors: list[str], prefix: str) -> None:
    nycif = event.get("nycif") or {}
    if nycif.get("data_layer") != "review_supplemental":
        return
    if nycif.get("promotion_allowed") is True:
        errors.append(f"{prefix}: supplemental promotion_allowed true")
    if nycif.get("production_feed") is True:
        errors.append(f"{prefix}: supplemental production_feed true")
    if not str(event.get("id", "")).startswith("review_supplemental:"):
        errors.append(f"{prefix}: supplemental id not namespaced")
    if nycif.get("coordinate_status") == "approximate":
        if nycif.get("display_disposition") != "approximate_marker":
            errors.append(f"{prefix}: approximate anchor lacks approximate_marker disposition")
        if nycif.get("coordinate_precision") != "park_level_anchor":
            errors.append(f"{prefix}: approximate anchor lacks park_level_anchor precision")
        if nycif.get("coordinate_source") != "dpr_parks_properties_centroid":
            errors.append(f"{prefix}: approximate anchor has unexpected coordinate source")
        if event.get("latitude") is None or event.get("longitude") is None:
            errors.append(f"{prefix}: approximate anchor lacks coordinate pair")


def validate_event(event: dict, errors: list[str], prefix: str) -> None:
    validate_required_fields(event, errors, prefix)
    validate_source_block(event, errors, prefix)
    validate_coordinates(event, errors, prefix)
    validate_supplemental_checks(event, errors, prefix)


def apply_supplemental_park_anchor(
    projected: dict[str, Any],
    source_row: dict[str, Any],
    *,
    park_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Apply one reviewed DPR centroid contract without granting map-ready status."""
    nycif = projected.get("nycif") if isinstance(projected.get("nycif"), dict) else {}
    if nycif.get("data_layer") != "review_supplemental":
        return projected
    if nycif.get("coordinate_status") != "list_only":
        return projected
    try:
        tier = classify_location_evidence(projected).tier.value
    except Exception:
        return projected
    if tier != "unresolved":
        return projected

    probe = dict(source_row)
    probe["evidence_tier"] = "unresolved"
    probe["location"] = projected.get("location") or source_row.get("location")
    probe["borough"] = projected.get("borough") or source_row.get("borough")
    resolved = resolve_facility_anchor(probe, lookup=park_lookup)
    if not resolved:
        return projected

    projected["latitude"] = resolved["latitude"]
    projected["longitude"] = resolved["longitude"]
    nycif = dict(nycif)
    nycif.update(
        {
            "coordinate_status": "approximate",
            "display_disposition": "approximate_marker",
            "coordinate_precision": "park_level_anchor",
            "coordinate_source": "dpr_parks_properties_centroid",
            "park_id": resolved.get("park_id"),
            "park_name": resolved.get("park_name"),
            "park_borough": resolved.get("park_borough"),
            "park_match_type": resolved.get("park_match_type"),
            "park_query_name": resolved.get("park_query_name"),
            "promotion_allowed": False,
            "production_feed": False,
            "public_map_modified": False,
        }
    )
    projected["nycif"] = nycif
    return projected


def project_layer(
    rows: list[dict],
    *,
    data_layer: str,
    park_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[dict]:
    reset_stable_id_registry()
    projected_events: list[dict] = []
    lookup = park_lookup or {}
    for index, row in enumerate(rows):
        projected = project_event(row, index=index, data_layer=data_layer)
        if data_layer == "review_supplemental" and lookup:
            projected = apply_supplemental_park_anchor(
                projected,
                row,
                park_lookup=lookup,
            )
        projected_events.append(projected)
    return projected_events


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-write-feeds", action="store_true")
    args = parser.parse_args()

    generated_at = utc_now()
    staged_rows = extract_events(json.loads(STAGED_PATH.read_text(encoding="utf-8")))
    supplemental_rows = extract_events(json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8")))
    park_lookup = load_park_lookup()

    staged_events = project_layer(staged_rows, data_layer="approved_staged")
    supplemental_events = project_layer(
        supplemental_rows,
        data_layer="review_supplemental",
        park_lookup=park_lookup,
    )
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

    sample = staged_events[:100] + staged_events[-50:]
    for i, event in enumerate(sample):
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
            "park_lookup_aliases": len(park_lookup),
            "map_ready_count": sum(
                1 for e in supplemental_events if e["nycif"]["coordinate_status"] == "map_ready"
            ),
            "approximate_count": sum(
                1 for e in supplemental_events if e["nycif"]["coordinate_status"] == "approximate"
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
        write_repo_json("data/events_schema_v1_staged.json", staged_env)
        write_repo_json("data/events_schema_v1_supplemental_review.json", supp_env)
    write_repo_json("data/events_schema_v1_validation_report.json", report)
    print(json.dumps({"qa_pass": report["qa_pass"], "report": str(OUT_REPORT)}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
