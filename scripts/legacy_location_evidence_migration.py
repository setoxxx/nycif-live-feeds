#!/usr/bin/env python3
"""Deterministically migrate trusted legacy location matches into V3 evidence.

This is deliberately narrow. It does not geocode and does not certify a point
merely because coordinates exist. A legacy match is promotable only when the
current official row, matched record, geometry, borough, and location text agree,
and the current location claim maps to an already-recognized exact evidence tier.

Street-segment claims are intentionally excluded from legacy-coordinate
migration. Those rows were a known wrong-pin class in the legacy map and must be
re-resolved by the canonical street-segment resolver before exact publication.
"""
from __future__ import annotations

import re
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


def _evidence_tier(raw: dict[str, Any]) -> str | None:
    """Map a current official location claim into an existing V3 exact tier."""
    location = _raw_location(raw)
    cemsids = [value for value in _split_ids(raw.get("cemsid") or raw.get("source_cemsid")) if value != "0"]

    if cemsids:
        return "certified_facility"
    if re.match(r"^\d+[a-z-]*\s+\S", location.strip(), flags=re.IGNORECASE):
        return "exact_address"
    if re.search(r"\s(?:at|@|&)\s", location, flags=re.IGNORECASE):
        return "exact_intersection"
    return None


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
    if match_type == "location_cache" and source not in TRUSTED_LEGACY_SOURCES:
        return {"eligible": False, "reason_code": "LEGACY_PROVENANCE_NOT_ALLOWLISTED"}

    # Known legacy wrong-pin class. Text/borough agreement is not proof that the
    # old coordinate lies on the claimed blockface. Require the canonical
    # Geoclient/segment resolver to rebuild evidence from current street claims.
    if _is_street_segment_claim(raw):
        return {
            "eligible": False,
            "reason_code": "STREET_SEGMENT_REQUIRES_CANONICAL_RERESOLUTION",
        }

    tier = _evidence_tier(raw)
    if tier is None:
        return {"eligible": False, "reason_code": "CURRENT_LOCATION_CLAIM_NOT_EXACT_TIER"}

    return {
        "eligible": True,
        "reason_code": "LEGACY_LOCATION_REVALIDATED",
        "latitude": lat,
        "longitude": lng,
        "tier": tier,
        "source_provenance": source or "exact_source_event_id_location_match",
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
        "tier": decision["tier"],
        "validation_state": "validated",
        "exact_pin_eligible": True,
        "source_provenance": decision["source_provenance"],
        "provider": "NYCIF deterministic legacy-location migration",
        "reason_code": "LEGACY_LOCATION_REVALIDATED",
        "reason_detail": (
            "Current official location claim, matched location text and borough-safe "
            "geometry agree; migrated into an existing V3 exact evidence tier."
        ),
    }
    return migrated, decision
