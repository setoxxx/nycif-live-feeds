"""Tiered NYC location resolver for permit and GPS review rows."""

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

    def as_match_dict(self) -> dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "display_location": self.label,
            "geocoder_source": self.source,
            "geocoder_confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
            "resolver_tier": self.tier,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


class NYCLocationResolver:
    """Tiered public resolver: gazetteer (+ supplemental overlay) → geosearch cache → live geosearch."""

    def __init__(
        self,
        gazetteer: NYCLocationGazetteer,
        geosearch_cache: dict[str, dict[str, Any]],
        *,
        allow_live_geosearch: bool = False,
    ) -> None:
        self.gazetteer = gazetteer
        self.geosearch_cache = geosearch_cache
        self.allow_live_geosearch = allow_live_geosearch
        self._live_calls = 0

    @classmethod
    def load_default(cls) -> NYCLocationResolver:
        allow_live = os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
        cache_payload = load_json(GEOSEARCH_CACHE_PATH, {})
        entries = cache_payload.get("entries", {}) if isinstance(cache_payload, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        return cls(gazetteer, entries, allow_live_geosearch=allow_live)

    def _from_entry(self, tier: str, entry: dict[str, Any]) -> ResolveResult:
        return ResolveResult(
            resolved=True,
            tier=tier,
            lat=float(entry["lat"]),
            lng=float(entry["lng"]),
            source=str(entry.get("source") or tier),
            confidence=str(entry.get("confidence") or "medium"),
            confidence_reason=str(entry.get("confidence_reason") or f"Matched via {tier}."),
            label=entry.get("label"),
        )

    def _cache_key(self, query: str, borough: str | None = None) -> str:
        return f"{borough_norm(borough)}|{normalize_text_legacy(query)}" if borough else normalize_text_legacy(query)

    def _geosearch_live(self, query: str) -> dict[str, Any] | None:
        params = urllib.parse.urlencode({"text": query, "size": 5})
        url = f"{GEOSEARCH_BASE}?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "nycif-location-resolver/1.0"})
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
        )

    def _resolve_street_segment(self, display: str, borough: str | None) -> ResolveResult | None:
        parsed = parse_street_between(display)
        if not parsed:
            return None
        main_street, cross1, cross2 = parsed
        borough_name = borough_label(str(borough or ""))
        endpoint_queries = [
            f"1 {cross1}, {borough_name}, NY",
            f"1 {cross2}, {borough_name}, NY",
            f"100 {main_street}, {borough_name}, NY",
        ]
        points: list[tuple[float, float, str]] = []
        for query in endpoint_queries:
            hit = self._resolve_geosearch(query, borough)
            if hit and hit.lat is not None and hit.lng is not None:
                points.append((hit.lat, hit.lng, hit.label or query))
        if len(points) >= 2:
            best_pair = None
            best_distance = -1.0
            for i, a in enumerate(points):
                for b in points[i + 1 :]:
                    distance = haversine_m(a[0], a[1], b[0], b[1])
                    if distance > best_distance:
                        best_distance = distance
                        best_pair = (a, b)
            if best_pair and best_distance >= 20.0:
                a, b = best_pair
                return ResolveResult(
                    resolved=True,
                    tier="tier_2_geosearch_midpoint",
                    lat=round((a[0] + b[0]) / 2.0, 7),
                    lng=round((a[1] + b[1]) / 2.0, 7),
                    source="nyc_geosearch_planninglabs_midpoint",
                    confidence="medium",
                    confidence_reason=(
                        f"Midpoint from GeoSearch endpoints '{a[2]}' and '{b[2]}' for open street segment."
                    ),
                    label=display,
                    query_used=f"{cross1} / {cross2} on {main_street}",
                )
        return self._resolve_geosearch(f"{main_street}, {borough_name}, NY", borough)

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

        if parse_street_between(display):
            street = self._resolve_street_segment(display, borough)
            if street:
                return street

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
