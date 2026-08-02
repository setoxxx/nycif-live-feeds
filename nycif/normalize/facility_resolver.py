"""Fail-closed park/facility resolver for unresolved event locations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from enigma.shadow2.location_evidence import classify_location_evidence
from nycif.normalize.park_geometry import DEFAULT_LOOKUP_PATH, find_park_centroid

_FACILITY_RE = re.compile(
    r"\b(?:park|playground|pool|recreation\s+center|rec\s+center|field|court|"
    r"visitor\s+center|nature\s+center|gymnasium|garden|greenway|beach)\b",
    re.IGNORECASE,
)


def location_text(record: dict[str, Any]) -> str:
    return str(
        record.get("location")
        or record.get("display_location")
        or record.get("address")
        or ""
    ).strip()


def evidence_tier(record: dict[str, Any]) -> str:
    nycif = record.get("nycif") if isinstance(record.get("nycif"), dict) else {}
    explicit = record.get("evidence_tier") or nycif.get("evidence_tier")
    if explicit:
        return str(explicit)
    try:
        return classify_location_evidence(record).tier.value
    except Exception:
        return "unresolved"


def resolve_facility_anchor(
    record: dict[str, Any],
    *,
    lookup: dict[str, dict[str, Any]] | None = None,
    lookup_path: Path = DEFAULT_LOOKUP_PATH,
) -> dict[str, Any] | None:
    """Resolve an unresolved facility-in-park claim to an authoritative centroid."""
    if not isinstance(record, dict) or evidence_tier(record) != "unresolved":
        return None
    text = location_text(record)
    if not text or not _FACILITY_RE.search(text):
        return None
    match = find_park_centroid(text, lookup=lookup, lookup_path=lookup_path)
    if not match:
        return None
    return {
        "latitude": match["lat"],
        "longitude": match["lng"],
        "coordinate_precision": "park_level_anchor",
        "coordinate_source": "dpr_parks_properties_centroid",
        "park_id": match["park_id"],
        "park_name": match.get("park_name"),
        "park_borough": match.get("borough"),
        "park_match_type": match["match_type"],
        "park_query_name": match["query_name"],
        "promotion_allowed": False,
    }


def apply_facility_anchor(
    record: dict[str, Any],
    *,
    lookup: dict[str, dict[str, Any]] | None = None,
    lookup_path: Path = DEFAULT_LOOKUP_PATH,
) -> dict[str, Any] | None:
    """Return an enriched copy or ``None`` while preserving review-only safety."""
    resolved = resolve_facility_anchor(record, lookup=lookup, lookup_path=lookup_path)
    if not resolved:
        return None
    enriched = dict(record)
    enriched.update(resolved)
    enriched["coordinate_status"] = "approximate"
    enriched["display_disposition"] = "approximate_marker"
    enriched["promotion_allowed"] = False
    enriched["production_feed"] = False
    enriched["public_map_modified"] = False
    nycif = dict(enriched.get("nycif") or {})
    nycif.update(
        {
            "coordinate_status": "approximate",
            "display_disposition": "approximate_marker",
            "coordinate_precision": "park_level_anchor",
            "coordinate_source": "dpr_parks_properties_centroid",
            "promotion_allowed": False,
            "production_feed": False,
            "public_map_modified": False,
        }
    )
    enriched["nycif"] = nycif
    return enriched
