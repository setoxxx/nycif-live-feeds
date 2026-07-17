"""GeoJSON polygon helpers (stdlib only) for park boundary checks."""

from __future__ import annotations

from typing import Any, Iterable

try:
    from scripts.coverage_gap_utils import valid_nyc_lat_lng
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import valid_nyc_lat_lng
    from gps_identity import normalize_text_legacy


def _ring_lng_lat_pairs(ring: Any) -> list[tuple[float, float]]:
    if not isinstance(ring, list):
        return []
    pairs: list[tuple[float, float]] = []
    for pos in ring:
        if not isinstance(pos, (list, tuple)) or len(pos) < 2:
            continue
        try:
            lng = float(pos[0])
            lat = float(pos[1])
        except (TypeError, ValueError):
            continue
        pairs.append((lng, lat))
    return pairs


def point_in_ring(lng: float, lat: float, ring: Any) -> bool:
    """Ray-casting point-in-polygon for one GeoJSON linear ring ([lng, lat] pairs)."""
    points = _ring_lng_lat_pairs(ring)
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_polygon_geometry(lng: float, lat: float, geometry: dict[str, Any]) -> bool:
    geom_type = str(geometry.get("type") or "")
    coords = geometry.get("coordinates")
    if geom_type == "Polygon" and isinstance(coords, list):
        if not coords:
            return False
        if not point_in_ring(lng, lat, coords[0]):
            return False
        for hole in coords[1:]:
            if point_in_ring(lng, lat, hole):
                return False
        return True
    if geom_type == "MultiPolygon" and isinstance(coords, list):
        for polygon in coords:
            if isinstance(polygon, list) and polygon:
                if point_in_ring(lng, lat, polygon[0]):
                    in_hole = any(point_in_ring(lng, lat, hole) for hole in polygon[1:])
                    if not in_hole:
                        return True
        return False
    return False


def ring_centroid(ring: Any) -> tuple[float, float] | None:
    points = _ring_lng_lat_pairs(ring)
    if len(points) < 3:
        return None
    area = 0.0
    cx = 0.0
    cy = 0.0
    for i, (x0, y0) in enumerate(points):
        x1, y1 = points[(i + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(area) < 1e-15:
        lng = sum(p[0] for p in points) / len(points)
        lat = sum(p[1] for p in points) / len(points)
        return lat, lng
    area *= 0.5
    cx /= 6.0 * area
    cy /= 6.0 * area
    return cy, cx


def geometry_centroid(geometry: dict[str, Any]) -> tuple[float, float] | None:
    geom_type = str(geometry.get("type") or "")
    coords = geometry.get("coordinates")
    if geom_type == "Polygon" and isinstance(coords, list) and coords:
        return ring_centroid(coords[0])
    if geom_type == "MultiPolygon" and isinstance(coords, list) and coords:
        first = coords[0]
        if isinstance(first, list) and first:
            return ring_centroid(first[0])
    return None


def normalize_park_name(name: Any) -> str:
    return normalize_text_legacy(str(name or ""))


def build_parks_properties_name_index(
    properties: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in properties:
        if not isinstance(row, dict):
            continue
        for key_field in ("signname", "name311", "park_name", "name"):
            norm = normalize_park_name(row.get(key_field))
            if norm:
                index.setdefault(norm, []).append(row)
    return index


def find_park_property_row(
    park_name: str,
    borough: Any,
    name_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    target = normalize_park_name(park_name)
    if not target:
        return None
    boro_key = normalize_text_legacy(str(borough or ""))
    candidates = name_index.get(target, [])
    if not candidates:
        for norm, rows in name_index.items():
            if target in norm or norm in target:
                candidates.extend(rows)
    if not candidates:
        return None
    if boro_key:
        for row in candidates:
            row_boro = normalize_text_legacy(str(row.get("borough_label") or row.get("borough") or ""))
            if row_boro and (boro_key in row_boro or row_boro in boro_key):
                return row
    return candidates[0]


def snap_to_park_interior(
    lat: float,
    lng: float,
    park_name: str,
    borough: Any,
    name_index: dict[str, list[dict[str, Any]]],
) -> tuple[float, float, str] | None:
    """If (lat,lng) is outside the named park polygon, return park-interior centroid."""
    row = find_park_property_row(park_name, borough, name_index)
    if not row:
        return None
    geometry = row.get("geometry") or row.get("multipolygon")
    if not isinstance(geometry, dict):
        return None
    if point_in_polygon_geometry(lng, lat, geometry):
        return None
    centroid = row.get("centroid_lat"), row.get("centroid_lng")
    if centroid[0] is not None and centroid[1] is not None:
        try:
            c_lat = float(centroid[0])
            c_lng = float(centroid[1])
        except (TypeError, ValueError):
            c_lat = c_lng = None  # type: ignore[assignment]
        else:
            if valid_nyc_lat_lng(c_lat, c_lng):
                label = str(row.get("signname") or row.get("name311") or park_name)
                return c_lat, c_lng, label
    computed = geometry_centroid(geometry)
    if computed and valid_nyc_lat_lng(computed[0], computed[1]):
        label = str(row.get("signname") or row.get("name311") or park_name)
        return computed[0], computed[1], label
    return None
