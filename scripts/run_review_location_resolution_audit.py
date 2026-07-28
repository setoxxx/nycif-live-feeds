#!/usr/bin/env python3
"""Run remaining review-location resolution with exact, bounded GeoSearch.

Each extracted candidate is looked up exactly once, successes and failures are
memoized, and live results must share a distinctive place/address token with
the query before official NYC borough-polygon validation can accept them.
Locations stated as "main street between cross street A and cross street B" are
resolved only when both endpoint intersections and their midpoint validate
inside the declared borough.
"""

from __future__ import annotations

import json
import math
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
MIN_SEGMENT_LENGTH_M = 10.0
MAX_SEGMENT_LENGTH_M = 5000.0

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

BETWEEN_RE = re.compile(
    r"^(?P<main>.+?)\s+between\s+(?P<cross1>.+?)\s+and\s+(?P<cross2>.+)$",
    flags=re.IGNORECASE,
)
BOROUGH_SUFFIX_RE = re.compile(
    r"\s+(?P<borough>Manhattan|Brooklyn|Queens|Bronx|Staten Island)\s*$",
    flags=re.IGNORECASE,
)


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


def parse_street_segment(value: Any) -> tuple[str, str, str, str | None] | None:
    first = str(value or "").split("|")[0].strip()
    if not first:
        return None
    suffix = BOROUGH_SUFFIX_RE.search(first)
    borough = audit.canonical_borough(suffix.group("borough")) if suffix else None
    if suffix:
        first = first[: suffix.start()].strip()
    match = BETWEEN_RE.match(first)
    if not match:
        return None
    main = match.group("main").strip(" ,.")
    cross1 = match.group("cross1").strip(" ,.")
    cross2 = match.group("cross2").strip(" ,.")
    if not main or not cross1 or not cross2:
        return None
    return main, cross1, cross2, borough


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(value))


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


def resolve_street_segment_proposal(
    proposal: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
    resolver: NYCLocationResolver,
) -> dict[str, Any] | None:
    if proposal.get("disposition") != "unresolved":
        return None
    if valid_nyc_lat_lng(proposal.get("existing_latitude"), proposal.get("existing_longitude")):
        return None
    parsed = parse_street_segment(proposal.get("location"))
    if not parsed:
        return None
    main, cross1, cross2, suffix_borough = parsed
    proposed_borough = audit.canonical_borough(proposal.get("proposed_borough")) or suffix_borough
    if not proposed_borough:
        return None

    query1 = f"{main} and {cross1}"
    query2 = f"{main} and {cross2}"
    first = resolver.resolve(display_location=query1, borough=proposed_borough)
    second = resolver.resolve(display_location=query2, borough=proposed_borough)
    if not first.resolved or first.lat is None or first.lng is None:
        return None
    if not second.resolved or second.lat is None or second.lng is None:
        return None

    first_borough = audit.borough_for_point(boundaries, float(first.lat), float(first.lng))
    second_borough = audit.borough_for_point(boundaries, float(second.lat), float(second.lng))
    if first_borough != proposed_borough or second_borough != proposed_borough:
        return None
    segment_length = haversine_m(float(first.lat), float(first.lng), float(second.lat), float(second.lng))
    if not (MIN_SEGMENT_LENGTH_M <= segment_length <= MAX_SEGMENT_LENGTH_M):
        return None

    midpoint_lat = round((float(first.lat) + float(second.lat)) / 2.0, 7)
    midpoint_lng = round((float(first.lng) + float(second.lng)) / 2.0, 7)
    midpoint_borough = audit.borough_for_point(boundaries, midpoint_lat, midpoint_lng)
    if midpoint_borough != proposed_borough:
        return None

    out = dict(proposal)
    out.update(
        {
            "disposition": "mapped_from_street_segment_endpoints",
            "proposed_borough": proposed_borough,
            "proposed_latitude": midpoint_lat,
            "proposed_longitude": midpoint_lng,
            "pin_eligible": True,
            "confidence": "high",
            "reason": (
                "Both stated street-segment endpoint intersections and their midpoint fall inside "
                "the declared official NYC borough polygon."
            ),
            "street_segment_main": main,
            "street_segment_cross_streets": [cross1, cross2],
            "street_segment_endpoint_queries": [query1, query2],
            "street_segment_endpoint_labels": [first.label, second.label],
            "street_segment_length_m": round(segment_length, 1),
            "evidence_source": "nyc_geosearch_segment_endpoints_plus_dcp_borough_boundary",
            "official_boundary_borough": midpoint_borough,
        }
    )
    return out


_original_resolve_one = audit.resolve_one
_original_resolve_payload = audit.resolve_payload


def _resolve_one_with_street_segments(
    proposal: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
    gazetteer: Any,
    resolver: NYCLocationResolver,
):
    street = resolve_street_segment_proposal(
        proposal,
        boundaries=boundaries,
        resolver=resolver,
    )
    if street is not None:
        return street, True
    return _original_resolve_one(
        proposal,
        boundaries=boundaries,
        gazetteer=gazetteer,
        resolver=resolver,
    )


def _resolve_payload_with_run_metadata(*args: Any, **kwargs: Any):
    final_report, final_payload = _original_resolve_payload(*args, **kwargs)
    final_report["allow_live_geosearch"] = bool(kwargs.get("allow_live"))
    return final_report, final_payload


audit.NYCLocationResolver = BoundedMemoizedResolver
audit.resolve_one = _resolve_one_with_street_segments
audit.resolve_payload = _resolve_payload_with_run_metadata


if __name__ == "__main__":
    raise SystemExit(audit.main())
