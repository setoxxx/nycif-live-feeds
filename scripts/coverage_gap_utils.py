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
# Shared supplemental GPS fill resolution + location resolution engine tiers
# ---------------------------------------------------------------------------

CALENDAR_PARKS_PROPOSALS_PATH = DATA_DIR / "calendar_parks_coord_match_proposals.json"
PARKS_PROPERTIES_PATH = DATA_DIR / "nyc_parks_properties_reference.json"

INTERSECTION_PATTERN = re.compile(r"^(.+?)\s+and\s+(.+)$", flags=re.IGNORECASE)

UNGEOCODABLE_LOCATION_MARKERS = (
    "citywide",
    "poll sites citywide",
    "see the flyer",
    "see flyer",
    "seee flyer",
    "please seee flyer",
    "across all five boroughs",
    "check website",
    "participating restaurants",
    "virtual/online",
    "virtual\\/online",
    "online events",
    "summer streets",
    "brooklyn bridge to broadway",
)

GEOSEARCH_FILL_METHODS = {
    "tier_2_geosearch_cache": "nyc_geosearch_cache",
    "tier_3_nyc_geosearch_live": "nyc_geosearch_live",
    "tier_2_geosearch_midpoint": "nyc_geosearch_midpoint",
}


def parse_facility_in_parent(display: Any) -> tuple[str, str] | None:
    text = str(display or "").strip()
    if not text:
        return None
    segment = _display_primary_segment(text)
    paren_match = re.match(r"^(.+?)\s*\(\s*in\s+(.+?)\)\s*$", segment, flags=re.IGNORECASE)
    if paren_match:
        child = paren_match.group(1).strip()
        parent = paren_match.group(2).strip()
        if child and parent:
            return child, parent
    match = re.search(r"\s+in\s+", segment, flags=re.IGNORECASE)
    if not match:
        return None
    child = segment[: match.start()].strip()
    parent = segment[match.end() :].strip()
    if not child or not parent:
        return None
    return child, parent


def _display_primary_segment(display: Any) -> str:
    text = str(display or "").strip()
    if not text:
        return ""
    return text.split(",")[0].strip()


def parse_intersection(display: Any) -> tuple[str, str] | None:
    segment = _display_primary_segment(display)
    if not segment:
        return None
    match = INTERSECTION_PATTERN.match(segment)
    if not match:
        return None
    street1 = match.group(1).strip()
    street2 = match.group(2).strip()
    if not street1 or not street2:
        return None
    return street1, street2


def parse_intersection_in_parent(display: Any) -> tuple[str, str, str] | None:
    decomposed = parse_facility_in_parent(display)
    if not decomposed:
        return None
    child, parent = decomposed
    parsed = parse_intersection(child)
    if not parsed:
        return None
    return parsed[0], parsed[1], parent


def is_ungeocodable_location(display: Any, borough: Any) -> bool:
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
    except ModuleNotFoundError:  # pragma: no cover
        from schema_v1_common import borough_label
    raw = str(borough or "").strip()
    if not raw or "," in raw:
        return None
    return borough_label(raw)


def load_parks_properties_name_index(
    path: Path = PARKS_PROPERTIES_PATH,
) -> dict[str, list[dict[str, Any]]]:
    try:
        from scripts.geojson_polygon_utils import build_parks_properties_name_index
    except ModuleNotFoundError:  # pragma: no cover
        from geojson_polygon_utils import build_parks_properties_name_index
    payload = load_json_file(path, {})
    properties = payload.get("properties") if isinstance(payload, dict) else payload
    if not isinstance(properties, list):
        return {}
    return build_parks_properties_name_index(properties)


def is_summer_streets_event(row: dict[str, Any]) -> bool:
    title = str(row.get("title") or "").lower()
    display = str(row.get("display_location") or "").lower()
    return "summer streets" in title or "brooklyn bridge to broadway" in display


