"""Deterministic authoritative facility lookup construction and loading."""
from __future__ import annotations

import html
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen

NYC_BOUNDS = (40.4774, 40.9176, -74.2591, -73.7004)
SPACE_RE = re.compile(r"\s+")
BOROUGH_ALIASES = {
    "1": "Manhattan", "m": "Manhattan", "mn": "Manhattan", "manhattan": "Manhattan", "new york": "Manhattan",
    "2": "Bronx", "x": "Bronx", "bx": "Bronx", "bronx": "Bronx", "the bronx": "Bronx",
    "3": "Brooklyn", "b": "Brooklyn", "bk": "Brooklyn", "brooklyn": "Brooklyn",
    "4": "Queens", "q": "Queens", "qn": "Queens", "queens": "Queens",
    "5": "Staten Island", "r": "Staten Island", "si": "Staten Island", "staten island": "Staten Island",
}


def clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", html.unescape(str(value or "")).strip())


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value)).encode("ascii", "ignore").decode()
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"['’]", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return SPACE_RE.sub(" ", text).strip()


def canonical_borough(value: Any) -> str | None:
    if isinstance(value, (list, tuple, set)):
        matches = {canonical_borough(item) for item in value}
        matches.discard(None)
        return next(iter(matches)) if len(matches) == 1 else None
    return BOROUGH_ALIASES.get(normalize_name(value))


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_nyc_point(lat: Any, lng: Any) -> bool:
    lat_f, lng_f = finite_number(lat), finite_number(lng)
    return bool(lat_f is not None and lng_f is not None and NYC_BOUNDS[0] <= lat_f <= NYC_BOUNDS[1] and NYC_BOUNDS[2] <= lng_f <= NYC_BOUNDS[3] and not (abs(lat_f) < 1e-12 and abs(lng_f) < 1e-12))


def point_from_row(row: dict[str, Any], geometry_fields: Iterable[str] = ()) -> tuple[float, float] | None:
    for lat_key, lng_key in (("latitude", "longitude"), ("lat", "lng")):
        if valid_nyc_point(row.get(lat_key), row.get(lng_key)):
            return round(float(row[lat_key]), 7), round(float(row[lng_key]), 7)
    for field in ("the_geom", "point", "geometry", *geometry_fields):
        geometry = row.get(field)
        if isinstance(geometry, str):
            try:
                geometry = json.loads(geometry)
            except json.JSONDecodeError:
                continue
        if not isinstance(geometry, dict):
            continue
        if str(geometry.get("type", "")).casefold() == "point":
            coordinates = geometry.get("coordinates")
            if isinstance(coordinates, list) and len(coordinates) >= 2 and valid_nyc_point(coordinates[1], coordinates[0]):
                return round(float(coordinates[1]), 7), round(float(coordinates[0]), 7)
        try:
            from nycif.normalize.park_geometry import representative_point_from_geometry
            point = representative_point_from_geometry(geometry)
        except Exception:
            point = None
        if point and valid_nyc_point(point[0], point[1]):
            return round(float(point[0]), 7), round(float(point[1]), 7)
    return None


def fetch_json(url: str, *, timeout: int = 120) -> Any:
    request = Request(url, headers={"User-Agent": "NYCInFocus-authoritative-facilities/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def socrata_rows(dataset_id: str, *, order: str | None = None, limit: int = 50000) -> list[dict[str, Any]]:
    query = f"?$limit={limit}"
    if order:
        from urllib.parse import quote
        query += "&$order=" + quote(order, safe=",")
    payload = fetch_json(f"https://data.cityofnewyork.us/resource/{dataset_id}.json{query}")
    if not isinstance(payload, list):
        raise ValueError(f"{dataset_id} returned non-list payload")
    return [row for row in payload if isinstance(row, dict)]


def build_lookup(rows: Iterable[dict[str, Any]], *, dataset_id: str, name_fields: tuple[str, ...], id_fields: tuple[str, ...], borough_fields: tuple[str, ...], facility_type: str, geometry_fields: tuple[str, ...] = (), alias_expander=None, row_filter=None) -> dict[str, Any]:
    source_rows = valid_geometry_rows = 0
    entries: list[tuple[dict[str, Any], list[str]]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_rows += 1
        if row_filter and not row_filter(row):
            continue
        names = [clean_text(row.get(field)) for field in name_fields if clean_text(row.get(field))]
        if not names:
            continue
        point = point_from_row(row, geometry_fields)
        if not point:
            continue
        valid_geometry_rows += 1
        authority_id = next((clean_text(row.get(field)) for field in id_fields if clean_text(row.get(field))), "")
        borough = next((canonical_borough(row.get(field)) for field in borough_fields if canonical_borough(row.get(field))), None)
        aliases = set(names)
        if alias_expander:
            for name in list(names):
                aliases.update(alias_expander(name, row) or [])
        entry = {"authority_id": authority_id or f"{dataset_id}:{source_rows}", "facility_name": names[0], "facility_type": facility_type, "borough": borough, "lat": point[0], "lng": point[1], "source_dataset": dataset_id}
        entries.append((entry, sorted({normalize_name(alias) for alias in aliases if len(normalize_name(alias)) >= 3})))
    alias_candidates: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for entry, aliases in entries:
        for alias in aliases:
            alias_candidates[alias][entry["authority_id"]] = entry
    aliases: dict[str, dict[str, Any]] = {}
    ambiguous: list[str] = []
    for alias in sorted(alias_candidates):
        candidates = list(alias_candidates[alias].values())
        if len(candidates) != 1:
            ambiguous.append(alias)
        else:
            aliases[alias] = candidates[0]
    return {"metadata": {"source_dataset": dataset_id, "source_rows": source_rows, "valid_geometry_rows": valid_geometry_rows, "unique_facilities": len({entry["authority_id"] for entry, _ in entries}), "aliases_written": len(aliases), "ambiguous_aliases_omitted": len(ambiguous), "float_precision": 7, "promotion_allowed": False}, "aliases": aliases, "ambiguous_aliases": ambiguous}


def write_lookup(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_lookup(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"metadata": {}, "aliases": {}, "ambiguous_aliases": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("aliases"), dict):
        return {"metadata": {}, "aliases": {}, "ambiguous_aliases": []}
    return payload
