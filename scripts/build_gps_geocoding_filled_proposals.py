#!/usr/bin/env python3
"""Build Phase 2C staging-only filled GPS geocoding proposals.

This script reads data/gps_review_geocoding_proposals.json and writes
proposed coordinate fields into a separate staging file only.

Safety guarantees:
- Does not modify data/location_cache.json.
- Does not modify data/nycif_staged_live_events.json.
- Does not publish anything to the public map.
- Does not set promotion_allowed=true.

Current fill strategy:
1. Prefer local approved reference files when they exist.
2. Use existing GPS repository memory as a conservative fallback for broad park/place names.
3. Leave unresolved rows pending with null coordinates.

Optional local reference inputs:
- data/manual_gps_reference.json
- data/nyc_parks_facility_reference.json

Outputs:
- data/gps_review_geocoding_filled_proposals.json
- data/gps_review_geocoding_fill_report.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PROPOSALS_PATH = DATA_DIR / "gps_review_geocoding_proposals.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
MANUAL_REFERENCE_PATH = DATA_DIR / "manual_gps_reference.json"
PARKS_REFERENCE_PATH = DATA_DIR / "nyc_parks_facility_reference.json"
FILLED_PROPOSALS_PATH = DATA_DIR / "gps_review_geocoding_filled_proposals.json"
FILL_REPORT_PATH = DATA_DIR / "gps_review_geocoding_fill_report.json"


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


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def reference_rows(path: Path) -> list[dict[str, Any]]:
    payload = load_json_file(path, {})
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("references", "facilities", "places", "rows", "events"):
            if isinstance(payload.get(key), list):
                return [row for row in payload[key] if isinstance(row, dict)]
    return []


def proposal_keys(row: dict[str, Any]) -> set[str]:
    values = [
        row.get("group_key"),
        row.get("display_location"),
        row.get("simplified_geocoder_query"),
        row.get("geocoder_query"),
    ]
    return {normalize_text_legacy(value) for value in values if normalize_text_legacy(value)}


def reference_keys(row: dict[str, Any]) -> set[str]:
    values = [
        row.get("group_key"),
        row.get("display_location"),
        row.get("name"),
        row.get("place_name"),
        row.get("facility_name"),
        row.get("geocoder_query"),
        row.get("simplified_geocoder_query"),
    ]
    borough = str(row.get("borough") or "").strip()
    for field in ("name", "place_name", "facility_name", "display_location"):
        value = str(row.get(field) or "").strip()
        if value and borough:
            values.append(f"{value}, {borough}, New York, NY")
    return {normalize_text_legacy(value) for value in values if normalize_text_legacy(value)}


def build_reference_index(paths: list[tuple[str, Path]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for source_name, path in paths:
        for row in reference_rows(path):
            lat = row.get("lat") or row.get("latitude")
            lng = row.get("lng") or row.get("lon") or row.get("longitude")
            if not valid_nyc_lat_lng(lat, lng):
                continue
            reference = {
                "lat": float(lat),
                "lng": float(lng),
                "source": row.get("geocoder_source") or row.get("source") or source_name,
                "place_id": row.get("geocoder_place_id") or row.get("place_id") or row.get("id"),
                "confidence": row.get("geocoder_confidence") or row.get("confidence") or "high",
                "confidence_reason": row.get("confidence_reason") or f"Matched local reference file {path.name}.",
            }
            for key in reference_keys(row):
                index.setdefault(key, reference)
            for field in ("name", "place_name", "facility_name", "display_location", "location_text"):
                simplified = simplified_place(str(row.get(field) or ""))
                if simplified:
                    index.setdefault(simplified, reference)
    return index


def location_cache_entries() -> dict[str, Any]:
    payload = load_json_file(LOCATION_CACHE_PATH, {})
    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return payload["entries"]
    return {}


def simplified_place(text: str) -> str:
    first = str(text or "").split(",")[0].strip()
    if ":" in first:
        first = first.split(":", 1)[0].strip()
    if "(" in first:
        first = first.split("(", 1)[0].strip()
    return normalize_text_legacy(first)


def build_cache_place_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for key, entry in location_cache_entries().items():
        if not isinstance(entry, dict) or not valid_nyc_lat_lng(entry.get("lat"), entry.get("lng")):
            continue
        borough = normalize_text_legacy(entry.get("borough"))
        display = entry.get("display_location") or entry.get("key_value") or key
        place = simplified_place(str(display))
        if not place:
            continue
        cache_key = f"{borough}|{place}"
        index.setdefault(cache_key, {
            "lat": float(entry.get("lat")),
            "lng": float(entry.get("lng")),
            "source": "existing_location_cache_place_memory",
            "place_id": key,
            "confidence": "medium",
            "confidence_reason": "Matched broad place name from existing NYCIF location cache. Requires manual approval before promotion.",
        })
    return index


def fill_from_references(row: dict[str, Any], reference_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key in proposal_keys(row):
        if key in reference_index:
            return reference_index[key]
    for value in (
        row.get("display_location"),
        row.get("simplified_geocoder_query"),
        row.get("geocoder_query"),
    ):
        simplified = simplified_place(str(value or ""))
        if simplified and simplified in reference_index:
            return reference_index[simplified]
    return None


def fill_from_cache_memory(row: dict[str, Any], cache_index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    borough = normalize_text_legacy(row.get("borough"))
    simplified = simplified_place(row.get("simplified_geocoder_query") or row.get("display_location"))
    if not borough or not simplified:
        return None
    return cache_index.get(f"{borough}|{simplified}")


def apply_fill(row: dict[str, Any], fill: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(row)
    out["phase_2c_processed"] = True
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    out["promotion_allowed"] = False
    if fill and valid_nyc_lat_lng(fill.get("lat"), fill.get("lng")):
        out["proposed_lat"] = float(fill["lat"])
        out["proposed_lng"] = float(fill["lng"])
        out["geocoder_source"] = fill.get("source")
        out["geocoder_place_id"] = fill.get("place_id")
        out["geocoder_confidence"] = fill.get("confidence")
        out["confidence_reason"] = fill.get("confidence_reason")
        out["manual_review_status"] = "pending"
        out["proposal_status"] = "filled_pending_manual_review"
    else:
        out["proposed_lat"] = None
        out["proposed_lng"] = None
        out["geocoder_source"] = None
        out["geocoder_place_id"] = None
        out["geocoder_confidence"] = None
        out["confidence_reason"] = "No local Parks/manual reference or conservative cache-memory match found."
        out["manual_review_status"] = "pending"
        out["proposal_status"] = "unfilled_pending_geocoder"
    return out


def main() -> int:
    payload = load_json_file(PROPOSALS_PATH, {})
    proposals = rows_from_payload(payload, "proposals")
    reference_index = build_reference_index([
        ("manual_gps_reference", MANUAL_REFERENCE_PATH),
        ("nyc_parks_facility_reference", PARKS_REFERENCE_PATH),
    ])
    cache_index = build_cache_place_index()

    filled: list[dict[str, Any]] = []
    for row in proposals:
        fill = fill_from_references(row, reference_index)
        if fill is None:
            fill = fill_from_cache_memory(row, cache_index)
        filled.append(apply_fill(row, fill))

    generated_at = datetime.now(timezone.utc).isoformat()
    status_counts = Counter(row.get("proposal_status") for row in filled)
    source_counts = Counter(row.get("geocoder_source") or "unfilled" for row in filled)
    confidence_counts = Counter(row.get("geocoder_confidence") or "unfilled" for row in filled)
    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2c_controlled_geocoder_fill",
        "input_proposal_count": len(proposals),
        "filled_count": status_counts.get("filled_pending_manual_review", 0),
        "unfilled_count": status_counts.get("unfilled_pending_geocoder", 0),
        "status_counts": dict(status_counts),
        "source_counts": dict(source_counts),
        "confidence_counts": dict(confidence_counts),
        "reference_keys_loaded": len(reference_index),
        "cache_place_keys_loaded": len(cache_index),
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed_count": 0,
        "next_required_step": "Manually review filled proposals. A separate promotion script may later promote only approved/high-confidence rows.",
    }

    save_json_file(FILLED_PROPOSALS_PATH, {"generated_at_utc": generated_at, "proposals": filled})
    save_json_file(FILL_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
