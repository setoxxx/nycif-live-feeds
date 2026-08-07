#!/usr/bin/env python3
"""Build the reader-safe MapLibre event source from canonical Projector V3 output.

This module is intentionally a projection-only adapter. It does not geocode,
resolve, repair, move, or infer pins. A point feature can exist only when the
canonical event already carries shared semantic MAP_READY authority and is a
standalone public event. GENERAL_AREA / REVIEW_REQUIRED / LIST_ONLY records are
counted for audit but never emitted as exact point geometry.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows, utc_now, write_json
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows, utc_now, write_json
    from nyc_location_resolver import coordinate_matches_borough
    from occurrence_identity_contract import occurrence_key_v2

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
OUT_GEOJSON = "data/reader-safe/national-map-events-v03.geojson"
OUT_STATUS = "data/reader-safe/national-map-events-v03-status.json"
KNOWN_BOROUGHS = {"manhattan", "brooklyn", "bronx", "queens", "staten island"}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def evidence_validated(event: dict[str, Any]) -> bool:
    evidence = event.get("location_evidence")
    if not isinstance(evidence, dict):
        return False
    return (
        str(evidence.get("validation_state") or "").lower() == "validated"
        and evidence.get("exact_pin_eligible") is True
        and bool(
            evidence.get("source_provenance")
            or evidence.get("geocoder_provenance")
            or evidence.get("source")
            or evidence.get("provider")
            or evidence.get("geocoder_source")
        )
    )


def marker_eligibility(event: dict[str, Any]) -> tuple[bool, str]:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    if nycif.get("map_eligibility_state") != "MAP_READY":
        return False, "not_map_ready"
    if nycif.get("certified_pin") is not True:
        return False, "not_certified_pin"
    if nycif.get("location_authority") != "projector_v3_semantic_map_decision":
        return False, "wrong_location_authority"
    if not evidence_validated(event):
        return False, "location_evidence_not_validated"
    if event.get("event_role") != "public_event":
        return False, "not_public_event"
    if event.get("parent_event_id") not in (None, ""):
        return False, "suppressed_child"
    if nycif.get("display_disposition") != "standalone_public_event":
        return False, "not_standalone_public_event"
    lat = finite(event.get("latitude"))
    lng = finite(event.get("longitude"))
    if lat is None or lng is None:
        return False, "nonfinite_coordinates"
    return True, "marker_ready"


def feature(event: dict[str, Any]) -> dict[str, Any]:
    lat = float(event["latitude"])
    lng = float(event["longitude"])
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    occurrence = occurrence_key_v2(event)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": {
            "id": event.get("id"),
            "occurrence_id": "|".join(str(part) for part in occurrence),
            "title": event.get("title"),
            "category": event.get("category"),
            "borough": event.get("borough"),
            "neighborhood": event.get("neighborhood"),
            "location": event.get("location"),
            "start_date_time": event.get("start_date_time"),
            "end_date_time": event.get("end_date_time"),
            "timezone": event.get("timezone"),
            "significance": event.get("significance"),
            "source_dataset": source.get("dataset"),
            "source_event_id": source.get("source_event_id"),
            "map_eligibility_state": "MAP_READY",
            "certified_pin": True,
            "location_authority": "projector_v3_semantic_map_decision",
            "event_role": "public_event",
            "display_disposition": "standalone_public_event",
            "is_major": bool(nycif.get("is_major")),
            "photo_pick": bool(nycif.get("photo_pick")),
        },
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = utc_now()
    canonical = extract_rows(load(CANONICAL))
    state_counts: Counter[str] = Counter()
    exclusion_counts: Counter[str] = Counter()
    features: list[dict[str, Any]] = []
    occurrence_ids: list[tuple[str, str, str]] = []
    borough_contradictions = 0
    borough_unverified = 0
    wrong_authority = 0
    evidence_failures = 0
    unsupported_markers = 0

    for event in canonical:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        state = str(nycif.get("map_eligibility_state") or "REVIEW_REQUIRED")
        if state not in {"MAP_READY", "GENERAL_AREA", "REVIEW_REQUIRED", "LIST_ONLY"}:
            state = "REVIEW_REQUIRED"
        state_counts[state] += 1

        eligible, reason = marker_eligibility(event)
        if not eligible:
            exclusion_counts[reason] += 1
            if state == "MAP_READY":
                unsupported_markers += 1
                if reason == "wrong_location_authority":
                    wrong_authority += 1
                if reason == "location_evidence_not_validated":
                    evidence_failures += 1
            continue

        lat = float(event["latitude"])
        lng = float(event["longitude"])
        borough = str(event.get("borough") or "").strip().lower()
        if borough in KNOWN_BOROUGHS:
            if not coordinate_matches_borough(lat, lng, borough):
                borough_contradictions += 1
                continue
        else:
            borough_unverified += 1

        occurrence_ids.append(occurrence_key_v2(event))
        features.append(feature(event))

    duplicate_exact = len(occurrence_ids) - len(set(occurrence_ids))
    status = {
        "schema_version": "nycif-national-map-events-v03-status",
        "generated_at_utc": generated_at,
        "authority": "projector_v3_semantic_map_decision",
        "canonical_event_count": len(canonical),
        "map_state_counts": {
            key: int(state_counts.get(key, 0))
            for key in ("MAP_READY", "GENERAL_AREA", "REVIEW_REQUIRED", "LIST_ONLY")
        },
        "exact_marker_count": len(features),
        "excluded_marker_candidates": dict(sorted(exclusion_counts.items())),
        "unsupported_marker_count": unsupported_markers,
        "wrong_authority_marker_count": wrong_authority,
        "location_evidence_failure_count": evidence_failures,
        "borough_contradiction_count": borough_contradictions,
        "borough_unverified_count": borough_unverified,
        "duplicate_exact_occurrence_count": duplicate_exact,
        "general_area_exact_geometry_count": 0,
        "qa_pass": (
            unsupported_markers == 0
            and wrong_authority == 0
            and evidence_failures == 0
            and borough_contradictions == 0
            and duplicate_exact == 0
        ),
    }
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": "nycif-national-map-events-v03",
            "generated_at_utc": generated_at,
            "authority": "projector_v3_semantic_map_decision",
            "exact_points_only": True,
            "general_area_as_exact_points": False,
        },
        "features": features,
    }
    return geojson, status


def main() -> int:
    geojson, status = build()
    write_json(OUT_GEOJSON, geojson)
    write_json(OUT_STATUS, status)
    print(json.dumps(status, indent=2, sort_keys=True))
    if not status["qa_pass"]:
        raise RuntimeError(f"MapLibre canonical marker audit failed: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