def _fill_from_parks_properties_parent(
    parent: str,
    *,
    child: str | None = None,
    borough: Any,
    parks_properties_index: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any] | None:
    if not parks_properties_index:
        return None
    try:
        from scripts.geojson_polygon_utils import find_park_property_row
    except ModuleNotFoundError:  # pragma: no cover
        from geojson_polygon_utils import find_park_property_row

    row_prop = find_park_property_row(parent, borough, parks_properties_index)
    if not row_prop:
        return None
    lat = row_prop.get("centroid_lat")
    lng = row_prop.get("centroid_lng")
    if not valid_nyc_lat_lng(lat, lng):
        return None
    label = str(row_prop.get("signname") or row_prop.get("name311") or parent)
    child_note = f" for '{child}'" if child else ""
    return {
        "proposed_lat": float(lat),
        "proposed_lng": float(lng),
        "geocoder_source": "nyc_parks_properties_reference",
        "geocoder_confidence": "medium",
        "confidence_reason": (
            f"Rejected-pass fill: NYC Parks Properties parent polygon centroid for '{label}'"
            f"{child_note}; pin may be park interior centroid. For manual review only."
        ),
        "fill_method": "parks_properties_parent_centroid",
    }


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


def _geoclient_hit_fill(hit: dict[str, Any], *, parent_park: str | None = None) -> dict[str, Any]:
    confidence_reason = str(hit.get("confidence_reason") or "NYC Geoclient intersection match.")
    if parent_park:
        confidence_reason = (
            f"{confidence_reason} Parent context: {parent_park}. For manual review only."
        )
    else:
        confidence_reason = f"Rejected-pass fill: {confidence_reason} For manual review only."
    return {
        "proposed_lat": float(hit["lat"]),
        "proposed_lng": float(hit["lng"]),
        "geocoder_source": str(hit.get("geocoder_source") or "nyc_geoclient_intersection"),
        "geocoder_confidence": str(hit.get("confidence") or "high"),
        "confidence_reason": confidence_reason,
        "fill_method": "nyc_geoclient_intersection",
        "geocoder_label": hit.get("geoclient_label"),
    }


def fill_from_resolve_result(result: Any) -> dict[str, Any] | None:
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


