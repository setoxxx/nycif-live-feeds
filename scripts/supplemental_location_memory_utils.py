"""Shared supplemental location memory lookup helpers for intake auto-resolution."""

from __future__ import annotations

from typing import Any

try:
    from scripts.build_supplemental_pin_quality_review_report import parent_park_from_display
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        parse_facility_in_parent,
        simplified_place,
        valid_nyc_lat_lng,
    )
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_location_gazetteer import (
        SUPPLEMENTAL_OVERLAY_PATH,
        NYCLocationGazetteer,
        borough_norm,
        load_supplemental_gazetteer_overlay,
    )
except ModuleNotFoundError:  # pragma: no cover
    from build_supplemental_pin_quality_review_report import parent_park_from_display
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        parse_facility_in_parent,
        simplified_place,
        valid_nyc_lat_lng,
    )
    from gps_identity import normalize_text_legacy
    from nyc_location_gazetteer import (
        SUPPLEMENTAL_OVERLAY_PATH,
        NYCLocationGazetteer,
        borough_norm,
        load_supplemental_gazetteer_overlay,
    )

MEMORY_PATH = DATA_DIR / "supplemental_location_memory.json"
LOW_CONFIDENCE = {"low", None, ""}


def location_key_for_row(row: dict[str, Any]) -> str:
    display = str(row.get("display_location") or "").strip()
    borough = borough_norm(row.get("borough"))
    norm_display = normalize_text_legacy(display)
    parent = parent_park_from_display(display)
    if parent:
        norm_parent = normalize_text_legacy(parent)
        return f"{borough}|{norm_display}|parent:{norm_parent}"
    return f"{borough}|{norm_display}"


def load_memory_entries(path: Any = MEMORY_PATH) -> dict[str, dict[str, Any]]:
    payload = load_json_file(path, {})
    entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
    if not isinstance(entries, dict):
        return {}
    return {str(key): value for key, value in entries.items() if isinstance(value, dict)}


def needs_memory_fill(row: dict[str, Any]) -> bool:
    if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
        return True
    confidence = str(row.get("geocoder_confidence") or "").strip().lower()
    return confidence in LOW_CONFIDENCE


def _fill_from_memory_entry(entry: dict[str, Any], *, location_key: str) -> dict[str, Any]:
    return {
        "proposed_lat": float(entry["proposed_lat"]),
        "proposed_lng": float(entry["proposed_lng"]),
        "lat": float(entry["proposed_lat"]),
        "lng": float(entry["proposed_lng"]),
        "geocoder_source": str(entry.get("geocoder_source") or "supplemental_location_memory"),
        "geocoder_confidence": str(entry.get("geocoder_confidence") or "medium"),
        "confidence_reason": (
            f"Supplemental location memory auto-resolution for '{entry.get('display_location')}' "
            f"({entry.get('event_count', 1)} prior approved event(s); staging intake only)."
        ),
        "fill_method": "supplemental_location_memory",
        "auto_resolved": True,
        "memory_location_key": location_key,
        "has_coordinates": True,
    }


def _fill_from_gazetteer_hit(hit: dict[str, Any], *, lookup_key: str) -> dict[str, Any]:
    source = str(hit.get("source") or "supplemental_location_gazetteer_overlay")
    return {
        "proposed_lat": float(hit["lat"]),
        "proposed_lng": float(hit["lng"]),
        "lat": float(hit["lat"]),
        "lng": float(hit["lng"]),
        "geocoder_source": source,
        "geocoder_confidence": str(hit.get("confidence") or "medium"),
        "confidence_reason": (
            f"Supplemental gazetteer overlay auto-resolution via '{lookup_key}' "
            f"({source}; staging intake only)."
        ),
        "fill_method": "supplemental_location_gazetteer_overlay",
        "auto_resolved": True,
        "memory_location_key": lookup_key,
        "has_coordinates": True,
    }


