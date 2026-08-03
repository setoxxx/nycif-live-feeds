"""Pure cross-pipeline location-disposition accounting for NYC and NJ feeds."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

RECOGNIZED = {"map_safe", "approximate", "list_only"}
MAP_SAFE_ALIASES = {"map_safe", "map_ready", "exact", "exact_pin"}
APPROXIMATE_ALIASES = {"approximate", "approximate_marker", "park_level_anchor", "certified_facility", "approximate_area"}
LIST_ONLY_ALIASES = {"list_only", "unresolved", "hidden", "not_mappable"}


def event_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def disposition(event: dict[str, Any]) -> str | None:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    values = (
        event.get("map_status"),
        event.get("coordinate_status"),
        event.get("display_disposition"),
        event.get("coordinate_precision"),
        nycif.get("coordinate_status"),
        nycif.get("display_disposition"),
        nycif.get("coordinate_precision"),
    )
    normalized = [str(value).strip().casefold() for value in values if value not in (None, "")]
    if any(value in MAP_SAFE_ALIASES for value in normalized):
        return "map_safe"
    if any(value in APPROXIMATE_ALIASES for value in normalized):
        return "approximate"
    if any(value in LIST_ONLY_ALIASES for value in normalized):
        return "list_only"
    return None


def stable_event_id(event: dict[str, Any], index: int) -> str:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return str(
        event.get("id")
        or event.get("event_id")
        or event.get("source_event_id")
        or source.get("source_event_id")
        or f"row:{index}"
    )


def dedupe(events: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_id: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for index, event in enumerate(events):
        key = stable_event_id(event, index)
        if key in by_id:
            duplicates += 1
        by_id[key] = event
    return list(by_id.values()), duplicates


def account_pipeline(name: str, events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows, duplicates = dedupe(events)
    counts: Counter[str] = Counter()
    unaccounted: list[dict[str, Any]] = []
    for index, event in enumerate(rows):
        status = disposition(event)
        if status in RECOGNIZED:
            counts[status] += 1
            continue
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        unaccounted.append(
            {
                "id": stable_event_id(event, index),
                "title": event.get("title"),
                "latitude": event.get("latitude", event.get("lat")),
                "longitude": event.get("longitude", event.get("lng")),
                "map_status": event.get("map_status"),
                "coordinate_status": event.get("coordinate_status") or nycif.get("coordinate_status"),
                "coordinate_precision": event.get("coordinate_precision") or nycif.get("coordinate_precision"),
            }
        )
    total = len(rows)
    accounted = counts["map_safe"] + counts["approximate"] + counts["list_only"]
    return {
        "pipeline": name,
        "total_count": total,
        "map_safe_count": counts["map_safe"],
        "approximate_count": counts["approximate"],
        "list_only_count": counts["list_only"],
        "accounted_count": accounted,
        "unaccounted_count": total - accounted,
        "duplicate_id_count": duplicates,
        "qa_pass": accounted == total,
        "unaccounted_sample": unaccounted[:50],
    }


def delta(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, int | None]:
    keys = ("total_count", "map_safe_count", "approximate_count", "list_only_count", "unaccounted_count")
    if not isinstance(previous, dict):
        return {key: None for key in keys}
    return {key: int(current.get(key) or 0) - int(previous.get(key) or 0) for key in keys}
