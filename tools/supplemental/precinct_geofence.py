"""NYPD precinct geofence helpers for supplemental preview staging."""

from __future__ import annotations

import re
from typing import Any

try:
    from scripts.geojson_polygon_utils import point_in_polygon_geometry
except ModuleNotFoundError:  # pragma: no cover
    from geojson_polygon_utils import point_in_polygon_geometry

NYC_OPEN_DATA_PRECINCT_URL = (
    "https://data.cityofnewyork.us/api/views/y76i-bdw7/rows.geojson?accessType=DOWNLOAD"
)

PRESS_HEURISTIC = re.compile(
    r"\b(police|precinct|nypd|sought|seeking|wanted|press release|manhunt)\b",
    re.IGNORECASE,
)

GEOFENCE_STORY_PLACEHOLDER = (
    "Press-area geofence preview — boundary shows the NYPD precinct footprint "
    "for this pin. Email ingestion and approval are not wired yet."
)


def round_coord(value: float, digits: int = 5) -> float:
    return round(float(value), digits)


def round_geometry_coords(coords: Any, digits: int = 5) -> Any:
    if isinstance(coords, (int, float)):
        return round_coord(coords, digits)
    if isinstance(coords, list):
        return [round_geometry_coords(item, digits) for item in coords]
    return coords


def normalize_precinct_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        precinct = str(props.get("precinct") or props.get("Precinct") or "").strip()
        geometry = feature.get("geometry")
        if not precinct or not isinstance(geometry, dict):
            continue
        normalized.append(
            {
                "precinct": precinct,
                "geometry": {
                    "type": geometry.get("type"),
                    "coordinates": round_geometry_coords(geometry.get("coordinates")),
                },
            }
        )
    normalized.sort(key=lambda row: int(row["precinct"]) if row["precinct"].isdigit() else row["precinct"])
    return normalized


def precinct_lookup_index(precincts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(row["precinct"]): row for row in precincts}


def find_precinct_for_point(
    lat: float | None,
    lng: float | None,
    precincts: list[dict[str, Any]],
) -> str | None:
    if lat is None or lng is None:
        return None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    for row in precincts:
        geometry = row.get("geometry")
        if isinstance(geometry, dict) and point_in_polygon_geometry(lng_f, lat_f, geometry):
            return str(row.get("precinct"))
    return None


def is_press_release_candidate(row: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ("title", "display_location", "displayLocation", "intake_type")
    )
    return bool(PRESS_HEURISTIC.search(haystack))


def geofence_row_from_event(
    row: dict[str, Any],
    precincts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    overlap_key = row.get("overlap_key") or row.get("id")
    lat = row.get("lat", row.get("proposed_lat"))
    lng = row.get("lng", row.get("proposed_lng"))
    if not overlap_key:
        return None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    assigned_precinct = find_precinct_for_point(lat_f, lng_f, precincts)
    if not assigned_precinct:
        return None
    press_candidate = is_press_release_candidate(row)
    return {
        "overlap_key": overlap_key,
        "title": row.get("title") or "",
        "date": row.get("date") or "",
        "borough": row.get("borough") or "",
        "display_location": row.get("display_location") or row.get("displayLocation") or "",
        "lat": lat_f,
        "lng": lng_f,
        "assigned_precinct": assigned_precinct,
        "geofence_type": "nypd_precinct_boundary",
        "boundary_source": "nyc_open_data_y76i-bdw7",
        "press_release_candidate": press_candidate,
        "geofence_enabled_preview": True,
        "story_placeholder": GEOFENCE_STORY_PLACEHOLDER,
        "manual_review_status": "pending",
        "manual_review_notes": "",
        "manual_reviewer": None,
        "manual_reviewed_at_utc": None,
        "approval_decision_reason": None,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "production_feed": False,
    }
