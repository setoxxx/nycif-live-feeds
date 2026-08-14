#!/usr/bin/env python3
"""NYC pin integrity and semantic map-eligibility authority.

Geometry validity is necessary but not sufficient for an exact public pin.
Bounds/null/swap checks remain the low-level geometry guard. Exact publication
eligibility is decided separately from evidence tier, validation state and
provenance under the Location Evidence Contract.
"""

from __future__ import annotations

import math
from typing import Any

from schema_v1_common import NYC, is_zero_coord_pair

# Stable reason codes for QA reports.
REASON_OK = "ok_nyc_geometry_valid"
REASON_OK_SWAP = "ok_nyc_geometry_valid_swap_corrected"
REASON_MISSING = "missing_coords"
REASON_NONFINITE = "nonfinite"
REASON_NULL_ISLAND = "null_island"
REASON_OOB = "oob_outside_nyc_box"
REASON_SWAP_SUSPECTED = "swap_suspected_demoted"
REASON_STATUS_WITHOUT_COORDS = "map_ready_without_coords"
REASON_PROPOSED_KEEP = "proposed_unverified_keep"
REASON_LEGACY_EVIDENCE = "LEGACY_EVIDENCE_PENDING_MIGRATION"
REASON_UNVALIDATED_EVIDENCE = "LOCATION_EVIDENCE_UNVALIDATED"
REASON_EXACT_ELIGIBLE = "LOCATION_EVIDENCE_VALIDATED"

EXACT_TIERS = {
    "exact_source_coordinate",
    "exact_address",
    "exact_intersection",
    "certified_street_segment",
    "certified_facility",
    # Temporary compatibility with pre-contract tier names emitted by the
    # resolver while callers migrate.
    "tier_1_certified_segment",
    "tier_2_geosearch_midpoint",
}

NYC_BOUNDS_DOC = {
    "min_lat": NYC["min_lat"],
    "max_lat": NYC["max_lat"],
    "min_lng": NYC["min_lng"],
    "max_lng": NYC["max_lng"],
    "label": "NYC metro envelope (schema_v1_common.NYC)",
}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def in_nyc_box(lat: float, lng: float) -> bool:
    return (
        NYC["min_lat"] <= lat <= NYC["max_lat"]
        and NYC["min_lng"] <= lng <= NYC["max_lng"]
    )


def certify_nyc_pin(
    lat: Any,
    lng: Any,
    *,
    allow_swap_correct: bool = True,
) -> tuple[float | None, float | None, bool, str]:
    """Return low-level geometry validity, not semantic location certification."""
    lat_f = _as_float(lat)
    lng_f = _as_float(lng)
    if lat_f is None and lng_f is None:
        return None, None, False, REASON_MISSING
    if lat_f is None or lng_f is None:
        return None, None, False, REASON_NONFINITE
    if is_zero_coord_pair(lat_f, lng_f):
        return None, None, False, REASON_NULL_ISLAND
    if in_nyc_box(lat_f, lng_f):
        return lat_f, lng_f, True, REASON_OK

    if allow_swap_correct and in_nyc_box(lng_f, lat_f):
        return lng_f, lat_f, True, REASON_OK_SWAP

    looks_swapped = (
        NYC["min_lat"] <= lng_f <= NYC["max_lat"]
        and NYC["min_lng"] <= lat_f <= NYC["max_lng"]
    )
    if looks_swapped:
        return None, None, False, REASON_SWAP_SUSPECTED
    return None, None, False, REASON_OOB


def _evidence_dict(event: dict[str, Any]) -> dict[str, Any]:
    evidence = event.get("location_evidence")
    if isinstance(evidence, dict):
        return evidence
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    nested = nycif.get("location_evidence")
    return nested if isinstance(nested, dict) else {}


