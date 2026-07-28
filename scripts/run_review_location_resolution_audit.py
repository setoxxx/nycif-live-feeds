#!/usr/bin/env python3
"""Run remaining review-location resolution with exact, bounded GeoSearch.

This wrapper changes only audit execution behavior. Each extracted candidate is
looked up exactly once, successes and failures are memoized, and live requests
use a short timeout. Broad resolver fallbacks are intentionally disabled here.
Live results must also share a distinctive place/address token with the query
before official NYC borough-polygon validation can accept the coordinate.
"""

from __future__ import annotations

import json
import re
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

AUDIT_HTTP_TIMEOUT_SEC = 2
AUDIT_REQUEST_DELAY_SEC = 0.02

GENERIC_LOCATION_TOKENS = {
    "at",
    "avenue",
    "ave",
    "boulevard",
    "bridge",
    "bronx",
    "brooklyn",
    "center",
    "centre",
    "ctr",
    "field",
    "gym",
    "gymnasium",
    "island",
    "lot",
    "manhattan",
    "multi",
    "new",
    "ny",
    "park",
    "parking",
    "playground",
    "pool",
    "queens",
    "recreation",
    "road",
    "room",
    "staten",
    "street",
    "the",
    "under",
    "use",
    "usa",
    "york",
}


def normalized_semantic_tokens(value: Any) -> set[str]:
    text = str(value or "").lower()
    text = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", r"\1", text)
    text = re.sub(r"\bst\.?\s+(?=[a-z])", "saint ", text)
    tokens = set(re.findall(r"[a-z0-9]+", text))
    return {
        token
        for token in tokens
        if token not in GENERIC_LOCATION_TOKENS and (len(token) >= 3 or token.isdigit())
    }


def labels_semantically_agree(query: Any, label: Any) -> bool:
    query_tokens = normalized_semantic_tokens(query)
    label_tokens = normalized_semantic_tokens(label)
    return bool(query_tokens and label_tokens and query_tokens.intersection(label_tokens))


class BoundedMemoizedResolver(NYCLocationResolver):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._audit_resolution_cache: dict[tuple[str, str | None, tuple[str, ...]], ResolveResult] = {}

    @staticmethod
    def _unresolved(reason: str) -> ResolveResult:
        return ResolveResult(
            resolved=False,
            tier="unresolved",
            lat=None,
            lng=None,
            source=None,
            confidence=None,
            confidence_reason=reason,
        )

    def resolve(
        self,
        *,
        display_location: str,
        borough: str | None = None,
        cache_keys: list[str] | None = None,
    ) -> ResolveResult:
        display = str(display_location or "").strip()
        key = (
            display.lower(),
            str(borough).strip().lower() if borough else None,
            tuple(cache_keys or []),
        )
        cached_result = self._audit_resolution_cache.get(key)
        if cached_result is not None:
            return cached_result

        if not display:
            result = self._unresolved("Missing display_location.")
            self._audit_resolution_cache[key] = result
            return result

        for cache_key in cache_keys or []:
            hit = self.gazetteer.lookup(cache_key)
            if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
                result = self._from_entry("tier_1_location_cache_key", hit)
                result.label = result.label or display
                result.query_used = display
                self._audit_resolution_cache[key] = result
                return result

        hit = self.gazetteer.lookup_display(display, borough)
        if hit and valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
            result = self._from_entry("tier_1_gazetteer_display", hit)
            result.label = result.label or display
            result.query_used = display
            self._audit_resolution_cache[key] = result
            return result

        result = self._resolve_geosearch(display, borough)
        if result is None:
            result = self._unresolved("No exact, semantically matching NYC GeoSearch result for the extracted candidate.")
            result.query_used = display
        else:
            result.label = result.label or display
            result.query_used = display
        self._audit_resolution_cache[key] = result
        return result

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
            label = props.get("label") or props.get("name")
            if not labels_semantically_agree(query, label):
                continue
            return {
                "lat": lat,
                "lng": lng,
                "label": label,
                "confidence": "high" if confidence_score >= 0.75 else "medium",
                "confidence_reason": (
                    f"Exact NYC GeoSearch match for query '{query}' with distinctive place/address token agreement."
                ),
                "source": "nyc_geosearch_planninglabs",
                "query": query,
                "cached_at_utc": utc_now_iso(),
            }
        return None


_original_resolve_payload = audit.resolve_payload


def _resolve_payload_with_run_metadata(*args: Any, **kwargs: Any):
    final_report, final_payload = _original_resolve_payload(*args, **kwargs)
    final_report["allow_live_geosearch"] = bool(kwargs.get("allow_live"))
    return final_report, final_payload


audit.NYCLocationResolver = BoundedMemoizedResolver
audit.resolve_payload = _resolve_payload_with_run_metadata


if __name__ == "__main__":
    raise SystemExit(audit.main())
