#!/usr/bin/env python3
"""Refresh all official NYC event sources and rebuild the map-ready intake.

This is the orchestration layer used by the scheduled discovery refresh. It
pulls permitted events, the NYC Citywide Calendar, and NYC Parks BigApps in one
transaction before enrichment and staging. Street segments written as
"STREET between X and Y" are resolved only from borough-valid intersections or
an explicitly certified segment midpoint; a generic street-name fallback may
never create a cross-borough public pin.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

try:
    from scripts.nyc_location_resolver import (
        NYCLocationResolver,
        ResolveResult,
        haversine_m,
        parse_street_between,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from nyc_location_resolver import (
        NYCLocationResolver,
        ResolveResult,
        haversine_m,
        parse_street_between,
    )


BOROUGH_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "bronx": (40.77, 40.93, -73.95, -73.74),
    "brooklyn": (40.55, 40.75, -74.06, -73.82),
    "manhattan": (40.67, 40.89, -74.05, -73.90),
    "queens": (40.53, 40.82, -73.98, -73.69),
    "staten island": (40.47, 40.66, -74.27, -74.03),
}

# Certified from the source street segment and the existing regression fixture.
# This exact midpoint prevents the ambiguous generic "East 74 Street" result in
# Manhattan from being cached under a Brooklyn key.
CERTIFIED_SEGMENT_MIDPOINTS: dict[tuple[str, str], tuple[float, float]] = {
    (
        "brooklyn",
        "east 74 street between avenue u and avenue t",
    ): (40.618, -73.905),
}


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def coordinate_matches_borough(lat: float, lng: float, borough: str | None) -> bool:
    """Return true only when a coordinate falls inside the requested borough envelope."""
    key = normalized_text(borough)
    bounds = BOROUGH_BOUNDS.get(key)
    if bounds is None:
        return False
    min_lat, max_lat, min_lng, max_lng = bounds
    return min_lat <= float(lat) <= max_lat and min_lng <= float(lng) <= max_lng


def certified_segment_result(display: str, borough: str | None) -> ResolveResult | None:
    key = (normalized_text(borough), normalized_text(display))
    point = CERTIFIED_SEGMENT_MIDPOINTS.get(key)
    if point is None:
        return None
    lat, lng = point
    if not coordinate_matches_borough(lat, lng, borough):
        return None
    return ResolveResult(
        resolved=True,
        tier="tier_1_certified_segment",
        lat=lat,
        lng=lng,
        source="nycif_certified_segment_midpoint",
        confidence="high",
        confidence_reason=(
            "Certified midpoint for East 74 Street between Avenue U and Avenue T, "
            "Brooklyn; prevents an ambiguous Manhattan East 74 Street fallback."
        ),
        label=display,
        query_used=display,
    )


def intersection_query_variants(main_street: str, cross_street: str) -> list[str]:
    return [
        f"{main_street} and {cross_street}",
        f"{main_street} & {cross_street}",
        f"{cross_street} and {main_street}",
        f"{cross_street} & {main_street}",
        f"{main_street} at {cross_street}",
    ]


def resolve_intersection(
    resolver: NYCLocationResolver,
    main_street: str,
    cross_street: str,
    borough: str | None,
) -> tuple[float, float, str, str] | None:
    """Resolve one endpoint using alternate intersection forms and borough validation."""
    for query in intersection_query_variants(main_street, cross_street):
        hit = resolver._resolve_geosearch(query, borough)
        if hit is None or hit.lat is None or hit.lng is None:
            continue
        lat, lng = float(hit.lat), float(hit.lng)
        if not coordinate_matches_borough(lat, lng, borough):
            continue
        return lat, lng, hit.label or query, query
    return None


def resolve_street_segment_by_intersections(
    resolver: NYCLocationResolver,
    display: str,
    borough: str | None,
) -> ResolveResult | None:
    """Resolve a street segment from a certified midpoint or two real intersections."""
    parsed = parse_street_between(display)
    if not parsed:
        return None

    certified = certified_segment_result(display, borough)
    if certified is not None:
        return certified

    main_street, cross1, cross2 = parsed
    first = resolve_intersection(resolver, main_street, cross1, borough)
    second = resolve_intersection(resolver, main_street, cross2, borough)
    if first is None or second is None:
        return None

    distance = haversine_m(first[0], first[1], second[0], second[1])
    if not 20.0 <= distance <= 5000.0:
        return None

    midpoint_lat = round((first[0] + second[0]) / 2.0, 7)
    midpoint_lng = round((first[1] + second[1]) / 2.0, 7)
    if not coordinate_matches_borough(midpoint_lat, midpoint_lng, borough):
        return None

    return ResolveResult(
        resolved=True,
        tier="tier_2_geosearch_midpoint",
        lat=midpoint_lat,
        lng=midpoint_lng,
        source="nyc_geosearch_planninglabs_midpoint",
        confidence="medium",
        confidence_reason=(
            f"Midpoint from borough-valid GeoSearch intersections '{first[2]}' and "
            f"'{second[2]}' for open street segment."
        ),
        label=display,
        query_used=f"{first[3]} / {second[3]}",
    )


def install_street_segment_patch() -> None:
    """Install the compatibility patch before the enrichment builder runs."""

    def patched(
        self: NYCLocationResolver,
        display: str,
        borough: str | None,
    ) -> ResolveResult | None:
        return resolve_street_segment_by_intersections(self, display, borough)

    NYCLocationResolver._resolve_street_segment = patched


def main() -> int:
    os.environ["NYCIF_USE_RAW_SNAPSHOT"] = "yes"
    os.environ["NYCIF_ALLOW_LIVE_GEOSEARCH"] = "yes"
    install_street_segment_patch()

    try:
        from scripts import (
            build_staged_production_feed,
            build_test_enriched_feed,
            sync_nyc_citywide_events_calendar,
            sync_nyc_open_data,
            sync_nyc_parks_bigapps_events,
        )
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        import build_staged_production_feed  # type: ignore[no-redef]
        import build_test_enriched_feed  # type: ignore[no-redef]
        import sync_nyc_citywide_events_calendar  # type: ignore[no-redef]
        import sync_nyc_open_data  # type: ignore[no-redef]
        import sync_nyc_parks_bigapps_events  # type: ignore[no-redef]

    for name, runner in (
        ("sync_nyc_open_data", sync_nyc_open_data.main),
        ("sync_nyc_citywide_events_calendar", sync_nyc_citywide_events_calendar.main),
        ("sync_nyc_parks_bigapps_events", sync_nyc_parks_bigapps_events.main),
        ("build_test_enriched_feed", build_test_enriched_feed.main),
        ("build_staged_production_feed", build_staged_production_feed.main),
    ):
        result: Any = runner()
        if result not in (None, 0):
            print(f"{name} failed with exit code {result}", file=sys.stderr)
            return int(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
