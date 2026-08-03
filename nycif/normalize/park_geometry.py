"""Authoritative NYC Parks property centroid lookup.

The module consumes the NYC Open Data Parks Properties dataset (``enfh-gkve``),
calculates deterministic area-weighted centroids from Polygon/MultiPolygon
geometry, and builds a fail-closed name lookup. Ambiguous aliases are omitted.
No coordinate is invented and no generic NYC fallback is ever returned.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen

DATASET_ID = "enfh-gkve"
DATASET_URL = (
    f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
    "?$limit=50000&$order=gispropnum,signname,name311,location"
)
DEFAULT_LOOKUP_PATH = Path(__file__).resolve().parents[2] / "data" / "park_centroids.json"
DEFAULT_AMBIGUOUS_PATH = Path(__file__).resolve().parents[2] / "data" / "park_centroids_ambiguous_aliases.json"

NYC_BOUNDS = {
    "min_lat": 40.4774,
    "max_lat": 40.9176,
    "min_lng": -74.2591,
    "max_lng": -73.7004,
}

_NAME_FIELDS = (
    "signname",
    "sign_name",
    "name311",
    "propertyname",
    "property_name",
    "park_name",
    "parkname",
    "location",
    "name",
)
_ID_FIELDS = (
    "gispropnum",
    "park_id",
    "parkid",
    "parknum",
    "omppropid",
    "globalid",
)
_GEOMETRY_FIELDS = (
    "the_geom",
    "multipolygon",
    "geometry",
    "shape",
    "geocoded_column",
)
_BOROUGH_FIELDS = ("borough", "park_borough", "boro")

_SUFFIX_RE = re.compile(
    r"\b(?:park|playground|recreation\s+center|recreational\s+center|rec\s+center|"
    r"community\s+center|nature\s+center|visitor\s+center|pool|athletic\s+field|"
    r"ballfield|field|courts?|garden|greenway|beach)\b\.?$",
    re.IGNORECASE,
)
_LEADING_ARTICLE_RE = re.compile(r"^(?:the)\s+", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_TARGET_SUFFIX = (
    r"park|playground|recreation\s+center|recreational\s+center|rec\s+center|"
    r"community\s+center|nature\s+center|visitor\s+center|pool|athletic\s+field|"
    r"ballfield|field|garden|greenway|beach"
)
_RELATION_PATTERNS = (
    re.compile(rf"\bentrance\s+to\s+(.+?\b(?:{_TARGET_SUFFIX})\b)", re.IGNORECASE),
    re.compile(rf"\b(?:in|at)\s+(.+?\b(?:{_TARGET_SUFFIX})\b)", re.IGNORECASE),
)
_WHOLE_TARGET_RE = re.compile(rf"^(.+?\b(?:{_TARGET_SUFFIX})\b)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PolygonMoment:
    signed_area: float
    centroid_x: float
    centroid_y: float


@dataclass(frozen=True, slots=True)
class BuildResult:
    lookup: dict[str, dict[str, Any]]
    source_rows: int
    geometry_rows: int
    park_groups: int
    aliases_written: int
    ambiguous_aliases: tuple[str, ...]
    invalid_geometry_rows: int


def _clean_text(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").strip())


def normalize_park_name(value: Any) -> str:
    """Normalize a park/facility name while treating common suffixes as aliases."""
    text = unicodedata.normalize("NFKD", _clean_text(value)).encode("ascii", "ignore").decode()
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    text = _LEADING_ARTICLE_RE.sub("", text)
    previous = None
    while text and text != previous:
        previous = text
        text = _SUFFIX_RE.sub("", text).strip()
    return _SPACE_RE.sub(" ", text).strip()


def extract_park_names(location_text: str) -> list[str]:
    """Extract candidate container park names from conservative relation patterns."""
    text = _clean_text(location_text).strip(" ,;:-")
    if not text:
        return []
    candidates: list[str] = []
    for pattern in _RELATION_PATTERNS:
        for match in pattern.finditer(text):
            candidate = match.group(1).strip(" ,;:-()[]")
            if candidate:
                candidates.append(candidate)
    whole = _WHOLE_TARGET_RE.fullmatch(text)
    if whole:
        candidates.append(whole.group(1).strip(" ,;:-()[]"))
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in reversed(candidates):
        key = candidate.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    unique.reverse()
    return unique


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_nyc_point(lat: Any, lng: Any) -> bool:
    lat_f = _finite(lat)
    lng_f = _finite(lng)
    return bool(
        lat_f is not None
        and lng_f is not None
        and NYC_BOUNDS["min_lat"] <= lat_f <= NYC_BOUNDS["max_lat"]
        and NYC_BOUNDS["min_lng"] <= lng_f <= NYC_BOUNDS["max_lng"]
        and not (abs(lat_f) < 1e-12 and abs(lng_f) < 1e-12)
    )


# =============================================================================
# PATCH 02 v4.1 — DPR Alias Expansion (independent test)
# =============================================================================

_BOROUGH_CODE_MAP = {
    "manhattan": "M",
    "mn": "M",
    "new york": "M",
    "bronx": "X",
    "bx": "X",
    "the bronx": "X",
    "brooklyn": "B",
    "bk": "B",
    "kings": "B",
    "queens": "Q",
    "qn": "Q",
    "staten island": "R",
    "si": "R",
    "richmond": "R",
}


def canonical_borough(borough_text: Any) -> str | None:
    """Return the canonical DPR borough code, or ``None`` if unknown."""
    text = _clean_text(borough_text)
    if not text:
        return None
    code = _BOROUGH_CODE_MAP.get(text.casefold())
    if code:
        return code
    uppercase = text.upper()
    return uppercase if len(uppercase) == 1 and uppercase in "MBQXR" else None


def valid_nyc_point(lat: Any, lng: Any) -> bool:
    """Public fail-closed wrapper around the module's NYC bounds check."""
    return _valid_nyc_point(lat, lng)


