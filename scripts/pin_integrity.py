#!/usr/bin/env python3
"""NYC pin integrity — single source of truth for desk map_ready certification.

Hard rule: never leave ocean / Null Island / swapped / OOB coords on the pin path.
Prefer demote to list_only over inventing replacements.

Bounds (NYC metro envelope, documented):
  lat 40.4774 .. 40.9176
  lng -74.2591 .. -73.7004
(Same envelope as schema_v1_common.NYC.)
"""

from __future__ import annotations

import math
from typing import Any

from schema_v1_common import NYC, is_zero_coord_pair

# Stable reason codes for QA reports.
REASON_OK = "ok_nyc_certified"
REASON_OK_SWAP = "ok_nyc_certified_swap_corrected"
REASON_MISSING = "missing_coords"
REASON_NONFINITE = "nonfinite"
REASON_NULL_ISLAND = "null_island"
REASON_OOB = "oob_outside_nyc_box"
REASON_SWAP_SUSPECTED = "swap_suspected_demoted"
REASON_STATUS_WITHOUT_COORDS = "map_ready_without_coords"
REASON_PROPOSED_KEEP = "proposed_unverified_keep"

NYC_BOUNDS_DOC = {
    "min_lat": NYC["min_lat"],
    "max_lat": NYC["max_lat"],
    "min_lng": NYC["min_lng"],
    "max_lng": NYC["max_lng"],
    "label": "NYC metro envelope (schema_v1_common.NYC)",
}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def in_nyc_box(lat: float, lng: float) -> bool:
    return (
        NYC["min_lat"] <= lat <= NYC["max_lat"]
        and NYC["min_lng"] <= lng <= NYC["max_lng"]
    )


def certify_nyc_pin(
    lat: Any,
    lng: Any,
    *,
    allow_swap_correct: bool = True,
) -> tuple[float | None, float | None, bool, str]:
    """Return (lat, lng, ok, reason_code).

    Swap correction (proven in civic farmers-market path): only when the as-is
    pair is outside the NYC box AND the swapped pair is inside. Logged as
    ok_nyc_certified_swap_corrected. Ambiguous cases are demoted, never invented.
    """
    lat_f = _as_float(lat)
    lng_f = _as_float(lng)
    if lat_f is None and lng_f is None:
        return None, None, False, REASON_MISSING
    if lat_f is None or lng_f is None:
        return None, None, False, REASON_NONFINITE
    if is_zero_coord_pair(lat_f, lng_f):
        return None, None, False, REASON_NULL_ISLAND
    if in_nyc_box(lat_f, lng_f):
        return lat_f, lng_f, True, REASON_OK

    # Swap candidate: values look like they were stored flipped.
    if allow_swap_correct and in_nyc_box(lng_f, lat_f):
        return lng_f, lat_f, True, REASON_OK_SWAP

    looks_swapped = (
        NYC["min_lat"] <= lng_f <= NYC["max_lat"]
        and NYC["min_lng"] <= lat_f <= NYC["max_lng"]
    )
    if looks_swapped:
        return None, None, False, REASON_SWAP_SUSPECTED
    return None, None, False, REASON_OOB


def _set_pin_coords(event: dict[str, Any], lat_f: float | None, lng_f: float | None) -> None:
    event["latitude"] = lat_f
    event["longitude"] = lng_f
    if "lat" in event:
        event["lat"] = lat_f
    if "lng" in event:
        event["lng"] = lng_f


def _demote_event(event: dict[str, Any], reason: str) -> None:
    _set_pin_coords(event, None, None)
    event["map_link"] = None
    event["coordinate_status"] = "list_only"
    event["pin_integrity_reason"] = reason
    event["certified_pin"] = False


def _certify_proposed(
    event: dict[str, Any],
    before_lat: Any,
    before_lng: Any,
    *,
    allow_swap_correct: bool,
) -> dict[str, Any]:
    lat_f, lng_f, ok, reason = certify_nyc_pin(before_lat, before_lng, allow_swap_correct=allow_swap_correct)
    if ok:
        _set_pin_coords(event, lat_f, lng_f)
        event["pin_integrity_reason"] = reason
        event["certified_pin"] = False  # proposed ≠ certified map pin
        return {"changed": False, "reason": REASON_PROPOSED_KEEP, "status": "proposed"}
    _demote_event(event, reason)
    return {
        "changed": True,
        "reason": reason,
        "before_status": "proposed",
        "after_status": "list_only",
        "before_lat": before_lat,
        "before_lng": before_lng,
    }


def _missing_claimed_coords(before_status: str, before_lat: Any, before_lng: Any) -> bool:
    if before_status != "map_ready":
        return False
    return before_lat in (None, "") or before_lng in (None, "")


def certify_event_pin(event: dict[str, Any], *, allow_swap_correct: bool = True) -> dict[str, Any]:
    """Certify/demote a single event-like dict in place for pin path fields.

    Returns a demotion record when status changes away from map_ready, else summary.
    Never invents coordinates. Clears lat/lng on demotion so bad numbers cannot render.
    """
    before_status = str(event.get("coordinate_status") or "")
    before_lat = event.get("latitude", event.get("lat"))
    before_lng = event.get("longitude", event.get("lng"))

    if before_status == "proposed":
        return _certify_proposed(
            event, before_lat, before_lng, allow_swap_correct=allow_swap_correct
        )

    lat_f, lng_f, ok, reason = certify_nyc_pin(before_lat, before_lng, allow_swap_correct=allow_swap_correct)
    if _missing_claimed_coords(before_status, before_lat, before_lng):
        ok = False
        reason = REASON_STATUS_WITHOUT_COORDS

    if ok and lat_f is not None and lng_f is not None:
        _set_pin_coords(event, lat_f, lng_f)
        event["coordinate_status"] = "map_ready"
        event["pin_integrity_reason"] = reason
        event["certified_pin"] = True
        return {
            "changed": reason == REASON_OK_SWAP,
            "reason": reason,
            "status": "map_ready",
            "before_lat": before_lat,
            "before_lng": before_lng,
            "after_lat": lat_f,
            "after_lng": lng_f,
        }

    _demote_event(event, reason)
    return {
        "changed": before_status == "map_ready" or before_lat not in (None, "") or before_lng not in (None, ""),
        "demoted": True,
        "reason": reason,
        "before_status": before_status or "missing",
        "after_status": "list_only",
        "before_lat": before_lat,
        "before_lng": before_lng,
    }


def nested_nycif_certify(event: dict[str, Any], *, allow_swap_correct: bool = True) -> dict[str, Any]:
    """Certify schema events that nest coordinate_status under nycif."""
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    flat = {
        "coordinate_status": nycif.get("coordinate_status") or event.get("coordinate_status"),
        "latitude": event.get("latitude"),
        "longitude": event.get("longitude"),
    }
    result = certify_event_pin(flat, allow_swap_correct=allow_swap_correct)
    event["latitude"] = flat.get("latitude")
    event["longitude"] = flat.get("longitude")
    if "nycif" not in event or not isinstance(event["nycif"], dict):
        event["nycif"] = {}
    event["nycif"]["coordinate_status"] = flat.get("coordinate_status")
    event["nycif"]["pin_integrity_reason"] = flat.get("pin_integrity_reason")
    event["nycif"]["certified_pin"] = flat.get("certified_pin")
    if flat.get("coordinate_status") != "map_ready":
        event["map_link"] = None
    return result
