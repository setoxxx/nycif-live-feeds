#!/usr/bin/env python3
"""Normalize location-resolution evidence without inventing exact-pin authority.

Coordinates are data, not publication authority.  This adapter carries explicit
resolver evidence forward into the enrichment/staging/projector pipeline.  A
legacy/cache/enriched match that contains coordinates but no explicit evidence
is preserved as unvalidated review material and can never become an exact pin
by inference.
"""
from __future__ import annotations

from typing import Any

SAFE_EVIDENCE_KEYS = (
    "tier",
    "location_tier",
    "validation_state",
    "exact_pin_eligible",
    "source_provenance",
    "geocoder_provenance",
    "source",
    "provider",
    "geocoder_source",
    "geocoder_confidence",
    "confidence_reason",
    "reason_code",
    "reason_detail",
)


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _nested_evidence(match: dict[str, Any]) -> dict[str, Any] | None:
    direct = match.get("location_evidence")
    if isinstance(direct, dict):
        return direct
    nycif = match.get("nycif")
    if isinstance(nycif, dict) and isinstance(nycif.get("location_evidence"), dict):
        return nycif["location_evidence"]
    return None


def normalize_location_evidence(match_type: str, match: dict[str, Any] | None) -> dict[str, Any]:
    """Return a fail-closed evidence object for a matched location candidate."""
    match_type = _text(match_type) or "none"
    match = match if isinstance(match, dict) else {}

    nested = _nested_evidence(match)
    if nested is not None:
        source = nested
        tier = _text(source.get("tier") or source.get("location_tier")) or "legacy_match"
        validation_state = _text(source.get("validation_state")) or "unvalidated"
        explicit = source.get("exact_pin_eligible") is True
        provenance = _text(
            source.get("source_provenance")
            or source.get("geocoder_provenance")
            or source.get("source")
            or source.get("provider")
            or source.get("geocoder_source")
        ) or match_type
        evidence = {
            "tier": tier,
            "validation_state": validation_state,
            "exact_pin_eligible": explicit,
            "source_provenance": provenance,
        }
        for key in (
            "geocoder_source",
            "geocoder_confidence",
            "confidence_reason",
            "reason_code",
            "reason_detail",
        ):
            value = source.get(key)
            if value not in (None, ""):
                evidence[key] = value
        return evidence

    resolver_tier = _text(match.get("resolver_tier"))
    if resolver_tier:
        validation_state = _text(match.get("validation_state")) or "unvalidated"
        provenance = _text(match.get("geocoder_source")) or f"nyc_location_resolver:{resolver_tier}"
        evidence = {
            "tier": resolver_tier,
            "validation_state": validation_state,
            "exact_pin_eligible": match.get("exact_pin_eligible") is True,
            "source_provenance": provenance,
        }
        for key in (
            "geocoder_source",
            "geocoder_confidence",
            "confidence_reason",
            "reason_code",
            "reason_detail",
        ):
            value = match.get(key)
            if value not in (None, ""):
                evidence[key] = value
        return evidence

    # Legacy/cache/enriched matches remain usable as location candidates, but
    # no exact publication claim may be inferred from coordinate presence or
    # match strength alone.
    return {
        "tier": "unresolved" if match_type == "none" else "legacy_match",
        "validation_state": "unvalidated",
        "exact_pin_eligible": False,
        "source_provenance": match_type,
        "reason_code": "NO_EXPLICIT_EXACT_LOCATION_EVIDENCE",
    }


def safe_location_evidence_copy(value: Any) -> dict[str, Any]:
    """Copy only evidence fields that participate in the public authority contract."""
    if not isinstance(value, dict):
        return normalize_location_evidence("none", None)
    copied = {key: value[key] for key in SAFE_EVIDENCE_KEYS if key in value}
    return normalize_location_evidence("carried_forward", {"location_evidence": copied})