def build_park_id_index(
    park_lookup: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a deterministic authority-ID index from the alias lookup.

    All aliases for an authority ID must agree on coordinates and borough.
    Conflicting lookup evidence is rejected rather than selected arbitrarily.
    """
    index: dict[str, dict[str, Any]] = {}
    for alias, entry in sorted(park_lookup.items()):
        if not isinstance(entry, dict):
            continue
        park_id_value = entry.get("park_id") or entry.get("gispropnum")
        if not park_id_value:
            continue
        park_id = str(park_id_value).strip().upper()
        lat = _finite(entry.get("lat"))
        lng = _finite(entry.get("lng"))
        borough = canonical_borough(entry.get("borough"))
        park_name = entry.get("park_name") or alias

        if park_id not in index:
            index[park_id] = {
                "lat": lat,
                "lng": lng,
                "borough": borough,
                "park_name": park_name,
                "anchor_method": entry.get("anchor_method"),
                "source_dataset": entry.get("source_dataset"),
                "aliases": [alias],
            }
            continue

        existing = index[park_id]
        if existing["lat"] != lat or existing["lng"] != lng:
            raise ValueError(
                f"Park ID {park_id} coordinate inconsistency: "
                f"{existing['lat']},{existing['lng']} vs {lat},{lng}"
            )
        if existing["borough"] != borough:
            raise ValueError(
                f"Park ID {park_id} borough inconsistency: "
                f"{existing['borough']} vs {borough}"
            )
        existing["aliases"].append(alias)
    return index


_PARK_ID_INDEX_CACHE: tuple[
    dict[str, dict[str, Any]], dict[str, dict[str, Any]]
] | None = None


def get_park_id_index(
    park_lookup: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return an authority-ID index cached for this immutable lookup object."""
    global _PARK_ID_INDEX_CACHE
    if _PARK_ID_INDEX_CACHE is None or _PARK_ID_INDEX_CACHE[0] is not park_lookup:
        _PARK_ID_INDEX_CACHE = (park_lookup, build_park_id_index(park_lookup))
    return _PARK_ID_INDEX_CACHE[1]


DPR_ABBREVIATION_MAP: dict[str, str] = {
    "plgd": "playground",
    "playgrd": "playground",
    "rec ctr": "recreation center",
    "rec center": "recreation center",
}


def _expand_dpr_abbreviations(text: str) -> str:
    expanded = text
    for abbreviation, replacement in DPR_ABBREVIATION_MAP.items():
        pattern = r"\b" + re.escape(abbreviation) + r"\b"
        expanded = re.sub(pattern, replacement, expanded, flags=re.IGNORECASE)
    return expanded


def _build_dpr_expanded_aliases(
    park_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Add only uniquely identified aliases created by DPR abbreviation expansion."""
    candidates: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for alias, entry in sorted(park_lookup.items()):
        if not isinstance(entry, dict) or not entry.get("park_id"):
            continue
        expanded = normalize_park_name(_expand_dpr_abbreviations(alias))
        if len(expanded) < 3 or expanded == alias:
            continue
        park_id = str(entry["park_id"]).strip().upper()
        candidates[expanded][park_id] = entry

    expanded_lookup = dict(park_lookup)
    added: set[str] = set()
    for alias, entries_by_id in sorted(candidates.items()):
        if alias not in expanded_lookup and len(entries_by_id) == 1:
            expanded_lookup[alias] = next(iter(entries_by_id.values()))
            added.add(alias)
    return expanded_lookup, added


_DPR_EXPANDED_ALIASES_CACHE: tuple[
    dict[str, dict[str, Any]], tuple[dict[str, dict[str, Any]], set[str]]
] | None = None


def _get_dpr_expanded_aliases(
    park_lookup: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Return uniquely expanded aliases cached for this immutable lookup object."""
    global _DPR_EXPANDED_ALIASES_CACHE
    if (
        _DPR_EXPANDED_ALIASES_CACHE is None
        or _DPR_EXPANDED_ALIASES_CACHE[0] is not park_lookup
    ):
        _DPR_EXPANDED_ALIASES_CACHE = (
            park_lookup,
            _build_dpr_expanded_aliases(park_lookup),
        )
    return _DPR_EXPANDED_ALIASES_CACHE[1]

DPR_INTERNAL_LANDMARK_MAP: dict[str, dict[str, Any]] = {
    "hippo playground": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "parkour park": {
        "target_park_name": "riverside park south",
        "target_authority_id": "M353",
        "borough": "M",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "parachute jump": {
        "target_park_name": "coney island beach and boardwalk",
        "target_authority_id": "B169",
        "borough": "B",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "audubon center": {
        "target_park_name": "prospect park",
        "target_authority_id": "B073",
        "borough": "B",
        "provenance": "Prospect Park Alliance + DPR cross-reference",
    },
    "jackie robinson park bandshell": {
        "target_park_name": "jackie robinson park",
        "target_authority_id": "M014",
        "borough": "M",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "102nd street field house": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "camel playground": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "riverbank playground": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "DPR Parks Properties enfh-gkve 2026-01-15",
    },
    "soldiers and sailors monument": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "NPS + DPR cross-reference",
    },
    "soldiers' and sailors' monument": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "NPS + DPR cross-reference",
    },
    "general grant national memorial": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "NPS + DPR cross-reference",
    },
    "grant's tomb": {
        "target_park_name": "riverside park",
        "target_authority_id": "M071",
        "borough": "M",
        "provenance": "NPS + DPR cross-reference",
    },
}

GENERIC_SUBFACILITIES = {
    "playground south",
    "play area",
    "gymnasium",
    "ballroom",
    "multi-use room",
    "open area",
    "lawn",
    "basketball courts",
}


def _exact_boundary_match(text: str, phrase: str) -> bool:
    pattern = r"\b" + re.escape(phrase) + r"\b"
    return bool(re.search(pattern, text, re.IGNORECASE))


def normalize_dpr_aliases(
    location_text: str | None,
    source_borough: Any = None,
    park_id_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Expand approved DPR aliases and resolve mapped internal landmarks."""
    if not location_text:
        return None

    text = _expand_dpr_abbreviations(_clean_text(location_text).casefold())

    for landmark, mapping in DPR_INTERNAL_LANDMARK_MAP.items():
        if not _exact_boundary_match(text, landmark):
            continue
        if park_id_index is None:
            return {
                "rejected": True,
                "rejection_reason": "park_id_index_unavailable",
                "landmark": landmark,
            }

        target_id = mapping["target_authority_id"]
        lookup_entry = park_id_index.get(target_id)
        if lookup_entry is None:
            return {
                "rejected": True,
                "rejection_reason": "authority_id_not_found_in_lookup",
                "target_authority_id": target_id,
            }

        lookup_borough = lookup_entry.get("borough")
        mapped_borough = canonical_borough(mapping.get("borough"))
        normalized_source = canonical_borough(source_borough)
        if mapped_borough != lookup_borough:
            return {
                "rejected": True,
                "rejection_reason": "mapping_lookup_borough_mismatch",
                "mapping_borough": mapped_borough,
                "lookup_borough": lookup_borough,
            }
        if normalized_source and lookup_borough and normalized_source != lookup_borough:
            return {
                "rejected": True,
                "rejection_reason": "borough_mismatch",
                "source_borough": source_borough,
                "lookup_borough": lookup_borough,
            }

        lat = lookup_entry.get("lat")
        lng = lookup_entry.get("lng")
        if not valid_nyc_point(lat, lng):
            return {
                "rejected": True,
                "rejection_reason": "invalid_coordinates",
                "latitude": lat,
                "longitude": lng,
            }

        return {
            "latitude": float(lat),
            "longitude": float(lng),
            "park_name": lookup_entry.get("park_name"),
            "park_borough": lookup_borough or normalized_source,
            "borough": lookup_borough or normalized_source,
            "authority_id": target_id,
            "landmark": landmark,
            "resolution_method": "dpr_internal_landmark_alias",
            "coordinate_source": "dpr_parks_properties_centroid",
            "coordinate_status": "approximate",
            "coordinate_precision": "park_level_anchor",
            "display_disposition": "approximate_marker",
            "promotion_allowed": False,
            "provenance": mapping["provenance"],
        }

    in_match = re.search(
        r"\bin\s+([\w\s'&.,-]+?)(?:\s*$|\s+at\s+|\s+near\s+|\s*[-:]\s*)",
        text,
        re.IGNORECASE,
    )
    if in_match:
        container = re.sub(r"['&,]+$", "", in_match.group(1)).strip()
        return {
            "normalized_text": text,
            "container_candidate": container,
            "resolution_method": "container_extraction",
        }
    return {"normalized_text": text}


def _ring_moment(ring: Any) -> PolygonMoment | None:
    if not isinstance(ring, list) or len(ring) < 3:
        return None
    points: list[tuple[float, float]] = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        x = _finite(point[0])
        y = _finite(point[1])
        if x is not None and y is not None:
            points.append((x, y))
    if len(points) < 3:
        return None
    if points[0] != points[-1]:
        points.append(points[0])
    cross_sum = 0.0
    cx_sum = 0.0
    cy_sum = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        cross = x1 * y2 - x2 * y1
        cross_sum += cross
        cx_sum += (x1 + x2) * cross
        cy_sum += (y1 + y2) * cross
    signed_area = cross_sum / 2.0
    if abs(signed_area) < 1e-15:
        return None
    return PolygonMoment(
        signed_area=signed_area,
        centroid_x=cx_sum / (6.0 * signed_area),
        centroid_y=cy_sum / (6.0 * signed_area),
    )


def _polygon_moment(polygon: Any) -> PolygonMoment | None:
    if not isinstance(polygon, list) or not polygon:
        return None
    ring_moments = [_ring_moment(ring) for ring in polygon]
    ring_moments = [moment for moment in ring_moments if moment is not None]
    if not ring_moments:
        return None
    shell = max(ring_moments, key=lambda moment: abs(moment.signed_area))
    weighted = [(abs(shell.signed_area), shell.centroid_x, shell.centroid_y)]
    for moment in ring_moments:
        if moment is shell:
            continue
        weighted.append((-abs(moment.signed_area), moment.centroid_x, moment.centroid_y))
    area = sum(item[0] for item in weighted)
    if area <= 1e-15:
        return None
    return PolygonMoment(
        signed_area=area,
        centroid_x=sum(a * x for a, x, _ in weighted) / area,
        centroid_y=sum(a * y for a, _, y in weighted) / area,
    )


def _geometry_moments(geometry: Any) -> list[PolygonMoment]:
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            return []
    if not isinstance(geometry, dict):
        return []
    geom_type = str(geometry.get("type") or "").casefold()
    coordinates = geometry.get("coordinates")
    if geom_type == "feature":
        return _geometry_moments(geometry.get("geometry"))
    if geom_type == "polygon":
        moment = _polygon_moment(coordinates)
        return [moment] if moment else []
    if geom_type == "multipolygon" and isinstance(coordinates, list):
        return [moment for polygon in coordinates if (moment := _polygon_moment(polygon))]
    if geom_type == "geometrycollection" and isinstance(geometry.get("geometries"), list):
        return [
            moment
            for child in geometry["geometries"]
            for moment in _geometry_moments(child)
        ]
    return []




def _geometry_polygons(geometry: Any) -> list[list[list[tuple[float, float]]]]:
    """Return normalized Polygon components as rings of (lng, lat) points."""
    if isinstance(geometry, str):
        try:
            geometry = json.loads(geometry)
        except json.JSONDecodeError:
            return []
    if not isinstance(geometry, dict):
        return []
    geom_type = str(geometry.get("type") or "").casefold()
    if geom_type == "feature":
        return _geometry_polygons(geometry.get("geometry"))
    if geom_type == "geometrycollection":
        return [
            polygon
            for child in geometry.get("geometries") or []
            for polygon in _geometry_polygons(child)
        ]
    coordinates = geometry.get("coordinates")
    raw_polygons = [coordinates] if geom_type == "polygon" else coordinates if geom_type == "multipolygon" else []
    polygons: list[list[list[tuple[float, float]]]] = []
    if not isinstance(raw_polygons, list):
        return polygons
    for raw_polygon in raw_polygons:
        if not isinstance(raw_polygon, list):
            continue
        rings: list[list[tuple[float, float]]] = []
        for raw_ring in raw_polygon:
            if not isinstance(raw_ring, list):
                continue
            ring: list[tuple[float, float]] = []
            for raw_point in raw_ring:
                if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
                    continue
                x = _finite(raw_point[0])
                y = _finite(raw_point[1])
                if x is not None and y is not None:
                    ring.append((x, y))
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(ring[0])
                rings.append(ring)
        if rings:
            shell_index = max(range(len(rings)), key=lambda index: abs(_ring_moment(rings[index]).signed_area) if _ring_moment(rings[index]) else 0.0)
            shell = rings[shell_index]
            holes = [ring for index, ring in enumerate(rings) if index != shell_index]
            polygons.append([shell, *holes])
    return polygons


def _point_on_segment(x: float, y: float, a: tuple[float, float], b: tuple[float, float]) -> bool:
    cross = (x - a[0]) * (b[1] - a[1]) - (y - a[1]) * (b[0] - a[0])
    if abs(cross) > 1e-12:
        return False
    return min(a[0], b[0]) - 1e-12 <= x <= max(a[0], b[0]) + 1e-12 and min(a[1], b[1]) - 1e-12 <= y <= max(a[1], b[1]) + 1e-12


def _point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    for a, b in zip(ring, ring[1:]):
        if _point_on_segment(x, y, a, b):
            return True
        if (a[1] > y) != (b[1] > y):
            crossing_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if crossing_x > x:
                inside = not inside
    return inside


def _point_in_polygon(x: float, y: float, polygon: list[list[tuple[float, float]]]) -> bool:
    return bool(polygon and _point_in_ring(x, y, polygon[0]) and not any(_point_in_ring(x, y, hole) for hole in polygon[1:]))


def _geometry_contains_point(polygons: list[list[list[tuple[float, float]]]], x: float, y: float) -> bool:
    return any(_point_in_polygon(x, y, polygon) for polygon in polygons)


def _polygon_surface_point(polygon: list[list[tuple[float, float]]]) -> tuple[float, float] | None:
    """Deterministic Shapely-style representative point using horizontal scanlines."""
    if not polygon or not polygon[0]:
        return None
    shell = polygon[0]
    ys = [point[1] for point in shell[:-1]]
    if not ys:
        return None
    y_min, y_max = min(ys), max(ys)
    moment = _polygon_moment(polygon)
    candidate_ys = []
    if moment:
        candidate_ys.append(moment.centroid_y)
    candidate_ys.extend(y_min + (y_max - y_min) * fraction for fraction in (0.5, 0.375, 0.625, 0.25, 0.75, 0.125, 0.875))
    best: tuple[float, float, float] | None = None
    for y in candidate_ys:
        intersections: list[float] = []
        for ring in polygon:
            for a, b in zip(ring, ring[1:]):
                if abs(a[1] - b[1]) < 1e-15:
                    continue
                low, high = sorted((a[1], b[1]))
                if not (low <= y < high):
                    continue
                intersections.append(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
        intersections.sort()
        for left, right in zip(intersections[0::2], intersections[1::2]):
            if right - left <= 1e-12:
                continue
            x = (left + right) / 2.0
            if _point_in_polygon(x, y, polygon):
                width = right - left
                if best is None or width > best[0]:
                    best = (width, x, y)
    if best:
        return best[1], best[2]
    for a, b in zip(shell, shell[1:]):
        x, y = (a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0
        if _point_in_polygon(x, y, polygon):
            return x, y
    return None


def representative_point_from_geometry(geometry: Any) -> tuple[float, float, str] | None:
    """Return (lat, lng, method), falling back to an interior point when needed."""
    moments = _geometry_moments(geometry)
    polygons = _geometry_polygons(geometry)
    if not moments or not polygons:
        return None
    total_area = sum(abs(moment.signed_area) for moment in moments)
    if total_area <= 1e-15:
        return None
    lng = sum(abs(moment.signed_area) * moment.centroid_x for moment in moments) / total_area
    lat = sum(abs(moment.signed_area) * moment.centroid_y for moment in moments) / total_area
    if _valid_nyc_point(lat, lng) and _geometry_contains_point(polygons, lng, lat):
        return lat, lng, "centroid"
    ranked = sorted(
        polygons,
        key=lambda polygon: abs(_polygon_moment(polygon).signed_area) if _polygon_moment(polygon) else 0.0,
        reverse=True,
    )
    for polygon in ranked:
        point = _polygon_surface_point(polygon)
        if point and _valid_nyc_point(point[1], point[0]):
            return point[1], point[0], "point_on_surface"
    return None

def centroid_from_geometry(geometry: Any) -> tuple[float, float] | None:
    """Backward-compatible park anchor: centroid when inside, else point-on-surface."""
    representative = representative_point_from_geometry(geometry)
    return (representative[0], representative[1]) if representative else None


def _first_value(row: dict[str, Any], fields: Iterable[str]) -> str | None:
    lowered = {str(key).casefold(): key for key in row}
    for field in fields:
        key = lowered.get(field.casefold())
        if key is not None:
            text = _clean_text(row.get(key))
            if text:
                return text
    return None


def _all_values(row: dict[str, Any], fields: Iterable[str]) -> list[str]:
    lowered = {str(key).casefold(): key for key in row}
    values: list[str] = []
    for field in fields:
        key = lowered.get(field.casefold())
        if key is not None:
            text = _clean_text(row.get(key))
            if text and text.casefold() not in {item.casefold() for item in values}:
                values.append(text)
    return values


def _geometry_value(row: dict[str, Any]) -> Any:
    lowered = {str(key).casefold(): key for key in row}
    for field in _GEOMETRY_FIELDS:
        key = lowered.get(field.casefold())
        if key is not None and row.get(key) not in (None, ""):
            return row.get(key)
    if row.get("type") in {"Feature", "Polygon", "MultiPolygon", "GeometryCollection"}:
        return row
    return None


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        if payload.get("type") == "FeatureCollection" and isinstance(payload.get("features"), list):
            rows: list[dict[str, Any]] = []
            for feature in payload["features"]:
                if not isinstance(feature, dict):
                    continue
                properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
                rows.append({**properties, "geometry": feature.get("geometry")})
            return rows
        for key in ("data", "rows", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                normalized: list[dict[str, Any]] = []
                for item in value:
                    if isinstance(item, dict) and isinstance(item.get("fields"), dict):
                        normalized.append(item["fields"])
                    elif isinstance(item, dict):
                        normalized.append(item)
                return normalized
    return []


def load_parks_properties(source: str | Path = DATASET_URL, *, timeout: int = 60) -> list[dict[str, Any]]:
    if isinstance(source, Path) or not str(source).startswith(("http://", "https://")):
        path = Path(source)
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        request = Request(str(source), headers={"User-Agent": "NYCInFocus-SHADOW2/1.0"})
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    rows = _rows_from_payload(payload)
    if not rows:
        raise ValueError("Parks Properties source contained no object rows")
    return rows


def build_park_lookup(rows: Iterable[dict[str, Any]]) -> BuildResult:
    grouped: dict[str, dict[str, Any]] = {}
    source_rows = 0
    geometry_rows = 0
    invalid_geometry_rows = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        source_rows += 1
        park_id = _first_value(row, _ID_FIELDS)
        names = _all_values(row, _NAME_FIELDS)
        geometry = _geometry_value(row)
        moments = _geometry_moments(geometry)
        if not park_id or not names or not moments:
            if geometry not in (None, "") and not moments:
                invalid_geometry_rows += 1
            continue
        geometry_rows += 1
        group = grouped.setdefault(
            park_id,
            {
                "park_id": park_id,
                "names": [],
                "boroughs": set(),
                "moments": [],
                "polygons": [],
            },
        )
        for name in names:
            if name.casefold() not in {item.casefold() for item in group["names"]}:
                group["names"].append(name)
        borough = _first_value(row, _BOROUGH_FIELDS)
        if borough:
            group["boroughs"].add(borough)
        group["moments"].extend(moments)
        group["polygons"].extend(_geometry_polygons(geometry))

    aliases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for park_id in sorted(grouped):
        group = grouped[park_id]
        moments = group["moments"]
        polygons = group["polygons"]
        total_area = sum(abs(moment.signed_area) for moment in moments)
        if total_area <= 1e-15 or not polygons:
            continue
        lng = sum(abs(moment.signed_area) * moment.centroid_x for moment in moments) / total_area
        lat = sum(abs(moment.signed_area) * moment.centroid_y for moment in moments) / total_area
        anchor_method = "centroid"
        if not _valid_nyc_point(lat, lng) or not _geometry_contains_point(polygons, lng, lat):
            anchor_method = "point_on_surface"
            ranked = sorted(
                polygons,
                key=lambda polygon: abs(_polygon_moment(polygon).signed_area) if _polygon_moment(polygon) else 0.0,
                reverse=True,
            )
            surface = next((point for polygon in ranked if (point := _polygon_surface_point(polygon))), None)
            if not surface:
                continue
            lng, lat = surface
        if not _valid_nyc_point(lat, lng):
            continue
        names = sorted(group["names"], key=lambda value: (value.casefold(), value))
        canonical_name = names[0]
        boroughs = sorted(group["boroughs"], key=str.casefold)
        entry = {
            "lat": round(lat, 7),
            "lng": round(lng, 7),
            "park_id": park_id,
            "park_name": canonical_name,
            "borough": boroughs[0] if len(boroughs) == 1 else None,
            "anchor_method": anchor_method,
            "source_dataset": DATASET_ID,
        }
        for name in names:
            normalized = normalize_park_name(name)
            if len(normalized) >= 3:
                aliases[normalized].append(entry)

    lookup: dict[str, dict[str, Any]] = {}
    ambiguous: list[str] = []
    for alias, candidates in sorted(aliases.items()):
        unique_by_id = {candidate["park_id"]: candidate for candidate in candidates}
        if len(unique_by_id) != 1:
            ambiguous.append(alias)
            continue
        lookup[alias] = next(iter(unique_by_id.values())).copy()

    return BuildResult(
        lookup=lookup,
        source_rows=source_rows,
        geometry_rows=geometry_rows,
        park_groups=len(grouped),
        aliases_written=len(lookup),
        ambiguous_aliases=tuple(ambiguous),
        invalid_geometry_rows=invalid_geometry_rows,
    )


def write_park_lookup(
    rows: Iterable[dict[str, Any]],
    output_path: Path = DEFAULT_LOOKUP_PATH,
    ambiguous_output_path: Path | None = None,
) -> BuildResult:
    result = build_park_lookup(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.lookup, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if ambiguous_output_path is not None:
        ambiguous_output_path.parent.mkdir(parents=True, exist_ok=True)
        ambiguous_output_path.write_text(
            json.dumps(
                {
                    "source_dataset": DATASET_ID,
                    "ambiguous_aliases": list(result.ambiguous_aliases),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
    return result


def load_park_lookup(path: Path = DEFAULT_LOOKUP_PATH) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(key): value
        for key, value in payload.items()
        if isinstance(value, dict)
        and _valid_nyc_point(value.get("lat"), value.get("lng"))
        and value.get("park_id")
    }


def find_park_centroid(
    location_text: str,
    *,
    lookup: dict[str, dict[str, Any]] | None = None,
    lookup_path: Path = DEFAULT_LOOKUP_PATH,
    source_borough: Any = None,
) -> dict[str, Any] | None:
    """Return a unique authoritative park centroid or ``None``.

    Matching is exact after deterministic normalization. Suffix differences such
    as ``Park`` versus ``Playground`` are normalized away; broad edit-distance
    guessing is deliberately excluded. Multiple recognized park IDs fail closed.
    """
    table = lookup if lookup is not None else load_park_lookup(lookup_path)
    if not table:
        return None

    # PATCH 02 v4.1 integration hook. Authority-ID lookup remains fail-closed;
    # rejected alias evidence falls through to the existing exact-match logic.
    park_id_index = get_park_id_index(table)
    alias_result = normalize_dpr_aliases(location_text, source_borough, park_id_index)
    if alias_result and alias_result.get("latitude") is not None:
        landmark = str(alias_result["landmark"])
        return {
            "lat": alias_result["latitude"],
            "lng": alias_result["longitude"],
            "park_id": alias_result["authority_id"],
            "park_name": alias_result.get("park_name"),
            "borough": alias_result.get("borough"),
            "source_dataset": DATASET_ID,
            "query_name": landmark,
            "query_names": [landmark],
            "normalized_query": normalize_park_name(landmark),
            "match_type": alias_result["resolution_method"],
            "provenance": alias_result["provenance"],
            "promotion_allowed": False,
        }

    normalized_location = (
        str(alias_result.get("normalized_text"))
        if alias_result and alias_result.get("normalized_text")
        else location_text
    )
    match_table, abbreviation_aliases = _get_dpr_expanded_aliases(table)
    candidates = extract_park_names(normalized_location)
    matched: list[tuple[str, str, dict[str, Any]]] = []
    for candidate in candidates:
        normalized = normalize_park_name(candidate)
        if len(normalized) < 3:
            continue
        entry = match_table.get(normalized)
        if entry:
            matched.append((candidate, normalized, entry))
    unique_ids = {str(entry.get("park_id")) for _, _, entry in matched if entry.get("park_id")}
    if len(unique_ids) != 1:
        return None
    candidate, normalized, entry = matched[-1]
    result = dict(entry)
    result.update(
        {
            "query_name": candidate,
            "query_names": [item[0] for item in matched],
            "normalized_query": normalized,
            "match_type": (
                "dpr_abbreviation_alias"
                if normalized in abbreviation_aliases
                else "unique_normalized_name"
            ),
        }
    )
    return result


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DATASET_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_LOOKUP_PATH)
    args = parser.parse_args(argv)
    rows = load_parks_properties(args.source)
    result = write_park_lookup(rows, args.output)
    print(
        json.dumps(
            {
                "dataset_id": DATASET_ID,
                "source_rows": result.source_rows,
                "geometry_rows": result.geometry_rows,
                "park_groups": result.park_groups,
                "aliases_written": result.aliases_written,
                "ambiguous_aliases": len(result.ambiguous_aliases),
                "invalid_geometry_rows": result.invalid_geometry_rows,
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0 if result.aliases_written else 1


if __name__ == "__main__":
    raise SystemExit(_main())