def lookup_memory_fill(
    row: dict[str, Any],
    memory_entries: dict[str, dict[str, Any]],
    gazetteer: NYCLocationGazetteer | None = None,
) -> dict[str, Any] | None:
    key = location_key_for_row(row)
    entry = memory_entries.get(key)
    if entry and valid_nyc_lat_lng(entry.get("proposed_lat"), entry.get("proposed_lng")):
        return _fill_from_memory_entry(entry, location_key=key)

    display = str(row.get("display_location") or "").strip()
    if not display:
        return None

    if gazetteer is None:
        overlay_index = load_supplemental_gazetteer_overlay(SUPPLEMENTAL_OVERLAY_PATH)
        gazetteer = NYCLocationGazetteer(overlay_index)

    borough_key = borough_norm(row.get("borough"))
    candidates = [
        key,
        normalize_text_legacy(display),
        f"{borough_key}|{normalize_text_legacy(display)}" if borough_key else "",
        f"{borough_key}|{simplified_place(display)}" if borough_key else "",
        simplified_place(display),
    ]
    decomposed = parse_facility_in_parent(display)
    if decomposed:
        child, parent = decomposed
        candidates.extend(
            [
                normalize_text_legacy(child),
                f"{borough_key}|{normalize_text_legacy(child)}" if borough_key else "",
                f"{borough_key}|{simplified_place(child)}" if borough_key else "",
                simplified_place(child),
                normalize_text_legacy(parent),
                f"{borough_key}|{normalize_text_legacy(parent)}" if borough_key else "",
                f"{borough_key}|{simplified_place(parent)}" if borough_key else "",
                simplified_place(parent),
            ]
        )

    for candidate in candidates:
        if not candidate:
            continue
        hit = gazetteer.lookup(candidate)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            source = str(hit.get("source") or "")
            if source.startswith("supplemental"):
                return _fill_from_gazetteer_hit(hit, lookup_key=candidate)

    hit = gazetteer.lookup_display(display, row.get("borough"))
    if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
        source = str(hit.get("source") or "")
        if source.startswith("supplemental"):
            return _fill_from_gazetteer_hit(hit, lookup_key=location_key_for_row(row))
    return None


def apply_memory_fill_to_event(event: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    updated = dict(event)
    updated.update(fill)
    updated["promotion_allowed"] = False
    updated["public_map_modified"] = False
    updated["location_cache_modified"] = False
    updated["staged_feed_modified"] = False
    if updated.get("manual_review_status") in {None, ""}:
        updated["manual_review_status"] = "pending"
    return updated


def apply_memory_to_events(
    events: list[dict[str, Any]],
    *,
    memory_entries: dict[str, dict[str, Any]] | None = None,
    gazetteer: NYCLocationGazetteer | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    memory_entries = memory_entries if memory_entries is not None else load_memory_entries()
    if gazetteer is None:
        gazetteer = NYCLocationGazetteer(load_supplemental_gazetteer_overlay(SUPPLEMENTAL_OVERLAY_PATH))

    updated_events: list[dict[str, Any]] = []
    stats = {
        "event_count": len(events),
        "attempted_fill_count": 0,
        "memory_filled_count": 0,
        "already_had_coordinates_count": 0,
        "still_without_coordinates_count": 0,
        "fill_method_counts": {},
    }

    for event in events:
        row = dict(event)
        if not needs_memory_fill(row):
            stats["already_had_coordinates_count"] += 1
            updated_events.append(row)
            continue

        stats["attempted_fill_count"] += 1
        fill = lookup_memory_fill(row, memory_entries, gazetteer)
        if fill:
            row = apply_memory_fill_to_event(row, fill)
            stats["memory_filled_count"] += 1
            method = str(fill.get("fill_method") or "supplemental_location_memory")
            stats["fill_method_counts"][method] = stats["fill_method_counts"].get(method, 0) + 1
        if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
            stats["still_without_coordinates_count"] += 1
        updated_events.append(row)

    if stats["event_count"]:
        stats["memory_filled_pct"] = round((stats["memory_filled_count"] / stats["event_count"]) * 100.0, 2)
        stats["attempted_fill_resolution_pct"] = round(
            (stats["memory_filled_count"] / stats["attempted_fill_count"]) * 100.0, 2
        ) if stats["attempted_fill_count"] else 0.0
        stats["with_coordinates_after_count"] = stats["event_count"] - stats["still_without_coordinates_count"]
        stats["with_coordinates_after_pct"] = round(
            (stats["with_coordinates_after_count"] / stats["event_count"]) * 100.0, 2
        )
    return updated_events, stats
