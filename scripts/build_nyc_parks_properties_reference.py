#!/usr/bin/env python3
"""Build NYC Parks Properties polygon reference from Open Data (enfh-gkve).

Staging artifact for point-in-polygon park interior correction. Does not modify
location_cache.json or public map feeds.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.geojson_polygon_utils import geometry_centroid, normalize_park_name
except ModuleNotFoundError:  # pragma: no cover
    from geojson_polygon_utils import geometry_centroid, normalize_park_name

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "nyc_parks_properties_reference.json"
REPORT_PATH = DATA_DIR / "reports" / "nyc_parks_properties_reference_report.json"
SODA_URL = "https://data.cityofnewyork.us/resource/enfh-gkve.json"
PAGE_LIMIT = 500

BOROUGH_CODE_MAP = {
    "M": "Manhattan",
    "B": "Brooklyn",
    "Q": "Queens",
    "X": "Bronx",
    "R": "Staten Island",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def fetch_page(offset: int) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "$limit": PAGE_LIMIT,
            "$offset": offset,
            "$order": "objectid",
            "$select": "signname,name311,borough,multipolygon,objectid,gispropnum,subcategory,typecategory",
        }
    )
    url = f"{SODA_URL}?{params}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "nycif-live-feeds/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def borough_label(code: Any) -> str:
    key = str(code or "").strip().upper()
    return BOROUGH_CODE_MAP.get(key, str(code or "").strip())


def simplify_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    geometry = raw.get("multipolygon")
    if not isinstance(geometry, dict):
        return None
    signname = str(raw.get("signname") or raw.get("name311") or "").strip()
    if not signname:
        return None
    centroid = geometry_centroid(geometry)
    out: dict[str, Any] = {
        "objectid": raw.get("objectid"),
        "gispropnum": raw.get("gispropnum"),
        "signname": signname,
        "name311": str(raw.get("name311") or "").strip() or signname,
        "park_name": signname,
        "borough": str(raw.get("borough") or "").strip(),
        "borough_label": borough_label(raw.get("borough")),
        "park_key": normalize_park_name(signname),
        "geometry": geometry,
        "subcategory": raw.get("subcategory"),
        "typecategory": raw.get("typecategory"),
    }
    if centroid:
        out["centroid_lat"] = round(centroid[0], 7)
        out["centroid_lng"] = round(centroid[1], 7)
    return out


def fetch_all_rows() -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    offset = 0
    while True:
        try:
            page = fetch_page(offset)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"fetch offset {offset}: {exc}")
            break
        if not page:
            break
        for raw in page:
            simplified = simplify_row(raw)
            if simplified:
                rows.append(simplified)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
    return rows, errors


def run(*, use_existing_on_failure: bool = True) -> int:
    errors: list[str] = []
    rows, fetch_errors = fetch_all_rows()
    errors.extend(fetch_errors)
    source = "nyc_open_data_enfh_gkve"
    if not rows and use_existing_on_failure and OUTPUT_PATH.exists():
        existing = load_json(OUTPUT_PATH, {})
        rows = existing.get("properties", []) if isinstance(existing, dict) else []
        source = "committed_snapshot_fallback"
        errors.append("Used committed nyc_parks_properties_reference.json because live fetch failed or returned no rows.")

    with_centroid = sum(1 for row in rows if row.get("centroid_lat") is not None)
    payload = {
        "artifact_type": "nyc_parks_properties_reference",
        "generated_at_utc": utc_now_iso(),
        "source_dataset": "enfh-gkve",
        "source": source,
        "property_count": len(rows),
        "properties": rows,
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "promotion_allowed": False,
        },
    }
    save_json(OUTPUT_PATH, payload)
    report = {
        "generated_at_utc": payload["generated_at_utc"],
        "artifact_type": "nyc_parks_properties_reference_report",
        "source_dataset": "enfh-gkve",
        "property_count": len(rows),
        "properties_with_centroid": with_centroid,
        "fetch_errors": errors,
        "passed": len(rows) > 0,
        "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
        "public_map_modified": False,
        "location_cache_modified": False,
        "promotion_allowed": False,
    }
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
