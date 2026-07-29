#!/usr/bin/env python3
"""Refresh the live NYC permit snapshot and rebuild the map-ready staged intake.

This is the narrow orchestration layer used by the scheduled discovery refresh.
It keeps the existing sync, enrichment and staging builders intact while fixing
street-segment geocoding for locations written as "STREET between X and Y".
"""

from __future__ import annotations

import os
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


def resolve_street_segment_by_intersections(
    resolver: NYCLocationResolver,
    display: str,
    borough: str | None,
) -> ResolveResult | None:
    """Resolve a street segment from its two real intersections.

    The legacy resolver queried generic house numbers on each cross street and
    embedded the borough twice. Querying the two intersections is both more
    precise and compatible with the resolver's existing borough appending.
    """

    parsed = parse_street_between(display)
    if not parsed:
        return None

    main_street, cross1, cross2 = parsed
    endpoint_queries = [
        f"{main_street} and {cross1}",
        f"{main_street} and {cross2}",
    ]
    points: list[tuple[float, float, str]] = []
    for query in endpoint_queries:
        hit = resolver._resolve_geosearch(query, borough)
        if hit and hit.lat is not None and hit.lng is not None:
            points.append((hit.lat, hit.lng, hit.label or query))

    if len(points) >= 2:
        first, second = points[0], points[1]
        distance = haversine_m(first[0], first[1], second[0], second[1])
        if distance >= 20.0:
            return ResolveResult(
                resolved=True,
                tier="tier_2_geosearch_midpoint",
                lat=round((first[0] + second[0]) / 2.0, 7),
                lng=round((first[1] + second[1]) / 2.0, 7),
                source="nyc_geosearch_planninglabs_midpoint",
                confidence="medium",
                confidence_reason=(
                    f"Midpoint from GeoSearch intersections '{first[2]}' and "
                    f"'{second[2]}' for open street segment."
                ),
                label=display,
                query_used=f"{main_street} at {cross1} / {cross2}",
            )

    return resolver._resolve_geosearch(main_street, borough)


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
    # The sync writes the new source snapshot. The enrichment builder must then
    # consume that exact snapshot and may use NYC Planning GeoSearch for new
    # locations that are not yet in the committed gazetteer/cache.
    os.environ["NYCIF_USE_RAW_SNAPSHOT"] = "yes"
    os.environ["NYCIF_ALLOW_LIVE_GEOSEARCH"] = "yes"
    install_street_segment_patch()

    try:
        from scripts import (
            build_staged_production_feed,
            build_test_enriched_feed,
            sync_nyc_open_data,
        )
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        import build_staged_production_feed  # type: ignore[no-redef]
        import build_test_enriched_feed  # type: ignore[no-redef]
        import sync_nyc_open_data  # type: ignore[no-redef]

    for name, runner in (
        ("sync_nyc_open_data", sync_nyc_open_data.main),
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
