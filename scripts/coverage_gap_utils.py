"""Shared helpers for supplemental coverage-gap review artifacts."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def date_key(value: Any) -> str:
    text = str(value or "")
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def title_key(value: Any) -> str:
    return normalize_text_legacy(str(value or ""))


def overlap_key(title: Any, start: Any) -> str:
    return "|".join([title_key(title), date_key(start)])


def simplified_place(text: str) -> str:
    first = str(text or "").split(",")[0].strip()
    if ":" in first:
        first = first.split(":", 1)[0].strip()
    if "(" in first:
        first = first.split("(", 1)[0].strip()
    return normalize_text_legacy(first)


def safety_fields() -> dict[str, Any]:
    return {
        "manual_review_status": "pending",
        "manual_reviewer": None,
        "manual_reviewed_at_utc": None,
        "manual_review_notes": None,
        "approval_decision_reason": None,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def google_maps_search_url(display: str, borough: str = "") -> str:
    parts = [str(display or "").strip(), str(borough or "").strip(), "New York, NY"]
    query = ", ".join(part for part in parts if part)
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def google_maps_pin_url(lat: Any, lng: Any) -> str:
    if lat is None or lng is None:
        return ""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(str(lat) + ',' + str(lng))}"


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def row_coords(row: dict[str, Any]) -> tuple[float | None, float | None]:
    lat = row.get("lat") or row.get("latitude") or row.get("proposed_lat")
    lng = row.get("lng") or row.get("lon") or row.get("longitude") or row.get("proposed_lng")
    if valid_nyc_lat_lng(lat, lng):
        return float(lat), float(lng)
    return None, None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Shared supplemental GPS fill resolution
#
# Extracted from the M11 supplemental rejected-pass batch logic so any
# coverage-gap / GPS-fill script (rejected-pass re-review, coverage-gap
# review queues, unfilled-proposal geocoding, etc.) can reuse the same
# tiered coordinate-fill behavior instead of reimplementing it per script.
# ---------------------------------------------------------------------------

CALENDAR_PARKS_PROPOSALS_PATH = DATA_DIR / "calendar_parks_coord_match_proposals.json"

UNGEOCODABLE_LOCATION_MARKERS = (
    "citywide",
    "poll sites citywide",
    "see the flyer",
    "see flyer",
    "across all five boroughs",
    "check website",
    "participating restaurants",
)

# ResolveResult.tier -> supplemental fill_method label.
GEOSEARCH_FILL_METHODS = {
    "tier_2_geosearch_cache": "nyc_geosearch_cache",
    "tier_3_nyc_geosearch_live": "nyc_geosearch_live",
    "tier_2_geosearch_midpoint": "nyc_geosearch_midpoint",
}


def parse_facility_in_parent(display: Any) -> tuple[str, str] | None:
    """Split a "Child Facility in Parent Park" display string.

    Splits on the first standalone " in " occurrence (word-boundary,
    case-insensitive) so rows like "Pétanque Court in Washington Square Park"
    decompose to ("Pétanque Court", "Washington Square Park"). Returns None
    when there is no such split point (plain park/address names, e.g. "Bryant
    Park" or "125th Street and Marginal Street") or when either side would be
    empty.
    """
    text = str(display or "").strip()
    if not text:
        return None
    match = re.search(r"\s+in\s+", text, flags=re.IGNORECASE)
    if not match:
        return None
    child = text[: match.start()].strip()
    parent = text[match.end() :].strip()
    if not child or not parent:
        return None
    return child, parent


def is_ungeocodable_location(display: Any, borough: Any) -> bool:
    """True for locations that should never be geocoded (permanent rejects)."""
    text = str(display or "").lower()
    if any(marker in text for marker in UNGEOCODABLE_LOCATION_MARKERS):
        return True
    brow = str(borough or "")
    if "," in brow and len([part for part in brow.split(",") if part.strip()]) >= 2:
        return True
    return False


def build_calendar_parks_overlap_index(
    path: Path = CALENDAR_PARKS_PROPOSALS_PATH,
) -> dict[str, dict[str, Any]]:
    """Index data/calendar_parks_coord_match_proposals.json by overlap_key.

    Only proposals that already carry valid NYC coordinates are indexed;
    pending/unfilled proposals are skipped so this tier never introduces a
    null-coordinate "hit".
    """
    payload = load_json_file(path, {})
    proposals = payload.get("proposals") if isinstance(payload, dict) else payload
    if not isinstance(proposals, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in proposals:
        if not isinstance(row, dict):
            continue
        key = str(row.get("overlap_key") or "")
        if not key:
            continue
        lat, lng = row_coords(row)
        if valid_nyc_lat_lng(lat, lng):
            index[key] = row
    return index


def supplemental_borough_for_geosearch(borough: Any) -> str | None:
    try:
        from scripts.schema_v1_common import borough_label
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        from schema_v1_common import borough_label
    raw = str(borough or "").strip()
    if not raw or "," in raw:
        return None
    return borough_label(raw)


def _gazetteer_hit_fill(hit: dict[str, Any], *, fill_method: str, force_confidence: str | None = None) -> dict[str, Any]:
    confidence = force_confidence or str(hit.get("confidence") or "medium")
    if confidence not in {"high", "medium"}:
        confidence = "medium"
    return {
        "proposed_lat": float(hit["lat"]),
        "proposed_lng": float(hit["lng"]),
        "geocoder_source": str(hit.get("source") or "nyc_location_gazetteer"),
        "geocoder_confidence": confidence,
        "confidence_reason": (
            f"Rejected-pass fill: {hit.get('confidence_reason') or 'Gazetteer location match'} "
            "for manual review only."
        ),
        "fill_method": fill_method,
    }


def fill_from_resolve_result(result: Any) -> dict[str, Any] | None:
    """Convert an NYCLocationResolver ResolveResult into a supplemental fill dict."""
    if not result.resolved or result.lat is None or result.lng is None:
        return None
    if not valid_nyc_lat_lng(result.lat, result.lng):
        return None
    fill_method = GEOSEARCH_FILL_METHODS.get(result.tier, "location_gazetteer")
    confidence = str(result.confidence or "medium")
    if confidence not in {"high", "medium"}:
        confidence = "medium"
    source = str(result.source or "nyc_geosearch_planninglabs")
    fill = {
        "proposed_lat": float(result.lat),
        "proposed_lng": float(result.lng),
        "geocoder_source": source,
        "geocoder_confidence": confidence,
        "confidence_reason": (
            f"Rejected-pass fill: {result.confidence_reason or 'NYC GeoSearch match'} "
            "for manual review only."
        ),
        "fill_method": fill_method,
        "resolver_tier": result.tier,
        "geocoder_label": result.label,
        "query_used": result.query_used,
    }
    if str(result.tier or "").startswith("tier_1_"):
        fill["fill_method"] = "location_gazetteer"
    return fill


def resolve_supplemental_coordinates(
    row: dict[str, Any],
    gazetteer: Any,
    parks_overlap: dict[str, dict[str, Any]] | None = None,
    resolver: Any | None = None,
    *,
    calendar_parks_overlap: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Tiered supplemental coordinate fill for a rejected/pending review row.

    Tiers, in order:
    1. Exact Parks BigApps title+date overlap (raw snapshot index, when
       supplied by the caller — highest confidence, same source event).
    2. "Child in Parent" decomposition of display_location:
       a. gazetteer lookup on the CHILD facility name (with borough)
       b. gazetteer lookup on the PARENT park name (medium confidence —
          the pin may resolve to the park centroid, not the exact facility)
    3. Full display-string gazetteer lookup, for rows that do not match the
       "X in Y" pattern (plain park/address names).
    4. data/calendar_parks_coord_match_proposals.json by overlap_key —
       tried before GeoSearch so an already-computed calendar/Parks
       title+date coordinate match is preferred over a fresh geocode.
    5. NYCLocationResolver.resolve() — street-segment midpoint, GeoSearch
       cache, and (if enabled) live GeoSearch. Uses the CHILD name when the
       row decomposed, else the full display text.
    6. None — permanent-reject candidate (no resolvable GPS).
    """
    parks_overlap = parks_overlap or {}
    calendar_parks_overlap = calendar_parks_overlap or {}

    overlap = str(row.get("overlap_key") or "")
    if overlap and overlap in parks_overlap:
        hit = parks_overlap[overlap]
        lat, lng = row_coords(hit)
        if valid_nyc_lat_lng(lat, lng):
            return {
                "proposed_lat": float(lat),
                "proposed_lng": float(lng),
                "geocoder_source": "nyc_parks_bigapps_events_snapshot",
                "geocoder_confidence": "high",
                "confidence_reason": (
                    "Rejected-pass fill: Parks BigApps title+date match coordinates for manual review only."
                ),
                "fill_method": "parks_overlap_key",
            }

    display = str(row.get("display_location") or "")
    borough = row.get("borough")

    decomposed = parse_facility_in_parent(display)
    if decomposed:
        child, parent = decomposed
        hit = gazetteer.lookup_display(child, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            return _gazetteer_hit_fill(hit, fill_method="location_gazetteer")
        hit = gazetteer.lookup_display(parent, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            fill = _gazetteer_hit_fill(hit, fill_method="parent_park_fallback", force_confidence="medium")
            fill["confidence_reason"] = (
                f"Rejected-pass fill: parent park '{parent}' gazetteer match "
                f"(no facility-level match for '{child}'); pin may be the park centroid. "
                "For manual review only."
            )
            return fill
    else:
        hit = gazetteer.lookup_display(display, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            return _gazetteer_hit_fill(hit, fill_method="location_gazetteer")

    if overlap and overlap in calendar_parks_overlap:
        hit = calendar_parks_overlap[overlap]
        lat, lng = row_coords(hit)
        if valid_nyc_lat_lng(lat, lng):
            return {
                "proposed_lat": float(lat),
                "proposed_lng": float(lng),
                "geocoder_source": "calendar_parks_coord_match_proposals",
                "geocoder_confidence": "high",
                "confidence_reason": (
                    "Rejected-pass fill: Calendar+Parks title/date overlap match "
                    "(calendar_parks_coord_match_proposals) for manual review only."
                ),
                "fill_method": "parks_overlap_key",
            }

    if resolver is None or is_ungeocodable_location(display, borough):
        return None

    boro = supplemental_borough_for_geosearch(borough)
    query = decomposed[0] if decomposed else display
    result = resolver.resolve(display_location=query, borough=boro)
    return fill_from_resolve_result(result)
