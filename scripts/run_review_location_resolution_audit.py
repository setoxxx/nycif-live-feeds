#!/usr/bin/env python3
"""Run remaining review-location resolution with bounded, memoized GeoSearch.

This wrapper changes only audit execution behavior. It preserves the underlying
resolver's confidence threshold and result schema, caches both successes and
failures for repeated queries, and lowers the live HTTP timeout so a temporary
GeoSearch outage cannot consume the entire review workflow.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    from scripts import resolve_remaining_review_locations as audit
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.nyc_location_resolver import (
        GEOSEARCH_BASE,
        NYCLocationResolver,
        ResolveResult,
        utc_now_iso,
    )
except ModuleNotFoundError:  # pragma: no cover
    import resolve_remaining_review_locations as audit
    from nyc_location_gazetteer import valid_nyc_lat_lng
    from nyc_location_resolver import GEOSEARCH_BASE, NYCLocationResolver, ResolveResult, utc_now_iso

AUDIT_HTTP_TIMEOUT_SEC = 4
AUDIT_REQUEST_DELAY_SEC = 0.05


class BoundedMemoizedResolver(NYCLocationResolver):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._audit_resolution_cache: dict[tuple[str, str | None, tuple[str, ...]], ResolveResult] = {}

    def resolve(
        self,
        *,
        display_location: str,
        borough: str | None = None,
        cache_keys: list[str] | None = None,
    ) -> ResolveResult:
        key = (
            str(display_location or "").strip().lower(),
            str(borough).strip().lower() if borough else None,
            tuple(cache_keys or []),
        )
        if key not in self._audit_resolution_cache:
            self._audit_resolution_cache[key] = super().resolve(
                display_location=display_location,
                borough=borough,
                cache_keys=cache_keys,
            )
        return self._audit_resolution_cache[key]

    def _geosearch_live(self, query: str) -> dict[str, Any] | None:
        params = urllib.parse.urlencode({"text": query, "size": 5})
        url = f"{GEOSEARCH_BASE}?{params}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "nycif-review-location-audit/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=AUDIT_HTTP_TIMEOUT_SEC) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
        self._live_calls += 1
        time.sleep(AUDIT_REQUEST_DELAY_SEC)
        for feature in payload.get("features") or []:
            coords = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coords) != 2:
                continue
            lng, lat = float(coords[0]), float(coords[1])
            if not valid_nyc_lat_lng(lat, lng):
                continue
            props = feature.get("properties") or {}
            confidence_score = float(props.get("confidence") or 0.0)
            if confidence_score < 0.5:
                continue
            return {
                "lat": lat,
                "lng": lng,
                "label": props.get("label") or props.get("name"),
                "confidence": "high" if confidence_score >= 0.75 else "medium",
                "confidence_reason": f"NYC GeoSearch match for query '{query}'.",
                "source": "nyc_geosearch_planninglabs",
                "query": query,
                "cached_at_utc": utc_now_iso(),
            }
        return None


audit.NYCLocationResolver = BoundedMemoizedResolver


if __name__ == "__main__":
    raise SystemExit(audit.main())
