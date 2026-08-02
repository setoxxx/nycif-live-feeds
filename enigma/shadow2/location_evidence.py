"""Deterministic location-evidence classification for Enigma SHADOW-2.

This module classifies claims. It does not geocode, certify semantics, or grant
exact-pin eligibility. Exact-pin eligibility remains false until a later
validator proves every tier-specific requirement.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LocationPrecisionTier(str, Enum):
    EXACT_SOURCE_COORDINATE = "exact_source_coordinate"
    EXACT_ADDRESS = "exact_address"
    EXACT_INTERSECTION = "exact_intersection"
    CERTIFIED_STREET_SEGMENT = "certified_street_segment"
    CERTIFIED_FACILITY = "certified_facility"
    APPROXIMATE_AREA = "approximate_area"
    UNRESOLVED = "unresolved"


class ValidationState(str, Enum):
    VALIDATED = "validated"
    UNVALIDATED = "unvalidated"
    INVALID = "invalid"
    NOT_APPLICABLE = "not_applicable"


class ReasonCode(str, Enum):
    BOROUGH_MISMATCH = "BOROUGH_MISMATCH"
    STREET_TOKEN_MISMATCH = "STREET_TOKEN_MISMATCH"
    GENERIC_FALLBACK = "GENERIC_FALLBACK"
    NULL_ISLAND = "NULL_ISLAND"
    NONFINITE_COORDINATE = "NONFINITE_COORDINATE"
    COORDINATE_SOURCE_UNPROVEN = "COORDINATE_SOURCE_UNPROVEN"
    FACILITY_ID_UNKNOWN = "FACILITY_ID_UNKNOWN"
    SEGMENT_UNCERTIFIED = "SEGMENT_UNCERTIFIED"
    SEGMENT_ENDPOINT_MISMATCH = "SEGMENT_ENDPOINT_MISMATCH"
    DISTANCE_FROM_TRUSTED_EXCEEDED = "DISTANCE_FROM_TRUSTED_EXCEEDED"
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    MALFORMED_EVIDENCE = "MALFORMED_EVIDENCE"


@dataclass(frozen=True, slots=True)
class LocationEvidence:
    tier: LocationPrecisionTier
    validation_state: ValidationState
    exact_pin_eligible: bool = False
    promotion_allowed: bool = False
    reason_code: ReasonCode | None = None
    reason_detail: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.promotion_allowed:
            raise ValueError("SHADOW-2 classification cannot authorize promotion")
        if self.exact_pin_eligible and self.validation_state is not ValidationState.VALIDATED:
            raise ValueError("exact pin eligibility requires validated evidence")
        object.__setattr__(self, "evidence", dict(self.evidence))


_SOURCE_COORDINATE_MARKERS = {
    "source",
    "source_provided",
    "source-provided",
    "official_source",
    "official-source",
    "raw_source",
}
_GENERIC_FALLBACK_MARKERS = {
    "generic_fallback",
    "generic_street_fallback",
    "street_name_fallback",
}
_STREET_DESIGNATOR = re.compile(
    r"(?:\b\d+(?:st|nd|rd|th)?\b|\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|"
    r"lane|ln|drive|dr|place|pl|parkway|pkwy|highway|hwy|way|court|ct|terrace|ter)\b)",
    re.IGNORECASE,
)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coordinate_pair(record: dict[str, Any]) -> tuple[float, float] | None:
    lat = record.get("latitude", record.get("lat"))
    lng = record.get("longitude", record.get("lng"))
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lat_f) or not math.isfinite(lng_f):
        return None
    if abs(lat_f) <= 1e-9 and abs(lng_f) <= 1e-9:
        return None
    return lat_f, lng_f


def _coordinate_problem(record: dict[str, Any]) -> ReasonCode | None:
    lat_present = any(key in record and record.get(key) not in (None, "") for key in ("latitude", "lat"))
    lng_present = any(key in record and record.get(key) not in (None, "") for key in ("longitude", "lng"))
    if not lat_present and not lng_present:
        return None
    lat = record.get("latitude", record.get("lat"))
    lng = record.get("longitude", record.get("lng"))
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return ReasonCode.NONFINITE_COORDINATE
    if not math.isfinite(lat_f) or not math.isfinite(lng_f):
        return ReasonCode.NONFINITE_COORDINATE
    if abs(lat_f) <= 1e-9 and abs(lng_f) <= 1e-9:
        return ReasonCode.NULL_ISLAND
    return None


def _provenance_marker(record: dict[str, Any]) -> str | None:
    nycif = record.get("nycif") if isinstance(record.get("nycif"), dict) else {}
    for key in ("coordinate_source", "coordinate_origin", "geocoder_source"):
        value = _text(record.get(key)) or _text(nycif.get(key))
        if value:
            return value.lower().replace(" ", "_")
    return None


def _is_generic_fallback(record: dict[str, Any]) -> bool:
    marker = _provenance_marker(record)
    resolver_tier = _text(record.get("resolver_tier"))
    values = {value.lower().replace(" ", "_") for value in (marker, resolver_tier) if value}
    return bool(values & _GENERIC_FALLBACK_MARKERS) or any("generic" in value and "fallback" in value for value in values)


def _source_coordinates_proven(record: dict[str, Any]) -> bool:
    marker = _provenance_marker(record)
    if marker in _SOURCE_COORDINATE_MARKERS:
        return True
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return source.get("coordinates_provided") is True or record.get("source_coordinates_provided") is True


def _facility_claim(record: dict[str, Any]) -> tuple[str | None, str | None]:
    name = None
    for key in ("facility_name", "park_name", "venue_name", "facility", "park", "venue"):
        name = _text(record.get(key))
        if name:
            break
    facility_id = None
    for key in ("facility_id", "park_id", "venue_id", "facility_uid", "park_id_park"):
        facility_id = _text(record.get(key))
        if facility_id:
            break
    return name, facility_id


def _segment_claim(record: dict[str, Any]) -> dict[str, str] | None:
    street = _text(record.get("street") or record.get("road"))
    cross1 = _text(record.get("cross_street_1") or record.get("cross_street"))
    cross2 = _text(record.get("cross_street_2") or record.get("cross_street_end"))
    if street and cross1 and cross2:
        return {"street": street, "cross_street_1": cross1, "cross_street_2": cross2}

    location = _text(record.get("display_location") or record.get("location"))
    if not location:
        return None
    match = re.fullmatch(r"\s*(.+?)\s+between\s+(.+?)\s+and\s+(.+?)\s*", location, re.IGNORECASE)
    if not match:
        return None
    parts = [part.strip(" ,") for part in match.groups()]
    if not all(parts):
        return None
    return {"street": parts[0], "cross_street_1": parts[1], "cross_street_2": parts[2]}


def _looks_like_street(value: str) -> bool:
    return bool(_STREET_DESIGNATOR.search(value))


def _intersection_claim(record: dict[str, Any]) -> dict[str, str] | None:
    cross1 = _text(record.get("cross_street_1") or record.get("cross_street"))
    cross2 = _text(record.get("cross_street_2"))
    if cross1 and cross2 and _looks_like_street(cross1) and _looks_like_street(cross2):
        return {"cross_street_1": cross1, "cross_street_2": cross2}

    location = _text(record.get("display_location") or record.get("location"))
    if not location or "between" in location.lower():
        return None
    corner = re.fullmatch(
        r"\s*corner\s+of\s+(.+?)\s+(?:and|&)\s+(.+?)\s*",
        location,
        re.IGNORECASE,
    )
    if corner:
        first, second = (part.strip(" ,") for part in corner.groups())
        if _looks_like_street(first) or _looks_like_street(second):
            return {"cross_street_1": first, "cross_street_2": second}

    ampersand = re.fullmatch(r"\s*(.+?)\s+&\s+(.+?)\s*", location)
    if ampersand:
        first, second = (part.strip(" ,") for part in ampersand.groups())
        if _looks_like_street(first) or _looks_like_street(second):
            return {"cross_street_1": first, "cross_street_2": second}

    at_sign = re.fullmatch(r"\s*(.+?)\s+(?:at|@)\s+(.+?)\s*", location, re.IGNORECASE)
    if at_sign:
        first, second = (part.strip(" ,") for part in at_sign.groups())
        if _looks_like_street(first) and _looks_like_street(second):
            return {"cross_street_1": first, "cross_street_2": second}
    return None


def _address_claim(record: dict[str, Any]) -> str | None:
    for key in ("street_address", "address"):
        value = _text(record.get(key))
        if value and re.match(r"^\d+[A-Za-z-]*\s+\S", value):
            return value
    location = _text(record.get("display_location") or record.get("location"))
    if location and re.match(r"^\d+[A-Za-z-]*\s+\S", location):
        return location
    return None


def _area_claim(record: dict[str, Any]) -> dict[str, str | None] | None:
    borough = _text(record.get("borough"))
    neighborhood = _text(record.get("neighborhood") or record.get("area"))
    municipality = _text(record.get("municipality") or record.get("city") or record.get("town"))
    if not any((borough, neighborhood, municipality)):
        return None
    return {"borough": borough, "neighborhood": neighborhood, "municipality": municipality}


def classify_location_evidence(record: dict[str, Any]) -> LocationEvidence:
    """Classify location claims without performing semantic certification."""

    if not isinstance(record, dict):
        raise TypeError("record must be a dictionary")

    coordinate_problem = _coordinate_problem(record)
    pair = _coordinate_pair(record)
    if pair and _is_generic_fallback(record):
        area = _area_claim(record)
        return LocationEvidence(
            tier=LocationPrecisionTier.APPROXIMATE_AREA if area else LocationPrecisionTier.UNRESOLVED,
            validation_state=ValidationState.INVALID,
            reason_code=ReasonCode.GENERIC_FALLBACK,
            reason_detail="Generic fallback coordinates are not exact-pin evidence.",
            evidence={"latitude": pair[0], "longitude": pair[1], **(area or {})},
        )

    if pair and _source_coordinates_proven(record):
        return LocationEvidence(
            tier=LocationPrecisionTier.EXACT_SOURCE_COORDINATE,
            validation_state=ValidationState.UNVALIDATED,
            reason_detail="Source-coordinate provenance is present; semantic validation is pending.",
            evidence={
                "latitude": pair[0],
                "longitude": pair[1],
                "coordinate_source": _provenance_marker(record),
            },
        )

    facility_name, facility_id = _facility_claim(record)
    if facility_name and facility_id:
        return LocationEvidence(
            tier=LocationPrecisionTier.CERTIFIED_FACILITY,
            validation_state=ValidationState.UNVALIDATED,
            reason_detail="Facility claim has an authoritative identifier; registry validation is pending.",
            evidence={"facility_name": facility_name, "facility_id": facility_id},
        )

    segment = _segment_claim(record)
    if segment:
        return LocationEvidence(
            tier=LocationPrecisionTier.CERTIFIED_STREET_SEGMENT,
            validation_state=ValidationState.UNVALIDATED,
            reason_code=ReasonCode.SEGMENT_UNCERTIFIED,
            reason_detail="Segment endpoints are present; endpoint and midpoint certification is pending.",
            evidence=segment,
        )

    intersection = _intersection_claim(record)
    if intersection:
        return LocationEvidence(
            tier=LocationPrecisionTier.EXACT_INTERSECTION,
            validation_state=ValidationState.UNVALIDATED,
            reason_detail="Intersection claim is present; geocoder and borough validation are pending.",
            evidence=intersection,
        )

    address = _address_claim(record)
    if address:
        return LocationEvidence(
            tier=LocationPrecisionTier.EXACT_ADDRESS,
            validation_state=ValidationState.UNVALIDATED,
            reason_detail="Numbered address is present; geocoder and borough validation are pending.",
            evidence={"street_address": address},
        )

    area = _area_claim(record)
    if area:
        reason = ReasonCode.COORDINATE_SOURCE_UNPROVEN if pair else coordinate_problem
        detail = None
        if pair:
            detail = "Coordinates exist but source provenance is unproven; only broad area evidence is trusted."
        elif coordinate_problem:
            detail = "Invalid coordinates were ignored; broad area evidence remains."
        return LocationEvidence(
            tier=LocationPrecisionTier.APPROXIMATE_AREA,
            validation_state=ValidationState.NOT_APPLICABLE,
            reason_code=reason,
            reason_detail=detail,
            evidence={**area, **({"latitude": pair[0], "longitude": pair[1]} if pair else {})},
        )

    if facility_name and not facility_id:
        return LocationEvidence(
            tier=LocationPrecisionTier.UNRESOLVED,
            validation_state=ValidationState.UNVALIDATED,
            reason_code=ReasonCode.FACILITY_ID_UNKNOWN,
            reason_detail="Facility name is present without an authoritative facility identifier.",
            evidence={"facility_name": facility_name},
        )

    if pair:
        return LocationEvidence(
            tier=LocationPrecisionTier.UNRESOLVED,
            validation_state=ValidationState.UNVALIDATED,
            reason_code=ReasonCode.COORDINATE_SOURCE_UNPROVEN,
            reason_detail="Finite coordinates exist without proof that the source supplied them.",
            evidence={"latitude": pair[0], "longitude": pair[1]},
        )

    if coordinate_problem:
        return LocationEvidence(
            tier=LocationPrecisionTier.UNRESOLVED,
            validation_state=ValidationState.INVALID,
            reason_code=coordinate_problem,
            reason_detail="Coordinate fields are present but unusable.",
        )

    return LocationEvidence(
        tier=LocationPrecisionTier.UNRESOLVED,
        validation_state=ValidationState.NOT_APPLICABLE,
        reason_code=ReasonCode.MISSING_EVIDENCE,
        reason_detail="No usable location-evidence fields are present.",
    )
