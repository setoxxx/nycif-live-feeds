"""Pin every public TVPP street-permit row from official NYC sources.

Howard required tvpp-9vvx on the map every time. This resolver does not use
Google. It prefers Parks BigApps facility coordinates, official NYC DCP LION
centerline midpoints, NYC Geoclient blockface midpoints, then NYC Planning Labs
GeoSearch for remaining places.

Results are cached in data/tvpp_official_pin_cache.json. That file is not
location_cache.json and is not a public-map publish.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_geoclient_client import NYCGeoclientClient
    from scripts.nyc_location_gazetteer import simplified_place, valid_nyc_lat_lng
    from scripts.nyc_location_resolver import (
        coordinate_matches_borough,
        haversine_m,
        parse_street_between,
    )
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_geoclient_client import NYCGeoclientClient
    from nyc_location_gazetteer import simplified_place, valid_nyc_lat_lng
    from nyc_location_resolver import (
        coordinate_matches_borough,
        haversine_m,
        parse_street_between,
    )

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_PATH = DATA_DIR / "tvpp_official_pin_cache.json"
FACILITY_PATH = DATA_DIR / "nyc_parks_facility_reference.json"
LION_PATH = DATA_DIR / "reader-safe" / "street-segment-routes-v1.geojson"
GEOSEARCH_BASE = "https://geosearch.planninglabs.nyc/v2/search"
REQUEST_DELAY_SEC = 0.05
GEOSEARCH_RETRIES = 2

BETWEEN_IN_TEXT = re.compile(
    r"(?P<main>[A-Z0-9 .'-]+?)\s+between\s+(?P<cross1>.+?)\s+and\s+(?P<cross2>[^,]+)",
    flags=re.IGNORECASE,
)
AND_INTERSECTION = re.compile(
    r"^(?P<a>.+?)\s+(?:and|&)\s+(?P<b>.+)$",
    flags=re.IGNORECASE,
)
BOROUGH_TRAILING = re.compile(
    r"(?:,?\s+(?:manhattan|brooklyn|queens|the bronx|bronx|staten island)"
    r"(?:,?\s+n\.?y\.?)?)\s*$",
    flags=re.IGNORECASE,
)
NY_TRAILING = re.compile(r",?\s+n\.?y\.?\s*$", flags=re.IGNORECASE)
STREET_NUMBER = re.compile(
    r"^(?:(?P<dir>east|west|north|south)\s+)?(?P<num>\d+)\s+"
    r"(?P<kind>street|st|avenue|ave|road|rd|boulevard|blvd)\b",
    flags=re.IGNORECASE,
)


def _allow_live_geosearch() -> bool:
    return os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {"1", "true", "yes"}


def _allow_live_geoclient() -> bool:
    return os.environ.get("NYCIF_ALLOW_LIVE_GEOCLIENT", "").strip().lower() in {"1", "true", "yes"}


def tidy_street(name: str) -> str:
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    match = re.match(
        r"^(?P<dir>east|west|north|south)\s+(?P<num>\d+)\s+"
        r"(?P<kind>street|st|avenue|ave|road|rd|boulevard|blvd)\b(?P<rest>.*)$",
        text,
        flags=re.I,
    )
    if match:
        direction = match.group("dir").title()
        number = int(match.group("num"))
        return f"{direction} {_ordinal_street(number, match.group('kind'))}{match.group('rest')}"
    match = re.match(r"^(\d+)\s+(street|st|avenue|ave|road|rd|boulevard|blvd)\b(.*)$", text, flags=re.I)
    if not match:
        return text
    return f"{_ordinal_street(int(match.group(1)), match.group(2))}{match.group(3)}"


def _ordinal_street(number: int, kind: str) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    label = {
        "street": "Street",
        "st": "Street",
        "avenue": "Avenue",
        "ave": "Avenue",
        "road": "Road",
        "rd": "Road",
        "boulevard": "Boulevard",
        "blvd": "Boulevard",
    }[kind.lower()]
    return f"{number}{suffix} {label}"


def street_number(name: str) -> int | None:
    match = STREET_NUMBER.match(re.sub(r"\s+", " ", str(name or "")).strip())
    if not match:
        return None
    return int(match.group("num"))


def segment_identity(borough: str | None, main: str, cross1: str, cross2: str) -> str:
    crosses = tuple(sorted((normalize_text_legacy(cross1), normalize_text_legacy(cross2))))
    return "|".join(
        [
            normalize_text_legacy(borough or ""),
            normalize_text_legacy(main),
            crosses[0],
            crosses[1],
        ]
    )


def is_known_bad_si_dump(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    return abs(float(lat) - 40.533) < 0.0006 and abs(float(lng) + 74.2021) < 0.0006


def cache_key(display: str, borough: str | None) -> str:
    boro = normalize_text_legacy(borough or "")
    place = normalize_text_legacy(display)
    return f"{boro}|{place}" if boro else place


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@dataclass
class TvppPin:
    resolved: bool
    lat: float | None
    lng: float | None
    source: str
    confidence: str
    confidence_reason: str
    reason_code: str
    exact_pin_eligible: bool = False

    def evidence(self) -> dict[str, Any]:
        return {
            "exact_pin_eligible": self.exact_pin_eligible,
            "reason_code": self.reason_code,
            "geocoder_source": self.source,
            "geocoder_confidence": self.confidence,
            "confidence_reason": self.confidence_reason,
        }


UNRESOLVED = TvppPin(
    resolved=False,
    lat=None,
    lng=None,
    source="",
    confidence="",
    confidence_reason="TVPP location could not be pinned from Parks facilities, Geoclient, or GeoSearch.",
    reason_code="TVPP_UNRESOLVED",
    exact_pin_eligible=False,
)


def _pin(
    lat: float,
    lng: float,
    *,
    source: str,
    reason_code: str,
    reason: str,
    confidence: str = "high",
) -> TvppPin:
    return TvppPin(
        resolved=True,
        lat=round(float(lat), 7),
        lng=round(float(lng), 7),
        source=source,
        confidence=confidence,
        confidence_reason=reason,
        reason_code=reason_code,
        exact_pin_eligible=True,
    )


def _segments(display: str) -> list[str]:
    text = str(display or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\s*,\s*", text) if part.strip()]
    return parts or [text]


def _between_claim(text: str) -> tuple[str, str, str] | None:
    cleaned = clean_display_location(text)
    parsed = parse_street_between(cleaned)
    if parsed:
        main, cross1, cross2 = parsed
        return _collapse_spaces(main), _collapse_spaces(cross1), _collapse_spaces(cross2)
    match = BETWEEN_IN_TEXT.search(cleaned)
    if not match:
        return None
    return (
        _collapse_spaces(match.group("main")),
        _collapse_spaces(clean_display_location(match.group("cross1"))),
        _collapse_spaces(clean_display_location(match.group("cross2"))),
    )


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_display_location(display: str) -> str:
    """Drop trailing borough / NY tokens so LION and GeoSearch can parse the street."""
    text = _collapse_spaces(display)
    for _ in range(3):
        nxt = BOROUGH_TRAILING.sub("", text)
        nxt = NY_TRAILING.sub("", nxt).strip(" ,")
        if nxt == text:
            break
        text = nxt
    return text


def _intersection_claim(text: str) -> tuple[str, str] | None:
    cleaned = clean_display_location(text)
    if " between " in cleaned.casefold():
        return None
    match = AND_INTERSECTION.match(cleaned)
    if not match:
        return None
    left = _collapse_spaces(match.group("a"))
    right = _collapse_spaces(match.group("b"))
    if not left or not right:
        return None
    return left, right


def _flatten_line_coords(geometry: dict[str, Any] | None) -> list[list[float]]:
    if not isinstance(geometry, dict):
        return []
    kind = str(geometry.get("type") or "")
    raw = geometry.get("coordinates") or []
    if kind == "LineString" and isinstance(raw, list):
        return [point for point in raw if isinstance(point, list) and len(point) >= 2]
    if kind == "MultiLineString" and isinstance(raw, list):
        points: list[list[float]] = []
        for part in raw:
            if not isinstance(part, list):
                continue
            points.extend(point for point in part if isinstance(point, list) and len(point) >= 2)
        return points
    return []


def lion_line_midpoint(geometry: dict[str, Any] | None) -> tuple[float, float] | None:
    points = _flatten_line_coords(geometry)
    if not points:
        return None
    lng = (float(points[0][0]) + float(points[-1][0])) / 2.0
    lat = (float(points[0][1]) + float(points[-1][1])) / 2.0
    if not valid_nyc_lat_lng(lat, lng):
        return None
    return lat, lng


def build_lion_index(path: Path = LION_PATH) -> dict[str, dict[str, Any]]:
    payload = load_json(path, {})
    features = payload.get("features", []) if isinstance(payload, dict) else []
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(features, list):
        return index
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        midpoint = lion_line_midpoint(feature.get("geometry") if isinstance(feature.get("geometry"), dict) else None)
        if midpoint is None:
            continue
        location = str(props.get("location") or "").strip()
        borough = str(props.get("borough") or "").strip()
        entry = {
            "lat": midpoint[0],
            "lng": midpoint[1],
            "label": location,
            "segment_id": props.get("source_segment_id"),
        }
        if location:
            index.setdefault(cache_key(location, borough), entry)
        parsed = _between_claim(location) if location else None
        if parsed and borough:
            index.setdefault(segment_identity(borough, *parsed), entry)
    return index


def build_facility_index(path: Path = FACILITY_PATH) -> dict[str, dict[str, Any]]:
    payload = load_json(path, {})
    rows = payload.get("facilities", []) if isinstance(payload, dict) else payload
    index: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return index
    for row in rows:
        if not isinstance(row, dict) or not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
            continue
        entry = {
            "lat": float(row["lat"]),
            "lng": float(row["lng"]),
            "label": row.get("facility_name") or row.get("name") or row.get("display_location"),
        }
        for field in ("facility_name", "name", "place_name", "display_location"):
            token = simplified_place(str(row.get(field) or ""))
            if token:
                index.setdefault(token, entry)
            raw = normalize_text_legacy(row.get(field) or "")
            if raw:
                index.setdefault(raw, entry)
    return index


class TvppPinResolver:
    def __init__(
        self,
        facility_index: dict[str, dict[str, Any]],
        cache: dict[str, dict[str, Any]],
        *,
        geoclient: NYCGeoclientClient | None = None,
        allow_live_geosearch: bool | None = None,
        geosearch_fn: Any | None = None,
        lion_index: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.facility_index = facility_index
        self.cache = cache
        self.lion_index = lion_index if lion_index is not None else {}
        self.geoclient = geoclient or NYCGeoclientClient.load_default(allow_live=_allow_live_geoclient())
        self.allow_live_geosearch = (
            _allow_live_geosearch() if allow_live_geosearch is None else allow_live_geosearch
        )
        self.geosearch_fn = geosearch_fn or self._geosearch_live
        self.live_calls = 0

    @classmethod
    def load_default(cls) -> "TvppPinResolver":
        payload = load_json(CACHE_PATH, {})
        entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
        if not isinstance(entries, dict):
            entries = {}
        return cls(build_facility_index(), entries, lion_index=build_lion_index())

    def save_cache(self) -> None:
        save_json(
            CACHE_PATH,
            {
                "artifact_type": "tvpp_official_pin_cache",
                "entry_count": len(self.cache),
                "location_cache_modified": False,
                "staged_feed_modified": False,
                "public_map_modified": False,
                "promotion_allowed": False,
                "entries": self.cache,
            },
        )

    def _from_cache_entry(self, entry: dict[str, Any]) -> TvppPin | None:
        if not valid_nyc_lat_lng(entry.get("lat"), entry.get("lng")):
            return None
        if is_known_bad_si_dump(entry.get("lat"), entry.get("lng")):
            return None
        return _pin(
            float(entry["lat"]),
            float(entry["lng"]),
            source=str(entry.get("source") or "tvpp_official_pin_cache"),
            reason_code=str(entry.get("reason_code") or "TVPP_CACHE"),
            reason=str(entry.get("confidence_reason") or "Cached TVPP official pin."),
            confidence=str(entry.get("confidence") or "high"),
        )

    def _geosearch_live(self, query: str) -> dict[str, Any] | None:
        params = urllib.parse.urlencode({"text": query, "size": 5})
        url = f"{GEOSEARCH_BASE}?{params}"
        last_error: Exception | None = None
        for attempt in range(GEOSEARCH_RETRIES):
            try:
                raw = subprocess.check_output(
                    [
                        "curl",
                        "-sS",
                        "--max-time",
                        "8",
                        "-A",
                        "nycif-tvpp-pin-resolver/1.0",
                        url,
                    ],
                    timeout=10,
                )
                payload = json.loads(raw)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
                last_error = exc
                time.sleep(0.2 * (attempt + 1))
                continue
            self.live_calls += 1
            time.sleep(REQUEST_DELAY_SEC)
            if not isinstance(payload, dict):
                return None
            for feature in payload.get("features") or []:
                coords = (feature.get("geometry") or {}).get("coordinates") or []
                if len(coords) != 2:
                    continue
                lng, lat = float(coords[0]), float(coords[1])
                if not valid_nyc_lat_lng(lat, lng):
                    continue
                props = feature.get("properties") or {}
                confidence_score = float(props.get("confidence") or 0.0)
                if confidence_score < 0.4:
                    continue
                return {
                    "lat": lat,
                    "lng": lng,
                    "label": props.get("label") or props.get("name"),
                    "confidence": "high" if confidence_score >= 0.75 else "medium",
                }
            return None
        _ = last_error
        return None

    def _geosearch_point(self, query: str, borough: str | None) -> tuple[float, float] | None:
        if not query or not self.allow_live_geosearch:
            return None
        labeled = f"{query}, {borough}, NY" if borough else f"{query}, New York, NY"
        for candidate in (labeled, query):
            hit = self.geosearch_fn(candidate)
            if not hit:
                continue
            lat, lng = float(hit["lat"]), float(hit["lng"])
            if not valid_nyc_lat_lng(lat, lng):
                continue
            if borough and not coordinate_matches_borough(lat, lng, borough):
                continue
            return lat, lng
        return None

    def _lion(self, display: str, borough: str | None) -> TvppPin | None:
        keys = [cache_key(display, borough)]
        for segment in _segments(display):
            remainder = segment.split(":", 1)[-1].strip() if ":" in segment else segment
            parsed = _between_claim(remainder) or _between_claim(segment)
            if parsed:
                keys.append(segment_identity(borough, *parsed))
                keys.append(cache_key(segment, borough))
        for key in keys:
            hit = self.lion_index.get(key)
            if not hit:
                continue
            if not valid_nyc_lat_lng(hit.get("lat"), hit.get("lng")):
                continue
            return _pin(
                float(hit["lat"]),
                float(hit["lng"]),
                source="nyc_dcp_lion_centerline",
                reason_code="TVPP_LION_CENTERLINE_MIDPOINT",
                reason=f"Official NYC DCP LION centerline midpoint for '{hit.get('label') or display}'.",
            )
        return None

    def _facility_hit(self, hit: dict[str, Any], borough: str | None, reason: str) -> TvppPin | None:
        if is_known_bad_si_dump(hit.get("lat"), hit.get("lng")):
            return None
        if borough and not coordinate_matches_borough(hit["lat"], hit["lng"], borough):
            return None
        return _pin(
            hit["lat"],
            hit["lng"],
            source="nyc_parks_facility_reference",
            reason_code="TVPP_PARKS_FACILITY_OFFICIAL",
            reason=reason,
        )

    def _facility(self, display: str, borough: str | None = None) -> TvppPin | None:
        if _between_claim(display):
            return None
        candidates = [
            simplified_place(display),
            normalize_text_legacy(display.split(":", 1)[0] if ":" in display else display),
            normalize_text_legacy(display),
        ]
        for key in candidates:
            if not key:
                continue
            hit = self.facility_index.get(key)
            if hit:
                pin = self._facility_hit(
                    hit,
                    borough,
                    f"Official NYC Parks facility match for '{hit.get('label') or key}'.",
                )
                if pin:
                    return pin
        parent = simplified_place(display)
        if len(parent) >= 16:
            for key, hit in self.facility_index.items():
                if parent in key or key in parent:
                    pin = self._facility_hit(
                        hit,
                        borough,
                        f"Official NYC Parks facility substring match for '{parent}'.",
                    )
                    if pin:
                        return pin
        return None

    def _geoclient_midpoint(self, main: str, cross1: str, cross2: str, borough: str | None) -> TvppPin | None:
        if not borough:
            return None
        first = self.geoclient.resolve_intersection(main, cross1, borough)
        second = self.geoclient.resolve_intersection(main, cross2, borough)
        if not first or not second:
            return None
        try:
            lat1, lng1 = float(first["lat"]), float(first["lng"])
            lat2, lng2 = float(second["lat"]), float(second["lng"])
        except (TypeError, ValueError, KeyError):
            return None
        if not coordinate_matches_borough(lat1, lng1, borough) or not coordinate_matches_borough(lat2, lng2, borough):
            return None
        distance = haversine_m(lat1, lng1, lat2, lng2)
        if not 20.0 <= distance <= 5000.0:
            return None
        mid_lat = (lat1 + lat2) / 2.0
        mid_lng = (lng1 + lng2) / 2.0
        if not coordinate_matches_borough(mid_lat, mid_lng, borough):
            return None
        return _pin(
            mid_lat,
            mid_lng,
            source="nyc_geoclient_segment_midpoint",
            reason_code="SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED",
            reason=f"NYC Geoclient midpoint for {main} between {cross1} and {cross2}.",
        )

    def _geosearch_midpoint(self, main: str, cross1: str, cross2: str, borough: str | None) -> TvppPin | None:
        queries = [
            f"{tidy_street(main)} and {tidy_street(cross1)}",
            f"{main} and {cross1}",
            f"{tidy_street(main)} and {tidy_street(cross2)}",
            f"{main} and {cross2}",
        ]
        points: list[tuple[float, float]] = []
        for query in queries:
            point = self._geosearch_point(query, borough)
            if point is None or point in points:
                continue
            points.append(point)
            if len(points) == 2:
                break
        if len(points) < 2:
            return None
        first = points[0]
        second = points[1]
        distance = haversine_m(first[0], first[1], second[0], second[1])
        if first != second and not 20.0 <= distance <= 5000.0:
            second = first
        mid_lat = (first[0] + second[0]) / 2.0
        mid_lng = (first[1] + second[1]) / 2.0
        if not valid_nyc_lat_lng(mid_lat, mid_lng):
            return None
        return _pin(
            mid_lat,
            mid_lng,
            source="nyc_geosearch_segment_midpoint",
            reason_code="SEGMENT_GEOSEARCH_ENDPOINTS_VALIDATED",
            reason=f"NYC GeoSearch midpoint for {main} between {cross1} and {cross2}.",
        )

    def _block_address_queries(self, main: str, cross1: str, cross2: str, borough: str | None) -> list[str]:
        main_t = tidy_street(main)
        cross_t = tidy_street(cross1)
        n1 = street_number(cross1)
        n2 = street_number(cross2)
        main_n = street_number(main)
        boro = str(borough or "").strip().lower()
        queries: list[str] = []
        if boro == "queens" and n1 is not None:
            queries.append(f"{n1}-01 {main_t}")
            if n2 is not None:
                queries.append(f"{n2}-01 {main_t}")
        if n1 is not None and len(str(n1)) <= 2:
            queries.append(f"{n1}01 {main_t}")
            if main_n is not None:
                queries.append(f"{n1 * 100} {main_t}")
        if n1 is not None:
            queries.append(f"{n1} {main_t}")
        queries.extend([f"{main_t} and {cross_t}", f"{main} and {cross1}"])
        seen: set[str] = set()
        ordered: list[str] = []
        for query in queries:
            token = query.strip()
            if not token or token.lower() in seen:
                continue
            seen.add(token.lower())
            ordered.append(token)
        return ordered

    def _geosearch_street(self, main: str, cross1: str, cross2: str, borough: str | None) -> TvppPin | None:
        for query in self._block_address_queries(main, cross1, cross2, borough):
            point = self._geosearch_point(query, borough)
            if point is None:
                continue
            return _pin(
                point[0],
                point[1],
                source="nyc_geosearch_planninglabs",
                reason_code="TVPP_NYC_GEOSEARCH_STREET",
                reason=f"NYC GeoSearch street/address match for {main} between {cross1} and {cross2}.",
                confidence="medium",
            )
        return None

    def _street(self, display: str, borough: str | None) -> TvppPin | None:
        for segment in _segments(display):
            remainder = segment.split(":", 1)[-1].strip() if ":" in segment else segment
            parsed = _between_claim(remainder) or _between_claim(segment)
            if not parsed:
                continue
            main, cross1, cross2 = parsed
            hit = self._geoclient_midpoint(main, cross1, cross2, borough)
            if hit:
                return hit
            hit = self._geosearch_midpoint(main, cross1, cross2, borough)
            if hit:
                return hit
            hit = self._geosearch_street(main, cross1, cross2, borough)
            if hit:
                return hit
        intersection = _intersection_claim(display)
        if intersection:
            left, right = intersection
            point = self._geosearch_point(f"{tidy_street(left)} and {tidy_street(right)}", borough)
            if point is None:
                point = self._geosearch_point(f"{left} and {right}", borough)
            if point is not None:
                return _pin(
                    point[0],
                    point[1],
                    source="nyc_geosearch_planninglabs",
                    reason_code="TVPP_NYC_GEOSEARCH_STREET",
                    reason=f"NYC GeoSearch intersection match for {left} and {right}.",
                    confidence="medium",
                )
        return None

    def _parent_place(self, display: str) -> str:
        if ":" in display:
            return display.split(":", 1)[0].strip()
        return display.split(",")[0].strip()

    def _place_queries(self, display: str) -> list[str]:
        parent = self._parent_place(display)
        suffix = display.split(":", 1)[-1].strip() if ":" in display else ""
        suffix = re.sub(r"\([^)]*\)", " ", suffix)
        suffix = re.sub(r"[?]+", " ", suffix)
        suffix = _collapse_spaces(suffix)
        queries = [
            parent,
            parent.replace("&", "and"),
            re.sub(r"\s*&\s*", " ", parent),
            re.sub(r"beach\s*&\s*", "", parent, flags=re.I),
            suffix,
            re.sub(r"\bbays?\b.*", "", suffix, flags=re.I).strip(),
            display,
        ]
        in_place = re.search(r"\bin\s+(?P<place>[A-Za-z0-9 .'-]*Park)\b", display, flags=re.I)
        if in_place:
            queries.append(in_place.group("place"))
        alias_key = normalize_text_legacy(display)
        if alias_key in {
            "125th street and marginal street",
            "west 125th street and marginal street",
            "w 125th street and marginal street",
        }:
            queries.append("West Harlem Piers")
        seen: set[str] = set()
        ordered: list[str] = []
        for query in queries:
            token = _collapse_spaces(query)
            if len(token) < 6 or token.lower() in seen:
                continue
            seen.add(token.lower())
            ordered.append(token)
        return ordered

    def _sibling_parent_cache(self, display: str, borough: str | None) -> TvppPin | None:
        if ":" not in display:
            return None
        parent = normalize_text_legacy(self._parent_place(display))
        if len(parent) < 16:
            return None
        prefix = f"{normalize_text_legacy(borough or '')}|{parent}"
        for key, entry in self.cache.items():
            if key == cache_key(display, borough) or not str(key).startswith(prefix):
                continue
            hit = self._from_cache_entry(entry) if isinstance(entry, dict) else None
            if hit and (not borough or coordinate_matches_borough(hit.lat, hit.lng, borough)):
                return _pin(
                    float(hit.lat),
                    float(hit.lng),
                    source=hit.source or "tvpp_official_pin_cache",
                    reason_code="TVPP_PARENT_PLACE_CACHE",
                    reason=f"Reused official pin from the same parent place '{self._parent_place(display)}'.",
                    confidence=hit.confidence or "medium",
                )
        return None

    def _place(self, display: str, borough: str | None) -> TvppPin | None:
        for query in self._place_queries(display):
            point = self._geosearch_point(query, borough)
            if point is None:
                continue
            return _pin(
                point[0],
                point[1],
                source="nyc_geosearch_planninglabs",
                reason_code="TVPP_NYC_GEOSEARCH_PLACE",
                reason=f"NYC GeoSearch place match for '{query}'.",
                confidence="medium",
            )
        return None

    def resolve(self, display_location: str, borough: str | None = None) -> TvppPin:
        raw = str(display_location or "").strip()
        display = clean_display_location(raw)
        if not display:
            return UNRESOLVED
        key = cache_key(raw, borough)
        cleaned_key = cache_key(display, borough)
        for lookup in (key, cleaned_key):
            cached = self.cache.get(lookup)
            if isinstance(cached, dict):
                if _between_claim(display) and str(cached.get("source") or "").startswith("nyc_parks_facility"):
                    continue
                hit = self._from_cache_entry(cached)
                if hit and (not borough or coordinate_matches_borough(hit.lat, hit.lng, borough)):
                    return hit

        pin = self._lion(display, borough)
        if pin is None:
            pin = self._street(display, borough)
        if pin is None:
            pin = self._facility(display, borough)
        if pin is None:
            pin = self._sibling_parent_cache(display, borough)
        if pin is None:
            pin = self._place(display, borough)
        if pin is None:
            return UNRESOLVED
        self.cache[key] = {
            "lat": pin.lat,
            "lng": pin.lng,
            "source": pin.source,
            "confidence": pin.confidence,
            "confidence_reason": pin.confidence_reason,
            "reason_code": pin.reason_code,
            "exact_pin_eligible": True,
        }
        return pin


def fill_cache_from_tvpp_snapshot(path: Path | None = None) -> dict[str, Any]:
    from scripts.sync_supabase_official_source_catchup import TVPP_PATH

    snapshot = load_json(path or TVPP_PATH, [])
    rows = snapshot if isinstance(snapshot, list) else snapshot.get("events", [])
    resolver = TvppPinResolver.load_default()
    resolved = 0
    missed: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        display = str(row.get("event_location") or row.get("location") or "").strip()
        borough = str(row.get("event_borough") or row.get("borough") or "").strip()
        key = cache_key(display, borough)
        if not display or key in seen:
            continue
        seen.add(key)
        if key in resolver.cache and resolver._from_cache_entry(resolver.cache[key]):
            resolved += 1
            continue
        pin = resolver.resolve(display, borough)
        if pin.resolved:
            resolved += 1
            resolver.save_cache()
            print(f"pinned {resolved}/{len(seen)} {borough}|{display[:80]}", flush=True)
        else:
            missed.append({"borough": borough, "display_location": display[:180]})
    resolver.save_cache()
    if resolver.geoclient is not None:
        resolver.geoclient.save_cache()
    return {
        "unique_locations": len(seen),
        "resolved": resolved,
        "missed": len(missed),
        "miss_samples": missed[:25],
        "live_geosearch_calls": resolver.live_calls,
        "cache_path": str(CACHE_PATH),
    }


def main() -> int:
    report = fill_cache_from_tvpp_snapshot()
    print(json.dumps(report, indent=2))
    return 0 if report["missed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