def evaluate_map_eligibility(event: dict[str, Any]) -> dict[str, Any]:
    """Evaluate publication eligibility separately from geometry presence.

    Returns a fail-closed decision. Legacy records without evidence are not
    declared wrong; they are marked pending migration and cannot acquire a new
    `certified_pin=True` claim merely because coordinates fall inside NYC.
    """
    lat = event.get("latitude", event.get("lat"))
    lng = event.get("longitude", event.get("lng"))
    lat_f, lng_f, geometry_valid, geometry_reason = certify_nyc_pin(lat, lng)
    if not geometry_valid:
        return {
            "map_eligibility": "LIST_ONLY",
            "exact_pin_eligible": False,
            "geometry_valid": False,
            "reason_code": geometry_reason,
        }

    evidence = _evidence_dict(event)
    if not evidence:
        return {
            "map_eligibility": "REVIEW_REQUIRED",
            "exact_pin_eligible": False,
            "geometry_valid": True,
            "normalized_lat": lat_f,
            "normalized_lng": lng_f,
            "reason_code": REASON_LEGACY_EVIDENCE,
        }

    tier = str(evidence.get("tier") or evidence.get("location_tier") or "").strip().lower()
    validation_state = str(evidence.get("validation_state") or "unvalidated").strip().lower()
    explicit_eligible = evidence.get("exact_pin_eligible") is True
    provenance = (
        evidence.get("source_provenance")
        or evidence.get("geocoder_provenance")
        or evidence.get("source")
        or evidence.get("provider")
    )

    if tier == "approximate_area":
        return {
            "map_eligibility": "GENERAL_AREA",
            "exact_pin_eligible": False,
            "geometry_valid": True,
            "reason_code": "APPROXIMATE_AREA",
        }
    if tier in {"unresolved", ""}:
        return {
            "map_eligibility": "LIST_ONLY" if tier == "unresolved" else "REVIEW_REQUIRED",
            "exact_pin_eligible": False,
            "geometry_valid": True,
            "reason_code": "UNRESOLVED" if tier == "unresolved" else REASON_UNVALIDATED_EVIDENCE,
        }

    if (
        tier in EXACT_TIERS
        and validation_state == "validated"
        and explicit_eligible
        and bool(provenance)
    ):
        return {
            "map_eligibility": "MAP_READY",
            "exact_pin_eligible": True,
            "geometry_valid": True,
            "normalized_lat": lat_f,
            "normalized_lng": lng_f,
            "reason_code": REASON_EXACT_ELIGIBLE,
        }

    return {
        "map_eligibility": "REVIEW_REQUIRED",
        "exact_pin_eligible": False,
        "geometry_valid": True,
        "reason_code": REASON_UNVALIDATED_EVIDENCE,
    }


def _set_pin_coords(event: dict[str, Any], lat_f: float | None, lng_f: float | None) -> None:
    event["latitude"] = lat_f
    event["longitude"] = lng_f
    if "lat" in event:
        event["lat"] = lat_f
    if "lng" in event:
        event["lng"] = lng_f


def _demote_event(event: dict[str, Any], reason: str) -> None:
    _set_pin_coords(event, None, None)
    event["map_link"] = None
    event["coordinate_status"] = "list_only"
    event["map_eligibility_state"] = "LIST_ONLY"
    event["pin_integrity_reason"] = reason
    event["certified_pin"] = False


def _certify_proposed(
    event: dict[str, Any],
    before_lat: Any,
    before_lng: Any,
    *,
    allow_swap_correct: bool,
) -> dict[str, Any]:
    lat_f, lng_f, ok, reason = certify_nyc_pin(before_lat, before_lng, allow_swap_correct=allow_swap_correct)
    if ok:
        _set_pin_coords(event, lat_f, lng_f)
        event["pin_integrity_reason"] = reason
        event["certified_pin"] = False
        event["map_eligibility_state"] = "REVIEW_REQUIRED"
        return {"changed": False, "reason": REASON_PROPOSED_KEEP, "status": "proposed"}
    _demote_event(event, reason)
    return {
        "changed": True,
        "reason": reason,
        "before_status": "proposed",
        "after_status": "list_only",
        "before_lat": before_lat,
        "before_lng": before_lng,
    }


def _missing_claimed_coords(before_status: str, before_lat: Any, before_lng: Any) -> bool:
    if before_status != "map_ready":
        return False
    return before_lat in (None, "") or before_lng in (None, "")


