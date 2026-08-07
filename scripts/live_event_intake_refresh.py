#!/usr/bin/env python3
"""Refresh all official NYC event sources and rebuild the map-ready intake.

This is the orchestration layer used by the scheduled discovery refresh. It
pulls permitted events, the NYC Citywide Calendar, and NYC Parks BigApps in one
transaction before enrichment and staging.

Street-segment resolution is owned by ``scripts.nyc_location_resolver``. This
orchestrator must not monkey-patch resolver behavior; scheduled production and
standalone tools must execute the same canonical fail-closed resolver contract.
"""

from __future__ import annotations

import os
import sys
from typing import Any

try:
    from scripts.nyc_location_resolver import (
        NYCLocationResolver,
        ResolveResult,
        coordinate_matches_borough,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from nyc_location_resolver import (  # type: ignore[no-redef]
        NYCLocationResolver,
        ResolveResult,
        coordinate_matches_borough,
    )


def resolve_street_segment_by_intersections(
    resolver: Any,
    display: str,
    borough: str | None,
) -> ResolveResult | None:
    """Compatibility wrapper around the canonical resolver implementation.

    Older regression code imports this helper from the orchestration module.
    Keep that import stable during migration, but delegate all segment logic to
    ``NYCLocationResolver`` so there is only one implementation authority.
    """
    if isinstance(resolver, NYCLocationResolver):
        return resolver._resolve_street_segment(display, borough)

    # Lightweight compatibility adapter for test resolvers that only expose
    # ``_resolve_geosearch``. Canonical segment code remains the implementation.
    adapter = object.__new__(NYCLocationResolver)
    adapter._resolve_geosearch = resolver._resolve_geosearch  # type: ignore[method-assign,attr-defined]
    return NYCLocationResolver._resolve_street_segment(adapter, display, borough)


def main() -> int:
    os.environ["NYCIF_USE_RAW_SNAPSHOT"] = "yes"
    os.environ["NYCIF_ALLOW_LIVE_GEOSEARCH"] = "yes"

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
