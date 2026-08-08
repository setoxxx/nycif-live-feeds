#!/usr/bin/env python3
"""Refresh official NYC event sources and rebuild the semantic live intake.

BORG acquisition runs first. A store-first BORG -> Enigma handoff receipt is
then built from the exact acquired snapshots before any semantic processing.
Only after that accounting gate passes may the semantic live intake run.

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
    # that exact transaction so all source families share one refresh run.
    os.environ["NYCIF_USE_RAW_SNAPSHOT"] = "yes"
    os.environ.setdefault("NYCIF_ALLOW_LIVE_GEOSEARCH", "no")

    try:
        from scripts import (
            build_borg_enigma_handoff,
            build_semantic_live_intake,
            sync_nyc_citywide_events_calendar,
            sync_nyc_open_data,
            sync_nyc_parks_bigapps_events,
        )
    except ModuleNotFoundError:  # pragma: no cover - direct script execution
        import build_borg_enigma_handoff  # type: ignore[no-redef]
        import build_semantic_live_intake  # type: ignore[no-redef]
        import sync_nyc_citywide_events_calendar  # type: ignore[no-redef]
        import sync_nyc_open_data  # type: ignore[no-redef]
        import sync_nyc_parks_bigapps_events  # type: ignore[no-redef]

    # BORG: acquire and preserve the exact source transaction.
    for name, runner in (
        ("sync_nyc_open_data", sync_nyc_open_data.main),
        ("sync_nyc_citywide_events_calendar", sync_nyc_citywide_events_calendar.main),
        ("sync_nyc_parks_bigapps_events", sync_nyc_parks_bigapps_events.main),
    ):
        result: Any = runner()
        if result not in (None, 0):
            print(f"{name} failed with exit code {result}", file=sys.stderr)
            return int(result)

    # ENIGMA intake boundary: prove every acquired row is registered before
    # semantic filtering. This receipt grants no identity or location authority.
    result = build_borg_enigma_handoff.main()
    if result not in (None, 0):
        print(
            f"build_borg_enigma_handoff failed with exit code {result}",
            file=sys.stderr,
        )
        return int(result)

    # Semantic authorities act only after the store-first handoff passes.
    result = build_semantic_live_intake.main()
    if result not in (None, 0):
        print(
            f"build_semantic_live_intake failed with exit code {result}",
            file=sys.stderr,
        )
        return int(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
