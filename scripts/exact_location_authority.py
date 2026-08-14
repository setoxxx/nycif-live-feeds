#!/usr/bin/env python3
"""Final exact-site evidence gate for public event geometry.

This module is intentionally stricter than coordinate validity. A point may be
inside NYC and still be wrong for the event. Public exact pins must prove that
the coordinate represents the event's actual stated site, not a nearby street,
park centroid, neighborhood center, municipality anchor, or legacy guess.
"""
from __future__ import annotations

from typing import Any

CANONICAL_EXACT_TIERS = frozenset(
    {
        "exact_source_coordinate",
        "exact_address",
        "exact_intersection",
        "certified_street_segment",
        "certified_facility",
    }
)

PROHIBITED_LEGACY_TIERS = frozenset(
    {
        "tier_1_certified_segment",
        "tier_2_geosearch_midpoint",
    }
)

PROHIBITED_REASON_CODES = frozenset(
    {
        "LEGACY_LOCATION_REVALIDATED",
        "GENERIC_FALLBACK",
        "APPROXIMATE_AREA",
    }
)

PROHIBITED_PROVENANCE_TOKENS = (
    "generic_fallback",
    "neighborhood_centroid",
    "municipality_centroid",
    "park_level_anchor",
    "parks_properties_centroid",
    "parent_park_fallback",
    "planninglabs_midpoint",
)

SOURCE_COORDINATE_SITE_VALIDATED_REASONS = frozenset(
    {
        "OFFICIAL_SOURCE_COORDINATE_SITE_VALIDATED",
        "SOURCE_COORDINATE_SITE_VALIDATED",
    }
)

ADDRESS_VALIDATED_REASONS = frozenset(
    {
        "ADDRESS_GEOCLIENT_VALIDATED",
        "ADDRESS_SOURCE_EXACT_VALIDATED",
    }
)

INTERSECTION_VALIDATED_REASONS = frozenset(
    {
        "INTERSECTION_GEOCLIENT_VALIDATED",
        "INTERSECTION_SOURCE_EXACT_VALIDATED",
    }
)

SEGMENT_VALIDATED_REASONS = frozenset(
    {
        "SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED",
        "SEGMENT_CERTIFIED_REFERENCE",
    }
)

FACILITY_VALIDATED_REASONS = frozenset(
    {
        "FACILITY_REGISTRY_CONTAINMENT_VALIDATED",
        "FACILITY_SOURCE_EXACT_VALIDATED",
    }
)


def _evidence(event: dict[str, Any]) -> dict[str, Any]:
    direct = event.get("location_evidence")
    if isinstance(direct, dict):
        return direct
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    nested = nycif.get("location_evidence")
    return nested if isinstance(nested, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _provenance(evidence: dict[str, Any]) -> str:
    return _text(
        evidence.get("source_provenance")
        or evidence.get("geocoder_provenance")
        or evidence.get("geocoder_source")
        or evidence.get("source")
        or evidence.get("provider")
    )


def exact_site_assessment(event: dict[str, Any]) -> dict[str, Any]:
    """Return whether evidence is strong enough for an exact public pin.

    This is a publication gate, not a geocoder. False means retain the event but
    do not expose exact point geometry until canonical re-resolution completes.
    """
    evidence = _evidence(event)
    if not evidence:
        return {"eligible": False, "reason_code": "EXACT_SITE_EVIDENCE_MISSING"}

    tier = _text(evidence.get("tier") or evidence.get("location_tier")).lower()
    validation_state = _text(evidence.get("validation_state")).lower()
    explicit = evidence.get("exact_pin_eligible") is True
    reason_code = _text(evidence.get("reason_code"))
    provenance = _provenance(evidence)
    provenance_norm = provenance.lower().replace(" ", "_")

    if tier in PROHIBITED_LEGACY_TIERS:
        return {"eligible": False, "reason_code": "LEGACY_EXACT_TIER_PROHIBITED"}
    if tier not in CANONICAL_EXACT_TIERS:
        return {"eligible": False, "reason_code": "NON_EXACT_LOCATION_TIER"}
    if validation_state != "validated" or not explicit:
        return {"eligible": False, "reason_code": "EXACT_SITE_NOT_VALIDATED"}
    if not provenance:
        return {"eligible": False, "reason_code": "EXACT_SITE_PROVENANCE_MISSING"}
    if reason_code in PROHIBITED_REASON_CODES:
        return {"eligible": False, "reason_code": "EXACT_SITE_LEGACY_OR_APPROXIMATE_EVIDENCE"}
    if any(token in provenance_norm for token in PROHIBITED_PROVENANCE_TOKENS):
        return {"eligible": False, "reason_code": "EXACT_SITE_APPROXIMATE_PROVENANCE"}

    site_validation_state = _text(evidence.get("site_validation_state")).lower()

    if tier == "exact_source_coordinate":
        if reason_code not in SOURCE_COORDINATE_SITE_VALIDATED_REASONS and site_validation_state != "validated":
            return {"eligible": False, "reason_code": "SOURCE_COORDINATE_SITE_UNVERIFIED"}
    elif tier == "exact_address":
        if reason_code not in ADDRESS_VALIDATED_REASONS and site_validation_state != "validated":
            return {"eligible": False, "reason_code": "ADDRESS_SITE_UNVERIFIED"}
    elif tier == "exact_intersection":
        if reason_code not in INTERSECTION_VALIDATED_REASONS and site_validation_state != "validated":
            return {"eligible": False, "reason_code": "INTERSECTION_SITE_UNVERIFIED"}
    elif tier == "certified_street_segment":
        if reason_code not in SEGMENT_VALIDATED_REASONS:
            return {"eligible": False, "reason_code": "STREET_SEGMENT_SITE_UNVERIFIED"}
    elif tier == "certified_facility":
        facility_id = _text(
            evidence.get("facility_id")
            or evidence.get("park_id")
            or evidence.get("venue_id")
            or event.get("facility_id")
            or event.get("park_id")
            or event.get("venue_id")
        )
        if not facility_id:
            return {"eligible": False, "reason_code": "FACILITY_ID_REQUIRED_FOR_EXACT_SITE"}
        if reason_code not in FACILITY_VALIDATED_REASONS and site_validation_state != "validated":
            return {"eligible": False, "reason_code": "FACILITY_SITE_UNVERIFIED"}

    return {
        "eligible": True,
        "reason_code": "EXACT_EVENT_SITE_VALIDATED",
        "tier": tier,
        "provenance": provenance,
    }


def enforce_exact_site_on_map_decision(
    event: dict[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    """Fail closed when a lower-level MAP_READY decision lacks exact-site proof."""
    out = dict(decision)
    semantic_exact = (
        out.get("map_eligibility_state") == "MAP_READY"
        and out.get("certified_pin") is True
        and out.get("latitude") is not None
        and out.get("longitude") is not None
    )
    if not semantic_exact:
        return out

    assessment = exact_site_assessment(event)
    out["exact_site_assessment"] = assessment
    if assessment.get("eligible") is True:
        out["exact_site_validated"] = True
        return out

    out["map_eligibility_state"] = "REVIEW_REQUIRED"
    out["exact_pin_eligible"] = False
    out["latitude"] = None
    out["longitude"] = None
    out["coordinate_status"] = "list_only"
    out["certified_pin"] = False
    out["reason_code"] = assessment.get("reason_code")
    out["exact_site_validated"] = False
    return out
