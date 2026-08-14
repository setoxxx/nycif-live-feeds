#!/usr/bin/env python3
"""Deterministically migrate trusted legacy location matches into V3 evidence.

This is deliberately narrow. It does not geocode and does not certify a point
merely because coordinates exist. A legacy match is promotable only when the
current official row, matched record, geometry, borough, and location text agree.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.pin_integrity import certify_nyc_pin
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_location_resolver import coordinate_matches_borough
    from pin_integrity import certify_nyc_pin

MIGRATED_TIER = "verified_legacy_location_match"
TRUSTED_LEGACY_SOURCES = {
    "existing_enriched_feed_gps",
    "latest_test_feed_gps",
}
TRUSTED_MATCH_TYPES = {
    "event_id",
    "location_cache",
    "cemsid",
    "text_date_location",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _match_coords(match: dict[str, Any]) -> tuple[float | None, float | None, bool, str]:
    lat = match.get("lat", match.get("latitude"))
    lng = match.get("lng", match.get("longitude"))
    return certify_nyc_pin(lat, lng)


def _raw_location(raw: dict[str, Any]) -> str:
    return _text(raw.get("event_location") or raw.get("location"))


def _match_location(match: dict[str, Any]) -> str:
    return _text(match.get("display_location") or match.get("location") or match.get("event_location"))


def _raw_borough(raw: dict[str, Any]) -> str:
    return _text(raw.get("event_borough") or raw.get("borough"))


def _match_borough(match: dict[str, Any]) -> str:
    return _text(match.get("borough") or match.get("event_borough"))


def _same_location(raw: dict[str, Any], match: dict[str, Any]) -> bool:
    left = normalize_text_legacy(_raw_location(raw))
    right = normalize_text_legacy(_match_location(match))
    return bool(left and right and left == right)


def _same_borough(raw: dict[str, Any], match: dict[str, Any]) -> bool:
    raw_borough = normalize_text_legacy(_raw_borough(raw))
    match_borough = normalize_text_legacy(_match_borough(match))
    return bool(raw_borough and match_borough and raw_borough == match_borough)


def _same_event_id(raw: dict[str, Any], match: dict[str, Any]) -> bool:
    raw_id = _text(raw.get("event_id") or raw.get("source_event_id"))
    match_id = _text(match.get("source_event_id") or match.get("event_id"))
    return bool(raw_id and match_id and raw_id == match_id)


def migration_decision(
    raw: dict[str, Any], match_type: str, match: dict[str, Any] | None
) -> dict[str, Any]:
    """Return a deterministic migration decision without mutating inputs."""
    if match_type not in TRUSTED_MATCH_TYPES or not isinstance(match, dict):
        return {"eligible": False, "reason_code": "MATCH_CLASS_NOT_MIGRATABLE"}

    lat, lng, geometry_ok, geometry_reason = _match_coords(match)
    if not geometry_ok or lat is None or lng is None:
        return {"eligible": False, "reason_code": geometry_reason}

    borough = _raw_borough(raw)
    if not borough or not coordinate_matches_borough(lat, lng, borough):
        return {"eligible": False, "reason_code": "CURRENT_BOROUGH_COORDINATE_MISMATCH"}

    if not _same_location(raw, match):
        return {"eligible": False, "reason_code": "CURRENT_LOCATION_TEXT_MISMATCH"}

    if match_type == "event_id" and not _same_event_id(raw, match):
        return {"eligible": False, "reason_code": "SOURCE_EVENT_ID_MISMATCH"}

    source = _text(match.get("source") or match.get("location_source"))
    if source and source not in TRUSTED_LEGACY_SOURCES and match_type == "location_cache":
        return {"eligible": False, "reason_code": "LEGACY_PROVENANCE_NOT_ALLOWLISTED"}

    return {
        "eligible": True,
        "reason_code": "LEGACY_LOCATION_REVALIDATED",
        "latitude": lat,
        "longitude": lng,
        "source_provenance": source or f"legacy:{match_type}",
    }


def migrate_match(
    raw: dict[str, Any], match_type: str, match: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return a copied match carrying explicit evidence when revalidation passes."""
    decision = migration_decision(raw, match_type, match)
    if not isinstance(match, dict) or not decision.get("eligible"):
        return match, decision

    migrated = deepcopy(match)
    migrated["lat"] = decision["latitude"]
    migrated["lng"] = decision["longitude"]
    migrated["location_evidence"] = {
        "tier": MIGRATED_TIER,
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": decision["source_provenance"],
        "provider": "NYCIF deterministic legacy-location migration",
        "reason_code": "LEGACY_LOCATION_REVALIDATED",
        "reason_detail": (
            "Current official event identity/location and borough-safe geometry "
            "agree with the existing resolved location candidate."
        ),
    }
    return migrated, decision