def certify_event_pin(event: dict[str, Any], *, allow_swap_correct: bool = True) -> dict[str, Any]:
    """Apply geometry guard plus semantic eligibility without inventing evidence."""
    before_status = str(event.get("coordinate_status") or "")
    before_lat = event.get("latitude", event.get("lat"))
    before_lng = event.get("longitude", event.get("lng"))

    if before_status == "proposed":
        return _certify_proposed(event, before_lat, before_lng, allow_swap_correct=allow_swap_correct)

    lat_f, lng_f, geometry_ok, geometry_reason = certify_nyc_pin(
        before_lat, before_lng, allow_swap_correct=allow_swap_correct
    )
    if _missing_claimed_coords(before_status, before_lat, before_lng):
        geometry_ok = False
        geometry_reason = REASON_STATUS_WITHOUT_COORDS

    if not geometry_ok or lat_f is None or lng_f is None:
        _demote_event(event, geometry_reason)
        return {
            "changed": before_status == "map_ready" or before_lat not in (None, "") or before_lng not in (None, ""),
            "demoted": True,
            "reason": geometry_reason,
            "before_status": before_status or "missing",
            "after_status": "list_only",
            "before_lat": before_lat,
            "before_lng": before_lng,
        }

    _set_pin_coords(event, lat_f, lng_f)
    eligibility = evaluate_map_eligibility(event)
    event["pin_integrity_reason"] = eligibility["reason_code"]
    event["map_eligibility_state"] = eligibility["map_eligibility"]
    event["certified_pin"] = bool(eligibility["exact_pin_eligible"])

    if eligibility["map_eligibility"] == "MAP_READY":
        event["coordinate_status"] = "map_ready"
        return {
            "changed": geometry_reason == REASON_OK_SWAP,
            "reason": eligibility["reason_code"],
            "status": "map_ready",
            "before_lat": before_lat,
            "before_lng": before_lng,
            "after_lat": lat_f,
            "after_lng": lng_f,
        }

    # Backward-compatible transition: preserve valid legacy coordinates for
    # evidence rebuilding, but do not issue a new exact-pin certification.
    if eligibility["reason_code"] == REASON_LEGACY_EVIDENCE:
        event["coordinate_status"] = before_status or "map_ready"
        return {
            "changed": geometry_reason == REASON_OK_SWAP,
            "reason": REASON_LEGACY_EVIDENCE,
            "status": "legacy_evidence_pending_migration",
            "before_lat": before_lat,
            "before_lng": before_lng,
            "after_lat": lat_f,
            "after_lng": lng_f,
            "certified_pin": False,
        }

    event["coordinate_status"] = "list_only"
    event["certified_pin"] = False
    event["map_link"] = None
    return {
        "changed": before_status == "map_ready",
        "reason": eligibility["reason_code"],
        "status": "list_only",
        "before_lat": before_lat,
        "before_lng": before_lng,
        "after_lat": lat_f,
        "after_lng": lng_f,
    }


def nested_nycif_certify(event: dict[str, Any], *, allow_swap_correct: bool = True) -> dict[str, Any]:
    """Certify schema events that nest coordinate_status under nycif."""
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    flat = {
        "coordinate_status": nycif.get("coordinate_status") or event.get("coordinate_status"),
        "latitude": event.get("latitude"),
        "longitude": event.get("longitude"),
        "location_evidence": nycif.get("location_evidence") or event.get("location_evidence"),
    }
    result = certify_event_pin(flat, allow_swap_correct=allow_swap_correct)
    event["latitude"] = flat.get("latitude")
    event["longitude"] = flat.get("longitude")
    if "nycif" not in event or not isinstance(event["nycif"], dict):
        event["nycif"] = {}
    event["nycif"]["coordinate_status"] = flat.get("coordinate_status")
    event["nycif"]["map_eligibility_state"] = flat.get("map_eligibility_state")
    event["nycif"]["pin_integrity_reason"] = flat.get("pin_integrity_reason")
    event["nycif"]["certified_pin"] = flat.get("certified_pin")
    if flat.get("map_eligibility_state") not in {"MAP_READY", "REVIEW_REQUIRED"}:
        event["map_link"] = None
    return result
