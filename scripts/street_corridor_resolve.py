"""Turn a parsed block face into CORRIDOR_READY endpoints.

A and B must both resolve in-bounds in the same borough. The occurrence
keeps lat/lng null and certified_pin false. The phone draws A -- B.
"""

from __future__ import annotations

import math
from typing import Any, Callable

try:
    from scripts.official_event_contract import NYC_LAT_RANGE, NYC_LNG_RANGE, in_nyc_bounds
    from scripts.street_corridor_parse import parse_street_corridor
except ModuleNotFoundError:  # pragma: no cover
    from official_event_contract import NYC_LAT_RANGE, NYC_LNG_RANGE, in_nyc_bounds
    from street_corridor_parse import parse_street_corridor

PointLookup = Callable[[str, str | None], tuple[float, float] | None]
MIN_DISTANCE_M = 20.0
MAX_DISTANCE_M = 1609.34 * 0.6  # 0.6 miles ~ 6 short blocks


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _valid(lat: float, lng: float) -> bool:
    return in_nyc_bounds(lat, lng) and NYC_LAT_RANGE[0] <= lat <= NYC_LAT_RANGE[1] and NYC_LNG_RANGE[0] <= lng <= NYC_LNG_RANGE[1]


def resolve_corridor(
    display_location: str | None,
    borough: str | None,
    lookup: PointLookup,
) -> dict[str, Any]:
    parsed = parse_street_corridor(display_location, borough)
    if parsed is None:
        return {
            "ok": False,
            "map_eligibility_state": "LIST_ONLY",
            "reason_code": "NOT_STREET_BETWEEN_CLAIM",
        }

    point_a = lookup(parsed["query_a"], parsed.get("borough"))
    point_b = lookup(parsed["query_b"], parsed.get("borough"))
    if not point_a or not point_b:
        parsed["reason_code"] = "SEGMENT_ENDPOINT_UNRESOLVED"
        return {
            "ok": False,
            "map_eligibility_state": "LIST_ONLY",
            "reason_code": "SEGMENT_ENDPOINT_UNRESOLVED",
            "corridor": parsed,
        }

    lat_a, lng_a = point_a
    lat_b, lng_b = point_b
    if not _valid(lat_a, lng_a) or not _valid(lat_b, lng_b):
        parsed["reason_code"] = "SEGMENT_ENDPOINT_OUT_OF_BOUNDS"
        return {
            "ok": False,
            "map_eligibility_state": "LIST_ONLY",
            "reason_code": "SEGMENT_ENDPOINT_OUT_OF_BOUNDS",
            "corridor": parsed,
        }

    distance = haversine_m(lat_a, lng_a, lat_b, lng_b)
    if not MIN_DISTANCE_M <= distance <= MAX_DISTANCE_M:
        parsed["reason_code"] = "SEGMENT_DISTANCE_OUT_OF_RANGE"
        parsed["distance_m"] = round(distance, 1)
        return {
            "ok": False,
            "map_eligibility_state": "LIST_ONLY",
            "reason_code": "SEGMENT_DISTANCE_OUT_OF_RANGE",
            "corridor": parsed,
        }

    parsed["point_a"] = {"lat": round(lat_a, 7), "lng": round(lng_a, 7)}
    parsed["point_b"] = {"lat": round(lat_b, 7), "lng": round(lng_b, 7)}
    parsed["line"] = [
        [round(lng_a, 7), round(lat_a, 7)],
        [round(lng_b, 7), round(lat_b, 7)],
    ]
    parsed["distance_m"] = round(distance, 1)
    parsed["resolver"] = "injected_lookup"
    parsed["reason_code"] = "CERTIFIED_STREET_SEGMENT"
    parsed["map_eligibility_state"] = "CORRIDOR_READY"
    return {
        "ok": True,
        "map_eligibility_state": "CORRIDOR_READY",
        "certified_pin": False,
        "map_ready": False,
        "display_disposition": "CORRIDOR",
        "reason_code": "CERTIFIED_STREET_SEGMENT",
        "lat": None,
        "lng": None,
        "corridor": parsed,
    }
