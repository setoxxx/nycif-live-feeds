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


GENERIC_PARK_NAME_TOKENS = frozenset(
    {
        "park",
        "recreation",
        "center",
        "centre",
        "playground",
        "playground",
        "field",
        "fields",
        "beach",
        "boardwalk",
        "and",
        "the",
        "at",
        "in",
        "of",
    }
)


def _significant_park_tokens(norm: str) -> set[str]:
    return {token for token in norm.split() if token and token not in GENERIC_PARK_NAME_TOKENS and len(token) >= 3}


def _is_weak_park_norm(norm: str) -> bool:
    tokens = [token for token in norm.split() if token]
    return not tokens or tokens == ["park"] or all(token in GENERIC_PARK_NAME_TOKENS for token in tokens)


def _park_name_aliases(park_name: str) -> list[str]:
    target = normalize_park_name(park_name)
    aliases = [target]
    for suffix in (" recreation center", " play center", " recreation building"):
        if target.endswith(suffix):
            aliases.append(target[: -len(suffix)].strip())
    if " - " in target:
        aliases.append(target.split(" - ", 1)[0].strip())
    deduped: list[str] = []
    for alias in aliases:
        if alias and alias not in deduped:
            deduped.append(alias)
    return deduped


def _borough_match_keys(borough: Any) -> set[str]:
    keys = {normalize_text_legacy(str(borough or ""))}
    try:
        from scripts.schema_v1_common import borough_label
    except ModuleNotFoundError:  # pragma: no cover
        from schema_v1_common import borough_label
    label = borough_label(borough)
    if label:
        keys.add(normalize_text_legacy(label))
    return {key for key in keys if key}


def _park_match_score(alias: str, norm: str) -> int:
    if alias == norm:
        return 100
    if len(alias) >= 8 and len(norm) >= 6 and (alias in norm or norm in alias):
        return 70
    overlap = _significant_park_tokens(alias) & _significant_park_tokens(norm)
    if not overlap:
        return 0
    if len(overlap) >= 2:
        return 50 + len(overlap) * 5
    token = next(iter(overlap))
    if len(token) >= 5 and len(_significant_park_tokens(alias)) <= 2:
        return 35
    return 0


def find_park_property_row(
    park_name: str,
    borough: Any,
    name_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    boro_keys = _borough_match_keys(borough)
    scored: list[tuple[int, dict[str, Any]]] = []
    seen_ids: set[str] = set()

    def add_scored(score: int, rows: Iterable[dict[str, Any]]) -> None:
        for row in rows:
            row_id = str(row.get("gispropnum") or row.get("signname") or row.get("name311") or id(row))
            if row_id in seen_ids:
                continue
            seen_ids.add(row_id)
            scored.append((score, row))

    for alias in _park_name_aliases(park_name):
        if alias in name_index:
            add_scored(100, name_index[alias])
        target_tokens = _significant_park_tokens(alias)
        for norm, rows in name_index.items():
            if _is_weak_park_norm(norm):
                continue
            score = _park_match_score(alias, norm)
            if score:
                add_scored(score, rows)

    if not scored:
        return None
    if boro_keys:
        boro_scored = [
            (score, row)
            for score, row in scored
            if normalize_text_legacy(str(row.get("borough_label") or row.get("borough") or ""))
            in boro_keys
            or any(
                key in normalize_text_legacy(str(row.get("borough_label") or row.get("borough") or ""))
                or normalize_text_legacy(str(row.get("borough_label") or row.get("borough") or "")) in key
                for key in boro_keys
            )
        ]
        if boro_scored:
            scored = boro_scored
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


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
