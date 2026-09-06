"""Shared helpers for Culture community staging (fail closed, no publication)."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import NYC, valid_nyc_coords  # noqa: E402

DATA_DIR = ROOT / "data" / "culture"
STAGING_DIR = DATA_DIR / "staging"
REPORT_DIR = DATA_DIR / "reports"
TEMPLATE_CSV = DATA_DIR / "curated_storefronts.template.csv"
HOWARD_CSV = DATA_DIR / "curated_storefronts.csv"

SODA_BASE = "https://data.cityofnewyork.us/resource"
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NYCIF-culture-community/0.1 (+https://github.com/setoxxx/nycif-live-feeds)",
}

PLACE_KINDS = (
    "storefront",
    "worship",
    "civic_nypd",
    "civic_fdny",
    "shelter",
    "pet_care",
    "resource",
)

CALENDAR_KINDS = (
    "worship_service",
    "cultural_festival",
    "aspca_van",
    "community_clinic",
    "other",
)

RESOURCE_KINDS = (
    "immigration_legal",
    "health",
    "food_pantry",
    "community_faith",
    "know_your_rights",
    "multilingual_city",
)

NYPD_DATASET = "y76i-bdw7"
FDNY_DATASET = "hc8x-tcnd"
SHELTER_DATASET = "g9nt-57fp"

ADDRESS_COLUMN_HINTS = (
    "address",
    "facilityaddress",
    "facility_address",
    "street_address",
    "location_1",
    "house_number",
    "street",
)
LAT_COLUMN_HINTS = ("latitude", "lat", "y")
LNG_COLUMN_HINTS = ("longitude", "lng", "lon", "long", "x")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safety_envelope() -> dict[str, Any]:
    return {
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "production_feed": False,
        "wordpress_modified": False,
        "business_publication_enabled": False,
    }


def default_reader_gates() -> dict[str, bool]:
    return {
        "business_publication_enabled": False,
        "civic_publication_enabled": False,
        "calendar_publication_enabled": False,
        "nypd_layer_enabled": False,
        "fdny_layer_enabled": False,
        "shelter_layer_enabled": False,
        "pet_care_layer_enabled": False,
        "resource_layer_enabled": False,
    }


def stable_id(*parts: Any) -> str:
    joined = "|".join(str(p or "").strip() for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def nyc_point(lat: Any, lng: Any) -> tuple[float | None, float | None, bool]:
    return valid_nyc_coords(lat, lng)


def first_present(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for name in names:
        if name in lowered and lowered[name] not in (None, ""):
            return lowered[name]
    return None


def row_looks_addressable(row: dict[str, Any]) -> bool:
    if first_present(row, ADDRESS_COLUMN_HINTS):
        return True
    lat = first_present(row, LAT_COLUMN_HINTS)
    lng = first_present(row, LNG_COLUMN_HINTS)
    _lat, _lng, ok = nyc_point(lat, lng)
    return ok


def fetch_soda_rows(dataset: str, *, limit: int = 5000) -> list[dict[str, Any]]:
    params = {"$limit": limit}
    url = f"{SODA_BASE}/{dataset}.json?{urlencode(params)}"
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"SODA {dataset}: expected a list")
    return [row for row in payload if isinstance(row, dict)]


def load_rows_from_fixture(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path, {})
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("rows", "features", "precincts", "places"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    raise ValueError(f"fixture {path} has no rows/features array")


def write_staging(
    *,
    artifact_type: str,
    source_dataset: str,
    rows: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
    staging_name: str,
    report_name: str,
) -> dict[str, Any]:
    generated = utc_now()
    envelope = safety_envelope()
    staging = {
        "artifact_type": artifact_type,
        "generated_at_utc": generated,
        "source_dataset": source_dataset,
        "row_count": len(rows),
        "rows": rows,
        **envelope,
    }
    if extra:
        staging.update(extra)
    staging_path = STAGING_DIR / staging_name
    report_path = REPORT_DIR / report_name
    try:
        staging_rel = str(staging_path.relative_to(ROOT))
    except ValueError:
        staging_rel = str(staging_path)
    report = {
        "artifact_type": f"{artifact_type}_report",
        "generated_at_utc": generated,
        "source_dataset": source_dataset,
        "staging_path": staging_rel,
        "row_count": len(rows),
        "qa_pass": True,
        "publication_allowed": False,
        "invented_storefronts": False,
        **envelope,
    }
    save_json(staging_path, staging)
    save_json(report_path, report)
    return report


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        return [{str(k).strip(): (v or "").strip() for k, v in row.items() if k} for row in reader]


def missing_howard_csv_message(path: Path) -> str:
    return (
        f"Howard CSV not found at {path}. "
        "Drop the ~91 curated storefronts (see data/culture/curated_storefronts.template.csv). "
        "This script will not invent businesses."
    )


__all__ = [
    "ADDRESS_COLUMN_HINTS",
    "CALENDAR_KINDS",
    "DATA_DIR",
    "FDNY_DATASET",
    "HOWARD_CSV",
    "NYC",
    "NYPD_DATASET",
    "PLACE_KINDS",
    "REPORT_DIR",
    "RESOURCE_KINDS",
    "SHELTER_DATASET",
    "STAGING_DIR",
    "TEMPLATE_CSV",
    "default_reader_gates",
    "fetch_soda_rows",
    "first_present",
    "load_json",
    "load_rows_from_fixture",
    "missing_howard_csv_message",
    "nyc_point",
    "read_csv_rows",
    "row_looks_addressable",
    "safety_envelope",
    "save_json",
    "stable_id",
    "utc_now",
    "write_staging",
]
