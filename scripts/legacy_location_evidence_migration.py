#!/usr/bin/env python3
"""Classify trusted legacy location matches for V3 evidence recovery.

This module deliberately separates *candidate evidence* from *publication-ready
evidence*. A legacy/cache coordinate can be useful for deciding what to
re-resolve, but it is not certified merely because current location text,
borough, and an old point agree.

Street-segment claims are excluded from legacy-coordinate reuse entirely because
they are a known historical wrong-pin class. Facilities, addresses, and
intersections may enter a deterministic recovery queue, but they require their
own current-authority site validation before exact publication.
"""
from __future__ import annotations

import re
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_resolver import coordinate_matches_borough
    from scripts.pin_integrity import certify_nyc_pin
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_location_resolver import coordinate_matches_borough
    from pin_integrity import certify_nyc_pin

TRUSTED_LEGACY_SOURCES = {
    "existing_enriched_feed_gps",
    "latest_test_feed_gps",
}
TRUSTED_MATCH_TYPES = {
    "event_id",
    "location_cache",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return [part.strip() for part in _text(value).split(",") if part.strip()]


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


def _same_location(raw: dict[str, Any], match: dict[str, Any]) -> bool:
    left = normalize_text_legacy(_raw_location(raw))
    right = normalize_text_legacy(_match_location(match))
    return bool(left and right and left == right)


def _same_event_id(raw: dict[str, Any], match: dict[str, Any]) -> bool:
    raw_id = _text(raw.get("event_id") or raw.get("source_event_id"))
    match_id = _text(match.get("source_event_id") or match.get("event_id"))
    return bool(raw_id and match_id and raw_id == match_id)


def _is_street_segment_claim(raw: dict[str, Any]) -> bool:
    normalized = normalize_text_legacy(_raw_location(raw))
    return bool(re.search(r"\bbetween\b.+\band\b", normalized))


def _candidate_tier(raw: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Classify the current claim for independent re-resolution; do not certify it."""
    location = _raw_location(raw)
    cemsids = [value for value in _split_ids(raw.get("cemsid") or raw.get("source_cemsid")) if value != "0"]
    if cemsids:
        return "certified_facility", cemsids
    if re.match(r"^\d+[a-z-]*\s+\S", location.strip(), flags=re.IGNORECASE):
        return "exact_address", []
    if re.search(r"\s(?:at|@|&)\s", location, flags=re.IGNORECASE):
        return "exact_intersection", []
    return None, []


def _candidate_reason(tier: str) -> str:
    if tier == "certified_facility":
        return "FACILITY_SITE_VALIDATION_REQUIRED"
    if tier == "exact_address":
        return "ADDRESS_CANONICAL_RERESOLUTION_REQUIRED"
    if tier == "exact_intersection":
        return "INTERSECTION_CANONICAL_RERESOLUTION_REQUIRED"
    return "CURRENT_LOCATION_CLAIM_NOT_EXACT_TIER"


def migration_decision(
    raw: dict[str, Any], match_type: str, match: dict[str, Any] | None
) -> dict[str, Any]:
    """Return deterministic recovery classification without granting publication authority."""
    if match_type not in TRUSTED_MATCH_TYPES or not isinstance(match, dict):
        return {"eligible": False, "candidate": False, "reason_code": "MATCH_CLASS_NOT_MIGRATABLE"}

    lat, lng, geometry_ok, geometry_reason = _match_coords(match)
    if not geometry_ok or lat is None or lng is None:
        return {"eligible": False, "candidate": False, "reason_code": geometry_reason}

    borough = _raw_borough(raw)
    if not borough or not coordinate_matches_borough(lat, lng, borough):
        return {"eligible": False, "candidate": False, "reason_code": "CURRENT_BOROUGH_COORDINATE_MISMATCH"}

    if not _same_location(raw, match):
        return {"eligible": False, "candidate": False, "reason_code": "CURRENT_LOCATION_TEXT_MISMATCH"}

    if match_type == "event_id" and not _same_event_id(raw, match):
        return {"eligible": False, "candidate": False, "reason_code": "SOURCE_EVENT_ID_MISMATCH"}

    source = _text(match.get("source") or match.get("location_source"))
    if match_type == "location_cache" and source not in TRUSTED_LEGACY_SOURCES:
        return {"eligible": False, "candidate": False, "reason_code": "LEGACY_PROVENANCE_NOT_ALLOWLISTED"}

    if _is_street_segment_claim(raw):
        return {
            "eligible": False,
            "candidate": True,
            "candidate_tier": "certified_street_segment",
            "reason_code": "STREET_SEGMENT_REQUIRES_CANONICAL_RERESOLUTION",
            "latitude": lat,
            "longitude": lng,
            "source_provenance": source or "legacy_exact_event_id_location_match",
        }

    tier, facility_ids = _candidate_tier(raw)
    if tier is None:
        return {"eligible": False, "candidate": False, "reason_code": "CURRENT_LOCATION_CLAIM_NOT_EXACT_TIER"}

    result = {
        "eligible": False,
        "candidate": True,
        "candidate_tier": tier,
        "reason_code": _candidate_reason(tier),
        "latitude": lat,
        "longitude": lng,
        "source_provenance": source or "legacy_exact_event_id_location_match",
    }
    if facility_ids:
        result["facility_ids"] = facility_ids
    return result


def migrate_match(
    raw: dict[str, Any], match_type: str, match: dict[str, Any] | None
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return legacy match unchanged until an independent validator certifies the site.

    This function intentionally performs no evidence-envelope promotion. Its
    compatibility role is to let the semantic intake retain the original
    candidate while the decision object records the exact recovery lane.
    """
    decision = migration_decision(raw, match_type, match)
    return match, decision
