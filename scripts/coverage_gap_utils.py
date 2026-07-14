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
