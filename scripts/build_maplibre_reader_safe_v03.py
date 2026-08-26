#!/usr/bin/env python3
"""Build the reader-safe MapLibre event source from canonical Projector V3 output.

The reader-safe artifact serves two reader needs from one authority:
- exact MAP_READY markers, with Point geometry only when Projector V3 certifies them;
- current-window standalone public events whose exact geometry is withheld, represented
  with ``geometry: null`` so the Event List can still show the event without inventing
  a pin.

This module is projection-only. It does not geocode, repair, move, or infer pins.
Reader links are pass-through only: an already-public HTTP(S) event URL may be
projected as ``public_url``; backend/source-gathering URLs are never constructed.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    from scripts.discovery_v02 import extract_rows, write_json
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows, write_json
    from nyc_location_resolver import coordinate_matches_borough
    from occurrence_identity_contract import occurrence_key_v2

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
OUT_GEOJSON = "data/reader-safe/national-map-events-v03.geojson"
OUT_STATUS = "data/reader-safe/national-map-events-v03-status.json"
KNOWN_BOROUGHS = {"manhattan", "brooklyn", "bronx", "queens", "staten island"}
NYC_TZ = ZoneInfo("America/New_York")
READER_WINDOW_DAYS = 7
READER_VISIBLE_DISPOSITIONS = {"standalone_public_event", "list_only"}
PUBLIC_URL_FIELDS = ("public_url", "permalink", "link", "website", "url")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def safe_public_url(event: dict[str, Any]) -> str | None:
    """Return an already-public HTTP(S) event URL, without constructing one."""
    for field in PUBLIC_URL_FIELDS:
        value = event.get(field)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if re.match(r"^https?://", value, flags=re.IGNORECASE):
            return value
    return None


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


def reader_visible_event(event: dict[str, Any]) -> bool:
    """Return true only for standalone reader-facing public occurrences."""
    if event.get("event_role") != "public_event":
        return False
    if event.get("parent_event_id") not in (None, ""):
        return False
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return str(nycif.get("display_disposition") or "") in READER_VISIBLE_DISPOSITIONS


def ymd(value: Any) -> date | None:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def event_in_reader_window(event: dict[str, Any], window_start: date, window_end: date) -> bool:
    start = ymd(event.get("start_date_time") or event.get("date"))
    end = ymd(event.get("end_date_time")) or start
    if start is None:
        return False
    if end is None or end < start:
        end = start
    return start <= window_end and end >= window_start


def source_parts(event: dict[str, Any]) -> tuple[Any, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return (
        source.get("dataset") or event.get("source_dataset"),
        source.get("source_event_id") or event.get("source_event_id"),
    )


def feature(event: dict[str, Any], *, exact_marker: bool) -> dict[str, Any]:
    source_dataset, source_event_id = source_parts(event)
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    occurrence = occurrence_key_v2(event)
    geometry = None
    if exact_marker:
        geometry = {
            "type": "Point",
            "coordinates": [float(event["longitude"]), float(event["latitude"])],
        }
    return {
        "type": "Feature",
        "geometry": geometry,
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
            "public_url": safe_public_url(event),
            "source_dataset": source_dataset,
            "source_event_id": source_event_id,
            "map_eligibility_state": nycif.get("map_eligibility_state") or "REVIEW_REQUIRED",
            "certified_pin": bool(nycif.get("certified_pin")) if exact_marker else False,
            "location_authority": "projector_v3_semantic_map_decision",
            "event_role": "public_event",
            "display_disposition": nycif.get("display_disposition"),
            "is_major": bool(nycif.get("is_major")),
            "photo_pick": bool(nycif.get("photo_pick")),
        },
    }


def build() -> tuple[dict[str, Any], dict[str, Any]]:
    generated_dt = datetime.now(timezone.utc)
    generated_at = generated_dt.isoformat().replace("+00:00", "Z")
    window_start = generated_dt.astimezone(NYC_TZ).date()
    window_end = window_start + timedelta(days=READER_WINDOW_DAYS)

    canonical = extract_rows(load(CANONICAL))
    state_counts: Counter[str] = Counter()
    exclusion_counts: Counter[str] = Counter()
    features: list[dict[str, Any]] = []
    occurrence_ids: list[tuple[str, str, str]] = []
    reader_occurrence_ids: list[tuple[str, str, str]] = []
    borough_contradictions = 0
    borough_unverified = 0
    wrong_authority = 0
    evidence_failures = 0
    unsupported_markers = 0
    list_only_feature_count = 0

    for event in canonical:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        state = str(nycif.get("map_eligibility_state") or "REVIEW_REQUIRED")
        if state not in {"MAP_READY", "GENERAL_AREA", "REVIEW_REQUIRED", "LIST_ONLY"}:
            state = "REVIEW_REQUIRED"
        state_counts[state] += 1

        eligible, reason = marker_eligibility(event)
        if eligible:
            lat = float(event["latitude"])
            lng = float(event["longitude"])
            borough = str(event.get("borough") or "").strip().lower()
            if borough in KNOWN_BOROUGHS:
                if not coordinate_matches_borough(lat, lng, borough):
                    borough_contradictions += 1
                    continue
            else:
                borough_unverified += 1
            occurrence = occurrence_key_v2(event)
            occurrence_ids.append(occurrence)
            reader_occurrence_ids.append(occurrence)
            features.append(feature(event, exact_marker=True))
            continue

        exclusion_counts[reason] += 1
        if state == "MAP_READY":
            unsupported_markers += 1
            if reason == "wrong_location_authority":
                wrong_authority += 1
            if reason == "location_evidence_not_validated":
                evidence_failures += 1

        if reader_visible_event(event) and event_in_reader_window(event, window_start, window_end):
            occurrence = occurrence_key_v2(event)
            reader_occurrence_ids.append(occurrence)
            features.append(feature(event, exact_marker=False))
            list_only_feature_count += 1

    duplicate_exact = len(occurrence_ids) - len(set(occurrence_ids))
    duplicate_reader = len(reader_occurrence_ids) - len(set(reader_occurrence_ids))
    status = {
        "schema_version": "nycif-national-map-events-v03-status",
        "generated_at_utc": generated_at,
        "authority": "projector_v3_semantic_map_decision",
        "canonical_event_count": len(canonical),
        "map_state_counts": {
            key: int(state_counts.get(key, 0))
            for key in ("MAP_READY", "GENERAL_AREA", "REVIEW_REQUIRED", "LIST_ONLY")
        },
        "exact_marker_count": len(occurrence_ids),
        "reader_safe_event_count": len(features),
        "reader_safe_non_marker_count": list_only_feature_count,
        "reader_window_start": window_start.isoformat(),
        "reader_window_end": window_end.isoformat(),
        "excluded_marker_candidates": dict(sorted(exclusion_counts.items())),
        "unsupported_marker_count": unsupported_markers,
        "wrong_authority_marker_count": wrong_authority,
        "location_evidence_failure_count": evidence_failures,
        "borough_contradiction_count": borough_contradictions,
        "borough_unverified_count": borough_unverified,
        "duplicate_exact_occurrence_count": duplicate_exact,
        "duplicate_reader_occurrence_count": duplicate_reader,
        "general_area_exact_geometry_count": 0,
        "qa_pass": (
            unsupported_markers == 0
            and wrong_authority == 0
            and evidence_failures == 0
            and borough_contradictions == 0
            and duplicate_exact == 0
            and duplicate_reader == 0
        ),
    }
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": "nycif-national-map-events-v03",
            "generated_at_utc": generated_at,
            "authority": "projector_v3_semantic_map_decision",
            "exact_points_only": False,
            "general_area_as_exact_points": False,
            "non_marker_geometry": None,
            "reader_window_start": window_start.isoformat(),
            "reader_window_end": window_end.isoformat(),
            "exact_marker_count": len(occurrence_ids),
            "reader_safe_event_count": len(features),
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
