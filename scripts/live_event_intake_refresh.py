#!/usr/bin/env python3
"""Refresh all official NYC event sources and rebuild the semantic live intake.

This is the orchestration layer used by the discovery refresh. It pulls
permitted events, the NYC Citywide Calendar, and NYC Parks BigApps in one
transaction, then rebuilds the permitted-event intake through the shared
location-evidence authority before projection.

Street-segment resolution is owned by ``scripts.nyc_location_resolver``.
Coordinates alone never grant exact public pin authority.

The release-critical path defaults to cache/source-backed location evidence and
does not require live GeoSearch. Set ``NYCIF_ALLOW_LIVE_GEOSEARCH=yes`` only for
an explicit enrichment run. Unresolved rows remain review/list-only instead of
blocking publication or being promoted from weak coordinates.
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
    """Compatibility wrapper around the canonical resolver implementation."""
    if isinstance(resolver, NYCLocationResolver):
        return resolver._resolve_street_segment(display, borough)

    adapter = object.__new__(NYCLocationResolver)
    adapter._resolve_geosearch = resolver._resolve_geosearch  # type: ignore[method-assign,attr-defined]
    return NYCLocationResolver._resolve_street_segment(adapter, display, borough)


def main() -> int:
    # Source fetchers write local snapshots first; downstream builders consume
    # that exact transaction so all three source families share one refresh run.
    os.environ["NYCIF_USE_RAW_SNAPSHOT"] = "yes"
    os.environ.setdefault("NYCIF_ALLOW_LIVE_GEOSEARCH", "no")

    try:
        from scripts import (
            build_semantic_live_intake,
            sync_nyc_citywide_events_calendar,
            sync_nyc_open_data,
            sync_nyc_parks_bigapps_events,
        )
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        import build_semantic_live_intake  # type: ignore[no-redef]
        import sync_nyc_citywide_events_calendar  # type: ignore[no-redef]
        import sync_nyc_open_data  # type: ignore[no-redef]
        import sync_nyc_parks_bigapps_events  # type: ignore[no-redef]

    for name, runner in (
        ("sync_nyc_open_data", sync_nyc_open_data.main),
        ("sync_nyc_citywide_events_calendar", sync_nyc_citywide_events_calendar.main),
        ("sync_nyc_parks_bigapps_events", sync_nyc_parks_bigapps_events.main),
        ("build_semantic_live_intake", build_semantic_live_intake.main),
    ):
        result: Any = runner()
        if result not in (None, 0):
            print(f"{name} failed with exit code {result}", file=sys.stderr)
            return int(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
