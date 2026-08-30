#!/usr/bin/env python3
"""Compatibility wrapper for V3 reader-safe output plus reusable geography.

The base V3 builder remains fail-closed. This wrapper adds two explicitly safe
extensions used by the production transaction:

* ``approximate_marker`` remains reader-visible with null geometry and is mapped
  only by the separate approximate overlay;
* ``durable_location_registry_v1`` may satisfy the exact marker authority check
  when the event already satisfies every other V3 exact-pin invariant.

No weaker registry geometry is promoted: approximate durable locations remain
GENERAL_AREA/non-certified before this reader is invoked.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

try:
    from scripts import build_maplibre_reader_safe_v03 as reader
except ModuleNotFoundError:  # pragma: no cover
    import build_maplibre_reader_safe_v03 as reader  # type: ignore[no-redef]

DURABLE_AUTHORITY = "durable_location_registry_v1"
PROJECTOR_AUTHORITY = "projector_v3_semantic_map_decision"

reader.READER_VISIBLE_DISPOSITIONS = set(reader.READER_VISIBLE_DISPOSITIONS) | {"approximate_marker"}

_ORIGINAL_MARKER_ELIGIBILITY = reader.marker_eligibility
_ORIGINAL_FEATURE = reader.feature


def marker_eligibility_with_durable_reuse(event: dict[str, Any]) -> tuple[bool, str]:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    if nycif.get("location_authority") != DURABLE_AUTHORITY:
        return _ORIGINAL_MARKER_ELIGIBILITY(event)

    # Re-run the established V3 marker contract with only the authority token
    # translated. The source event is not mutated and every other gate remains
    # exactly the same: MAP_READY, certified, evidence, public role, standalone,
    # and finite coordinates are still required.
    candidate = deepcopy(event)
    candidate_nycif = candidate.setdefault("nycif", {})
    candidate_nycif["location_authority"] = PROJECTOR_AUTHORITY
    eligible, reason = _ORIGINAL_MARKER_ELIGIBILITY(candidate)
    return (eligible, "marker_ready_durable_reuse" if eligible else reason)


def feature_with_authority(event: dict[str, Any], *, exact_marker: bool) -> dict[str, Any]:
    result = _ORIGINAL_FEATURE(event, exact_marker=exact_marker)
    if exact_marker:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        authority = nycif.get("location_authority")
        if authority in {PROJECTOR_AUTHORITY, DURABLE_AUTHORITY}:
            result["properties"]["location_authority"] = authority
    return result


reader.marker_eligibility = marker_eligibility_with_durable_reuse
reader.feature = feature_with_authority

if __name__ == "__main__":
    raise SystemExit(reader.main())
