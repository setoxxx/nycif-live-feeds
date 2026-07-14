#!/usr/bin/env python3
"""Geocode unfilled GPS proposals using official NYC GeoSearch (staging only).

Uses NYC Planning GeoSearch API (Property Address Directory / Pelias):
https://geosearch.planninglabs.nyc/v2/search

Safety:
- Writes data/manual_gps_reference.json and data/gps_review_external_geocoder_report.json
- Does NOT modify location_cache.json or staged feeds
- Does NOT set promotion_allowed=true
- Does NOT publish to the public map

Re-run Phase 2C after this script:
  python3 scripts/build_gps_geocoding_filled_proposals.py
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        save_json_file,
        simplified_place,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        save_json_file,
        simplified_place,
        valid_nyc_lat_lng,
    )

UNFILLED_QUEUE = DATA_DIR / "gps_review_geocoding_unfilled_review_queue.json"
MANUAL_REFERENCE_PATH = DATA_DIR / "manual_gps_reference.json"
REPORT_PATH = DATA_DIR / "gps_review_external_geocoder_report.json"
GEOSEARCH_BASE = "https://geosearch.planninglabs.nyc/v2/search"
REQUEST_DELAY_SEC = 0.15


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_street(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").upper().strip())
    value = re.sub(r"\bEAST\s+(\d)", r"EAST \1", value)
    value = re.sub(r"\bWEST\s+(\d)", r"WEST \1", value)
    return value


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


def geosearch(text: str, size: int = 5) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"text": text, "size": size})
    url = f"{GEOSEARCH_BASE}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "nycif-live-feeds-geocoder/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []

    results: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        if not isinstance(feature, dict):
            continue
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coords) != 2:
            continue
        lng, lat = float(coords[0]), float(coords[1])
        if not valid_nyc_lat_lng(lat, lng):
            continue
        props = feature.get("properties") or {}
        results.append(
            {
                "label": props.get("label") or props.get("name"),
                "lat": lat,
                "lng": lng,
                "confidence": float(props.get("confidence") or 0.0),
                "query": text,
            }
        )
    return results


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def pick_best_result(
    results: list[dict[str, Any]],
    *,
    must_contain: str | None = None,
) -> dict[str, Any] | None:
    if not results:
        return None
    filtered = results
    if must_contain:
        token = simplified_place(must_contain)
        token_matches = [
            row
            for row in results
            if token and token in simplified_place(str(row.get("label") or ""))
        ]
        if token_matches:
            filtered = token_matches
    filtered.sort(key=lambda row: float(row.get("confidence") or 0.0), reverse=True)
    best = filtered[0]
    if float(best.get("confidence") or 0.0) < 0.5:
        return None
    return best


def geocode_park_subsite(row: dict[str, Any]) -> dict[str, Any] | None:
    display = str(row.get("display_location") or "")
    borough = borough_label(str(row.get("borough") or ""))
    parent = display.split(":")[0].strip()
    queries = [
        f"{parent}, {borough}, NY",
        f"{parent}, New York, NY",
        f"{simplified_place(parent)}, {borough}, NY",
    ]
    if "Open Street" in display:
        street = parent.replace("Open Street 2026", "").replace("Open Street", "").strip()
        queries.insert(0, f"{street}, {borough}, NY")

    for query in queries:
        hit = pick_best_result(geosearch(query), must_contain=parent)
        if hit:
            return {
                **hit,
                "geocoder_source": "nyc_geosearch_planninglabs",
                "geocoder_confidence": "high" if hit["confidence"] >= 0.75 else "medium",
                "confidence_reason": (
                    f"NYC GeoSearch match for '{hit['label']}' using query '{query}'. "
                    "Requires manual approval before promotion."
                ),
                "query_used": query,
            }
        time.sleep(REQUEST_DELAY_SEC)
    return None


def geocode_street_segment(row: dict[str, Any]) -> dict[str, Any] | None:
    display = str(row.get("display_location") or "")
    borough = borough_label(str(row.get("borough") or ""))
    parsed = parse_street_between(display)
    if not parsed:
        return None
    main_street, cross1, cross2 = parsed

    endpoint_queries = [
        f"1 {cross1}, {borough}, NY",
        f"1 {cross2}, {borough}, NY",
        f"100 {main_street}, {borough}, NY",
        f"1 {main_street}, {borough}, NY",
    ]
    points: list[tuple[float, float, str]] = []
    for query in endpoint_queries:
        hit = pick_best_result(geosearch(query))
        if hit:
            points.append((hit["lat"], hit["lng"], str(hit.get("label") or query)))
        time.sleep(REQUEST_DELAY_SEC)

    if len(points) >= 2:
        # Use the two points farthest apart as segment endpoints.
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
            lat = round((a[0] + b[0]) / 2.0, 7)
            lng = round((a[1] + b[1]) / 2.0, 7)
            if valid_nyc_lat_lng(lat, lng):
                return {
                    "label": f"Midpoint of open street segment ({display})",
                    "lat": lat,
                    "lng": lng,
                    "confidence": 0.7,
                    "geocoder_source": "nyc_geosearch_planninglabs_midpoint",
                    "geocoder_confidence": "medium",
                    "confidence_reason": (
                        f"Computed midpoint from NYC GeoSearch endpoints '{a[2]}' and '{b[2]}' "
                        f"for open street segment. Requires manual approval before promotion."
                    ),
                    "query_used": f"{cross1} / {cross2} on {main_street}",
                    "endpoint_labels": [a[2], b[2]],
                }

    fallback_query = f"{main_street}, {borough}, NY"
    hit = pick_best_result(geosearch(fallback_query), must_contain=main_street)
    if hit:
        return {
            **hit,
            "geocoder_source": "nyc_geosearch_planninglabs",
            "geocoder_confidence": "medium",
            "confidence_reason": (
                f"Fallback NYC GeoSearch match on main street '{main_street}'. "
                "Segment midpoint endpoints unavailable; requires manual approval."
            ),
            "query_used": fallback_query,
        }
    return None


def geocode_row(row: dict[str, Any]) -> dict[str, Any]:
    complexity = row.get("location_complexity")
    if complexity == "street_between_pair":
        fill = geocode_street_segment(row)
    else:
        fill = geocode_park_subsite(row)

    out = {
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "location_complexity": complexity,
        "event_count": row.get("event_count"),
        "priority_score": row.get("priority_score"),
        "geocoded": fill is not None,
        "lat": fill.get("lat") if fill else None,
        "lng": fill.get("lng") if fill else None,
        "geocoder_source": fill.get("geocoder_source") if fill else None,
        "geocoder_confidence": fill.get("geocoder_confidence") if fill else None,
        "confidence_reason": fill.get("confidence_reason") if fill else "No NYC GeoSearch match found.",
        "geocoder_label": fill.get("label") if fill else None,
        "query_used": fill.get("query_used") if fill else None,
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    return out


def reference_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "location_complexity": row.get("location_complexity"),
        "simplified_geocoder_query": row.get("display_location"),
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "confidence_reason": row.get("confidence_reason"),
        "geocoder_label": row.get("geocoder_label"),
        "query_used": row.get("query_used"),
        "manual_review_status": "pending",
        "promotion_allowed": False,
    }


def main() -> int:
    queue = load_json_file(UNFILLED_QUEUE, {})
    rows = queue.get("review_queue") if isinstance(queue, dict) else queue
    if not isinstance(rows, list):
        rows = []

    geocoded_rows = [geocode_row(row) for row in rows]
    filled = [row for row in geocoded_rows if row.get("geocoded")]
    unfilled = [row for row in geocoded_rows if not row.get("geocoded")]

    reference_payload = {
        "artifact_type": "manual_gps_reference",
        "generated_at_utc": utc_now_iso(),
        "source": "nyc_geosearch_external_geocoder_staging",
        "instructions": [
            "Coordinates generated by scripts/geocode_unfilled_gps_proposals.py using NYC GeoSearch.",
            "All rows remain manual_review_status=pending and promotion_allowed=false.",
            "Re-run scripts/build_gps_geocoding_filled_proposals.py after human spot-check.",
        ],
        "references": [reference_entry(row) for row in filled],
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
        },
    }

    report = {
        "generated_at_utc": utc_now_iso(),
        "phase": "external_geocoder_staging",
        "geocoder": "nyc_geosearch_planninglabs",
        "input_count": len(rows),
        "geocoded_count": len(filled),
        "unfilled_count": len(unfilled),
        "confidence_counts": {},
        "geocoded_rows": filled,
        "unfilled_rows": unfilled,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed_count": 0,
        "next_required_step": (
            "Spot-check geocoded coordinates, then run build_gps_geocoding_filled_proposals.py. "
            "Do not promote until manual approval."
        ),
    }
    confidence_counts: dict[str, int] = {}
    for row in filled:
        key = str(row.get("geocoder_confidence") or "unknown")
        confidence_counts[key] = confidence_counts.get(key, 0) + 1
    report["confidence_counts"] = confidence_counts

    save_json_file(MANUAL_REFERENCE_PATH, reference_payload)
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
