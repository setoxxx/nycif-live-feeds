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
DATASET_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json?$limit=50000"
DEFAULT_LOOKUP_PATH = Path(__file__).resolve().parents[2] / "data" / "park_centroids.json"

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


def centroid_from_geometry(geometry: Any) -> tuple[float, float] | None:
    moments = _geometry_moments(geometry)
    if not moments:
        return None
    total_area = sum(abs(moment.signed_area) for moment in moments)
    if total_area <= 1e-15:
        return None
    lng = sum(abs(moment.signed_area) * moment.centroid_x for moment in moments) / total_area
    lat = sum(abs(moment.signed_area) * moment.centroid_y for moment in moments) / total_area
    return (lat, lng) if _valid_nyc_point(lat, lng) else None


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
            },
        )
        for name in names:
            if name.casefold() not in {item.casefold() for item in group["names"]}:
                group["names"].append(name)
        borough = _first_value(row, _BOROUGH_FIELDS)
        if borough:
            group["boroughs"].add(borough)
        group["moments"].extend(moments)

    aliases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for park_id, group in grouped.items():
        moments = group["moments"]
        total_area = sum(abs(moment.signed_area) for moment in moments)
        if total_area <= 1e-15:
            continue
        lng = sum(abs(moment.signed_area) * moment.centroid_x for moment in moments) / total_area
        lat = sum(abs(moment.signed_area) * moment.centroid_y for moment in moments) / total_area
        if not _valid_nyc_point(lat, lng):
            continue
        names = group["names"]
        canonical_name = names[0]
        entry = {
            "lat": round(lat, 7),
            "lng": round(lng, 7),
            "park_id": park_id,
            "park_name": canonical_name,
            "borough": next(iter(group["boroughs"])) if len(group["boroughs"]) == 1 else None,
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


def write_park_lookup(rows: Iterable[dict[str, Any]], output_path: Path = DEFAULT_LOOKUP_PATH) -> BuildResult:
    result = build_park_lookup(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.lookup, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
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
) -> dict[str, Any] | None:
    """Return a unique authoritative park centroid or ``None``.

    Matching is exact after deterministic normalization. Suffix differences such
    as ``Park`` versus ``Playground`` are normalized away; broad edit-distance
    guessing is deliberately excluded.
    """
    table = lookup if lookup is not None else load_park_lookup(lookup_path)
    if not table:
        return None
    candidates = extract_park_names(location_text)
    for candidate in reversed(candidates):
        normalized = normalize_park_name(candidate)
        if len(normalized) < 3:
            continue
        entry = table.get(normalized)
        if not entry:
            continue
        result = dict(entry)
        result.update(
            {
                "query_name": candidate,
                "normalized_query": normalized,
                "match_type": "unique_normalized_name",
            }
        )
        return result
    return None


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
