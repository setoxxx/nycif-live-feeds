"""NYC location gazetteer — unified index from public in-repo sources."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
GAZETTEER_PATH = DATA_DIR / "nyc_location_gazetteer.json"
GEOSEARCH_CACHE_PATH = DATA_DIR / "nyc_geosearch_gazetteer_cache.json"

LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
PARKS_FACILITY_PATH = DATA_DIR / "nyc_parks_facility_reference.json"
PARKS_EVENTS_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
MANUAL_REFERENCE_PATH = DATA_DIR / "manual_gps_reference.json"


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def simplified_place(text: str) -> str:
    first = str(text or "").split(",")[0].strip()
    if ":" in first:
        first = first.split(":", 1)[0].strip()
    if "(" in first:
        first = first.split("(", 1)[0].strip()
    return normalize_text_legacy(first)


def borough_norm(value: Any) -> str:
    return normalize_text_legacy(value)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def gazetteer_entry(
    *,
    lat: float,
    lng: float,
    source: str,
    confidence: str,
    confidence_reason: str,
    label: str | None = None,
    borough: str | None = None,
) -> dict[str, Any]:
    return {
        "lat": float(lat),
        "lng": float(lng),
        "source": source,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "label": label,
        "borough": borough,
    }


def add_index_key(index: dict[str, dict[str, Any]], key: str, entry: dict[str, Any]) -> None:
    if not key:
        return
    existing = index.get(key)
    if existing is None:
        index[key] = entry
        return
    rank = {"high": 3, "medium": 2, "low": 1}
    if rank.get(str(entry.get("confidence")), 0) > rank.get(str(existing.get("confidence")), 0):
        index[key] = entry


def build_gazetteer_index() -> dict[str, Any]:
    index: dict[str, dict[str, Any]] = {}
    source_counts: dict[str, int] = {}

    cache_payload = load_json(LOCATION_CACHE_PATH, {})
    cache_entries = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
    if isinstance(cache_entries, dict):
        for key, row in cache_entries.items():
            if not isinstance(row, dict) or not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
                continue
            entry = gazetteer_entry(
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                source="location_cache",
                confidence="high",
                confidence_reason="Existing NYCIF location_cache entry.",
                label=row.get("display_location") or row.get("key_value") or key,
                borough=row.get("borough"),
            )
            add_index_key(index, str(key), entry)
            borough = borough_norm(row.get("borough"))
            display = row.get("display_location") or row.get("key_value") or key
            place = simplified_place(str(display))
            if borough and place:
                add_index_key(index, f"{borough}|{place}", entry)
            source_counts["location_cache"] = source_counts.get("location_cache", 0) + 1

    facility_payload = load_json(PARKS_FACILITY_PATH, {})
    facilities = facility_payload.get("facilities", []) if isinstance(facility_payload, dict) else []
    for row in facilities:
        if not isinstance(row, dict) or not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
            continue
        borough = borough_norm(row.get("borough"))
        entry = gazetteer_entry(
            lat=float(row["lat"]),
            lng=float(row["lng"]),
            source="nyc_parks_facility_reference",
            confidence="high",
            confidence_reason="Official NYC Parks BigApps facility reference.",
            label=row.get("facility_name") or row.get("display_location"),
            borough=row.get("borough"),
        )
        for field in ("facility_name", "display_location", "location_text", "name"):
            token = simplified_place(str(row.get(field) or ""))
            if token:
                add_index_key(index, token, entry)
                if borough:
                    add_index_key(index, f"{borough}|{token}", entry)
        source_counts["nyc_parks_facility_reference"] = source_counts.get("nyc_parks_facility_reference", 0) + 1

    parks_payload = load_json(PARKS_EVENTS_PATH, {})
    parks_events = parks_payload.get("events", parks_payload) if isinstance(parks_payload, dict) else parks_payload
    if isinstance(parks_events, list):
        for row in parks_events:
            if not isinstance(row, dict) or not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
                continue
            entry = gazetteer_entry(
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                source="nyc_parks_bigapps_events_snapshot",
                confidence="high",
                confidence_reason="NYC Parks BigApps events snapshot location.",
                label=row.get("location") or row.get("title"),
            )
            for field in ("location", "display_location", "title"):
                token = simplified_place(str(row.get(field) or ""))
                if token:
                    add_index_key(index, token, entry)
            source_counts["nyc_parks_bigapps_events_snapshot"] = (
                source_counts.get("nyc_parks_bigapps_events_snapshot", 0) + 1
            )

    manual_payload = load_json(MANUAL_REFERENCE_PATH, {})
    manual_rows = manual_payload.get("references", manual_payload) if isinstance(manual_payload, dict) else []
    if isinstance(manual_rows, list):
        for row in manual_rows:
            if not isinstance(row, dict) or not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
                continue
            borough = borough_norm(row.get("borough"))
            entry = gazetteer_entry(
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                source=str(row.get("geocoder_source") or "manual_gps_reference"),
                confidence=str(row.get("geocoder_confidence") or "medium"),
                confidence_reason=str(row.get("confidence_reason") or "Manual GPS reference row."),
                label=row.get("display_location"),
                borough=row.get("borough"),
            )
            for field in ("group_key", "display_location", "simplified_geocoder_query"):
                token = normalize_text_legacy(str(row.get(field) or ""))
                if token:
                    add_index_key(index, token, entry)
                place = simplified_place(str(row.get(field) or ""))
                if borough and place:
                    add_index_key(index, f"{borough}|{place}", entry)
            source_counts["manual_gps_reference"] = source_counts.get("manual_gps_reference", 0) + 1

    geosearch_cache = load_json(GEOSEARCH_CACHE_PATH, {})
    cache_rows = geosearch_cache.get("entries", geosearch_cache) if isinstance(geosearch_cache, dict) else {}
    if isinstance(cache_rows, dict):
        for key, row in cache_rows.items():
            if not isinstance(row, dict) or not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
                continue
            entry = gazetteer_entry(
                lat=float(row["lat"]),
                lng=float(row["lng"]),
                source="nyc_geosearch_gazetteer_cache",
                confidence=str(row.get("confidence") or "medium"),
                confidence_reason=str(row.get("confidence_reason") or "Cached NYC GeoSearch result."),
                label=row.get("label"),
                borough=row.get("borough"),
            )
            add_index_key(index, str(key), entry)
            source_counts["nyc_geosearch_gazetteer_cache"] = (
                source_counts.get("nyc_geosearch_gazetteer_cache", 0) + 1
            )

    return {
        "artifact_type": "nyc_location_gazetteer",
        "index": index,
        "index_key_count": len(index),
        "source_row_counts": source_counts,
    }


class NYCLocationGazetteer:
    def __init__(self, index: dict[str, dict[str, Any]]) -> None:
        self.index = index

    @classmethod
    def from_file(cls, path: Path = GAZETTEER_PATH) -> NYCLocationGazetteer:
        payload = load_json(path, {})
        index = payload.get("index", {}) if isinstance(payload, dict) else {}
        if not isinstance(index, dict):
            index = {}
        return cls(index)

    def lookup(self, key: str) -> dict[str, Any] | None:
        return self.index.get(key)

    def lookup_display(self, display_location: str, borough: str | None = None) -> dict[str, Any] | None:
        display = str(display_location or "").strip()
        if not display:
            return None
        borough_key = borough_norm(borough)
        candidates = [
            normalize_text_legacy(display),
            f"{borough_key}|{normalize_text_legacy(display)}" if borough_key else "",
            f"{borough_key}|{simplified_place(display)}" if borough_key else "",
            simplified_place(display),
        ]
        parent = display.split(":")[0].strip() if ":" in display else display
        if parent != display:
            candidates.extend(
                [
                    normalize_text_legacy(parent),
                    f"{borough_key}|{simplified_place(parent)}" if borough_key else "",
                    simplified_place(parent),
                ]
            )
        for key in candidates:
            if key and key in self.index:
                return self.index[key]
        return None
