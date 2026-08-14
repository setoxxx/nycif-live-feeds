"""Tiered NYC location resolver for permit and GPS review rows.

Resolver success is evidence, not publication authority. Callers must not treat a
returned coordinate as an exact public pin unless exact_pin_eligible is true.
Street-segment resolution is fail-closed: no generic street-name fallback may
stand in for a certified segment. Exact street-segment publication requires an
explicit certified reference or two borough-valid NYC Geoclient intersections.
Planning Labs GeoSearch remains candidate evidence for non-segment lookups; it is
not authoritative enough to certify a TVPP-style street segment.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_geoclient_client import NYCGeoclientClient
    from scripts.nyc_location_gazetteer import (
        GEOSEARCH_CACHE_PATH,
        GAZETTEER_PATH,
        NYCLocationGazetteer,
        borough_norm,
        load_json,
        simplified_place,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_geoclient_client import NYCGeoclientClient
    from nyc_location_gazetteer import (
        GEOSEARCH_CACHE_PATH,
        GAZETTEER_PATH,
        NYCLocationGazetteer,
        borough_norm,
        load_json,
        simplified_place,
        valid_nyc_lat_lng,
    )

GEOSEARCH_BASE = "https://geosearch.planninglabs.nyc/v2/search"
REQUEST_DELAY_SEC = 0.12

BOROUGH_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "bronx": (40.77, 40.93, -73.95, -73.74),
    "brooklyn": (40.55, 40.75, -74.06, -73.82),
    "manhattan": (40.67, 40.89, -74.05, -73.90),
    "queens": (40.53, 40.82, -73.98, -73.69),
    "staten island": (40.47, 40.66, -74.27, -74.03),
}

# Permanent certified segment references. These are evidence-backed exceptions,
# not a generic fallback mechanism.
CERTIFIED_SEGMENT_MIDPOINTS: dict[tuple[str, str], tuple[float, float]] = {
    (
        "brooklyn",
        "east 74 street between avenue u and avenue t",
    ): (40.618, -73.905),
}


@dataclass
class ResolveResult:
    resolved: bool
    tier: str
    lat: float | None
    lng: float | None
    source: str | None
    confidence: str | None
    confidence_reason: str | None
    label: str | None = None
    query_used: str | None = None
    validation_state: str = "unvalidated"
    exact_pin_eligible: bool = False
    reason_code: str | None = None
    reason_detail: str | None = None

    def as_match_dict(self) -> dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "display_location": self.label,
            "geocoder_source": self.source,
            "geocoder_confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "resolver_tier": self.tier,
            "validation_state": self.validation_state,
            "exact_pin_eligible": self.exact_pin_eligible,
            "reason_code": self.reason_code,
            "reason_detail": self.reason_detail,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def parse_street_between(display: str) -> tuple[str, str, str] | None:
    match = re.match(
        r"^(?P<main>.+?)\s+between\s+(?P<cross1>.+?)\s+and\s+(?P<cross2>.+)$",
        str(display or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("main").strip(), match.group("cross1").strip(), match.group("cross2").strip()


def borough_label(borough: str) -> str:
    mapping = {
        "manhattan": "New York",
        "brooklyn": "Brooklyn",
        "bronx": "Bronx",
        "queens": "Queens",
        "staten island": "Staten Island",
    }
    return mapping.get(str(borough or "").strip().lower(), str(borough or "New York"))


def coordinate_matches_borough(lat: float, lng: float, borough: str | None) -> bool:
    bounds = BOROUGH_BOUNDS.get(normalized_text(borough))
    if bounds is None:
        return False
    min_lat, max_lat, min_lng, max_lng = bounds
    return min_lat <= float(lat) <= max_lat and min_lng <= float(lng) <= max_lng


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def intersection_query_variants(main_street: str, cross_street: str) -> list[str]:
    return [
        f"{main_street} and {cross_street}",
        f"{main_street} & {cross_street}",
        f"{cross_street} and {main_street}",
        f"{cross_street} & {main_street}",
        f"{main_street} at {cross_street}",
    ]


class NYCLocationResolver:
    """Tiered resolver with fail-closed exact-location authority."""

    def __init__(
        self,
        gazetteer: NYCLocationGazetteer,
        geosearch_cache: dict[str, dict[str, Any]],
        *,
        allow_live_geosearch: bool = False,
        geoclient: NYCGeoclientClient | None = None,
    ) -> None:
        self.gazetteer = gazetteer
        self.geosearch_cache = geosearch_cache
        self.allow_live_geosearch = allow_live_geosearch
        self.geoclient = geoclient or NYCGeoclientClient.load_default(
            allow_live=os.environ.get("NYCIF_ALLOW_LIVE_GEOCLIENT", "").strip().lower()
            in {"1", "true", "yes"}
        )
        self._live_calls = 0

    @classmethod
    def load_default(cls) -> "NYCLocationResolver":
        allow_live = os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        allow_live_geoclient = os.environ.get("NYCIF_ALLOW_LIVE_GEOCLIENT", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
        cache_payload = load_json(GEOSEARCH_CACHE_PATH, {})
        entries = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        return cls(
            gazetteer,
            entries,
            allow_live_geosearch=allow_live,
            geoclient=NYCGeoclientClient.load_default(allow_live=allow_live_geoclient),
        )

    def _from_entry(self, tier: str, entry: dict[str, Any]) -> ResolveResult:
        return ResolveResult(
            resolved=True,
            tier=tier,
            lat=float(entry["lat"]),
            lng=float(entry["lng"]),
            source=str(entry.get("source") or tier),
            confidence=str(entry.get("confidence") or "medium"),
            confidence_reason=str(entry.get("confidence_reason") or f"Matched via {tier}."),
            label=entry.get("label") or entry.get("display_location"),
            validation_state=str(entry.get("validation_state") or "unvalidated"),
            exact_pin_eligible=bool(entry.get("exact_pin_eligible", False)),
            reason_code=entry.get("reason_code"),
            reason_detail=entry.get("reason_detail"),
        )

    def _cache_key(self, query: str, borough: str | None = None) -> str:
        return f"{borough_norm(borough)}|{normalize_text_legacy(query)}" if borough else normalize_text_legacy(query)

    def _geosearch_live(self, query: str) -> dict[str, Any] | None:
        params = urllib.parse.urlencode({"text": query, "size": 5})
        url = f"{GEOSEARCH_BASE}?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "nycif-location-resolver/1.2"})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None
        self._live_calls += 1
        time.sleep(REQUEST_DELAY_SEC)
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
            }
        return None

    def _resolve_geosearch(self, query: str, borough: str | None = None) -> ResolveResult | None:
        key = self._cache_key(query, borough)
        cached = self.geosearch_cache.get(key) or self.gazetteer.lookup(key)
        if cached and valid_nyc_lat_lng(cached.get("lat"), cached.get("lng")):
            result = self._from_entry("tier_2_geosearch_cache", cached)
            result.query_used = query
            return result
        if not self.allow_live_geosearch:
            return None
        live = self._geosearch_live(query if borough is None else f"{query}, {borough_label(str(borough))}, NY")
        if not live:
            return None
        self.geosearch_cache[key] = {
            **live,
            "borough": borough,
            "cached_at_utc": utc_now_iso(),
        }
        return ResolveResult(
            resolved=True,
            tier="tier_3_nyc_geosearch_live",
            lat=float(live["lat"]),
            lng=float(live["lng"]),
            source=str(live.get("source")),
            confidence=str(live.get("confidence")),
            confidence_reason=str(live.get("confidence_reason")),
            label=live.get("label"),
            query_used=query,
            validation_state="unvalidated",
            exact_pin_eligible=False,
            reason_code="GEOCODER_RESULT_UNVALIDATED",
            reason_detail="GeoSearch returned a candidate coordinate; semantic validation is still required.",
        )

    def _resolve_geoclient_endpoint(
        self,
        main_street: str,
        cross_street: str,
        borough: str | None,
    ) -> tuple[float, float, str] | None:
        if not borough or self.geoclient is None:
            return None
        hit = self.geoclient.resolve_intersection(main_street, cross_street, borough)
        if not isinstance(hit, dict):
            return None
        try:
            lat = float(hit.get("lat"))
            lng = float(hit.get("lng"))
        except (TypeError, ValueError):
            return None
        if not valid_nyc_lat_lng(lat, lng) or not coordinate_matches_borough(lat, lng, borough):
            return None
        source = str(hit.get("geocoder_source") or "")
        if source != "nyc_geoclient_intersection":
            return None
        return lat, lng, str(hit.get("geoclient_label") or f"{main_street} & {cross_street}")

    def _certified_segment_reference(self, display: str, borough: str | None) -> ResolveResult | None:
        key = (normalized_text(borough), normalized_text(display))
        point = CERTIFIED_SEGMENT_MIDPOINTS.get(key)
        if point is None:
            return None
        lat, lng = point
        if not coordinate_matches_borough(lat, lng, borough):
            return None
        return ResolveResult(
            resolved=True,
            tier="certified_street_segment",
            lat=lat,
            lng=lng,
            source="nycif_certified_segment_midpoint",
            confidence="high",
            confidence_reason="Explicit NYCIF certified segment midpoint.",
            label=display,
            query_used=display,
            validation_state="validated",
            exact_pin_eligible=True,
            reason_code="SEGMENT_CERTIFIED_REFERENCE",
            reason_detail="Explicit certified segment reference passed borough containment.",
        )

    def _resolve_street_segment(self, display: str, borough: str | None) -> ResolveResult | None:
        parsed = parse_street_between(display)
        if not parsed:
            return None

        certified = self._certified_segment_reference(display, borough)
        if certified is not None:
            return certified

        main_street, cross1, cross2 = parsed
        first = self._resolve_geoclient_endpoint(main_street, cross1, borough)
        second = self._resolve_geoclient_endpoint(main_street, cross2, borough)
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
            tier="certified_street_segment",
            lat=midpoint_lat,
            lng=midpoint_lng,
            source="nyc_geoclient_segment_midpoint",
            confidence="high",
            confidence_reason=(
                f"Midpoint from borough-valid NYC Geoclient intersections '{first[2]}' and '{second[2]}'."
            ),
            label=display,
            query_used=f"{main_street} & {cross1} / {main_street} & {cross2}",
            validation_state="validated",
            exact_pin_eligible=True,
            reason_code="SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED",
            reason_detail=(
                "Both stated blockface endpoints were independently resolved by NYC Geoclient, "
                "passed borough containment, and produced a sane segment midpoint."
            ),
        )

    def resolve(
        self,
        *,
        display_location: str,
        borough: str | None = None,
        cache_keys: list[str] | None = None,
    ) -> ResolveResult:
        display = str(display_location or "").strip()
        if not display:
            return ResolveResult(
                resolved=False,
                tier="unresolved",
                lat=None,
                lng=None,
                source=None,
                confidence=None,
                confidence_reason="Missing display_location.",
                validation_state="invalid",
                reason_code="MISSING_EVIDENCE",
                reason_detail="No display location was supplied.",
            )

        for key in cache_keys or []:
            hit = self.gazetteer.lookup(key)
            if hit:
                result = self._from_entry("tier_1_location_cache_key", hit)
                result.label = result.label or display
                return result

        hit = self.gazetteer.lookup_display(display, borough)
        if hit:
            result = self._from_entry("tier_1_gazetteer_display", hit)
            result.label = result.label or display
            return result

        # Street-segment claims are special: if NYC authoritative endpoint
        # evidence cannot certify the blockface, stop. Never continue into generic
        # display/street/neighborhood GeoSearch.
        if parse_street_between(display):
            street = self._resolve_street_segment(display, borough)
            if street:
                return street
            return ResolveResult(
                resolved=False,
                tier="unresolved",
                lat=None,
                lng=None,
                source=None,
                confidence=None,
                confidence_reason="Street segment could not be certified from authoritative endpoint evidence.",
                label=display,
                query_used=display,
                validation_state="invalid",
                exact_pin_eligible=False,
                reason_code="SEGMENT_UNCERTIFIED",
                reason_detail=(
                    "No explicit certified segment reference or two borough-valid NYC Geoclient "
                    "endpoint intersections were available."
                ),
            )

        parent = display.split(":")[0].strip() if ":" in display else display
        for query in (display, parent, simplified_place(display), simplified_place(parent)):
            if not query:
                continue
            geosearch_hit = self._resolve_geosearch(query, borough)
            if geosearch_hit:
                geosearch_hit.label = geosearch_hit.label or display
                return geosearch_hit

        return ResolveResult(
            resolved=False,
            tier="unresolved",
            lat=None,
            lng=None,
            source=None,
            confidence=None,
            confidence_reason="No gazetteer or GeoSearch match.",
            label=display,
            validation_state="invalid",
            exact_pin_eligible=False,
            reason_code="MISSING_EVIDENCE",
            reason_detail="No usable candidate location evidence was found.",
        )

    def save_geosearch_cache(self) -> None:
        GEOSEARCH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact_type": "nyc_geosearch_gazetteer_cache",
            "generated_at_utc": utc_now_iso(),
            "entry_count": len(self.geosearch_cache),
            "entries": self.geosearch_cache,
            "safety": {
                "public_map_modified": False,
                "location_cache_modified": False,
                "promotion_allowed": False,
            },
        }
        with GEOSEARCH_CACHE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