def _apply_park_polygon_correction(
    fill: dict[str, Any],
    *,
    display: str,
    borough: Any,
    parks_properties_index: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    if not parks_properties_index:
        return fill
    try:
        from scripts.geojson_polygon_utils import snap_to_park_interior
    except ModuleNotFoundError:  # pragma: no cover
        from geojson_polygon_utils import snap_to_park_interior

    parent_park: str | None = None
    parsed_parent = parse_facility_in_parent(display)
    if parsed_parent:
        parent_park = parsed_parent[1]
    else:
        parsed_ix_parent = parse_intersection_in_parent(display)
        if parsed_ix_parent:
            parent_park = parsed_ix_parent[2]
    if not parent_park:
        return fill

    lat = fill.get("proposed_lat")
    lng = fill.get("proposed_lng")
    if lat is None or lng is None:
        return fill
    snapped = snap_to_park_interior(float(lat), float(lng), parent_park, borough, parks_properties_index)
    if not snapped:
        return fill
    new_lat, new_lng, label = snapped
    out = dict(fill)
    out["proposed_lat"] = new_lat
    out["proposed_lng"] = new_lng
    out["fill_method"] = "park_polygon_correction"
    if out.get("geocoder_confidence") == "high":
        out["geocoder_confidence"] = "medium"
    out["confidence_reason"] = (
        f"Rejected-pass fill: relocated pin from street corner into '{label}' park interior "
        f"(parent context '{parent_park}') for manual review only."
    )
    return out


def resolve_supplemental_coordinates(
    row: dict[str, Any],
    gazetteer: Any,
    parks_overlap: dict[str, dict[str, Any]] | None = None,
    resolver: Any | None = None,
    *,
    calendar_parks_overlap: dict[str, dict[str, Any]] | None = None,
    geoclient: Any | None = None,
    parks_properties_index: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    """Tiered supplemental coordinate fill for a rejected/pending review row."""
    parks_overlap = parks_overlap or {}
    calendar_parks_overlap = calendar_parks_overlap or {}

    overlap = str(row.get("overlap_key") or "")
    if overlap and overlap in parks_overlap:
        hit = parks_overlap[overlap]
        lat, lng = row_coords(hit)
        if valid_nyc_lat_lng(lat, lng):
            fill = {
                "proposed_lat": float(lat),
                "proposed_lng": float(lng),
                "geocoder_source": "nyc_parks_bigapps_events_snapshot",
                "geocoder_confidence": "high",
                "confidence_reason": (
                    "Rejected-pass fill: Parks BigApps title+date match coordinates for manual review only."
                ),
                "fill_method": "parks_overlap_key",
            }
            return _apply_park_polygon_correction(
                fill,
                display=str(row.get("display_location") or ""),
                borough=row.get("borough"),
                parks_properties_index=parks_properties_index,
            )

    display = str(row.get("display_location") or "")
    borough = row.get("borough")

    if is_ungeocodable_location(display, borough):
        return None

    decomposed = parse_facility_in_parent(display)
    if decomposed:
        child, parent = decomposed
        hit = gazetteer.lookup_display(child, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            fill = _gazetteer_hit_fill(hit, fill_method="location_gazetteer")
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )
        hit = gazetteer.lookup_display(parent, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            fill = _gazetteer_hit_fill(hit, fill_method="parent_park_fallback", force_confidence="medium")
            fill["confidence_reason"] = (
                f"Rejected-pass fill: parent park '{parent}' gazetteer match "
                f"(no facility-level match for '{child}'); pin may be the park centroid. "
                "For manual review only."
            )
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )
        if not parse_intersection(child):
            fill = _fill_from_parks_properties_parent(
                parent,
                child=child,
                borough=borough,
                parks_properties_index=parks_properties_index,
            )
            if fill:
                return _apply_park_polygon_correction(
                    fill, display=display, borough=borough, parks_properties_index=parks_properties_index
                )
    else:
        hit = gazetteer.lookup_display(display, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            fill = _gazetteer_hit_fill(hit, fill_method="location_gazetteer")
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )

    parsed_ix_parent = parse_intersection_in_parent(display)
    if parsed_ix_parent and geoclient is not None:
        street1, street2, parent = parsed_ix_parent
        hit = geoclient.resolve_intersection(street1, street2, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            fill = _geoclient_hit_fill(hit, parent_park=parent)
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )
        fill = _fill_from_parks_properties_parent(
            parent,
            child=f"{street1} and {street2}",
            borough=borough,
            parks_properties_index=parks_properties_index,
        )
        if fill:
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )

    parsed_ix = parse_intersection(display)
    if parsed_ix and geoclient is not None:
        street1, street2 = parsed_ix
        hit = geoclient.resolve_intersection(street1, street2, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            fill = _geoclient_hit_fill(hit)
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )

    if overlap and overlap in calendar_parks_overlap:
        hit = calendar_parks_overlap[overlap]
        lat, lng = row_coords(hit)
        if valid_nyc_lat_lng(lat, lng):
            fill = {
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
            return _apply_park_polygon_correction(
                fill, display=display, borough=borough, parks_properties_index=parks_properties_index
            )

    if resolver is None:
        return None

    boro = supplemental_borough_for_geosearch(borough)
    query = decomposed[0] if decomposed else display
    outside_match = re.search(r"\boutside\s+(.+)$", display, flags=re.IGNORECASE)
    if outside_match:
        query = outside_match.group(1).strip(" ,.")
    result = resolver.resolve(display_location=query, borough=boro)
    fill = fill_from_resolve_result(result)
    if not fill and decomposed:
        result = resolver.resolve(display_location=decomposed[1], borough=boro)
        fill = fill_from_resolve_result(result)
    if not fill:
        return None
    return _apply_park_polygon_correction(
        fill, display=display, borough=borough, parks_properties_index=parks_properties_index
    )
