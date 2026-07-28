#!/usr/bin/env python3
"""Resolve review street segments from the current official NYC DCP LION node layer.

The legacy LION line feature endpoint can be redeployed independently of the
current node layer. This audit-only resolver queries the current LION_Node
FeatureServer directly by the two stated street names for each endpoint,
verifies the returned VIntersect label locally, and accepts a segment midpoint
only when both endpoints and the midpoint fall inside the declared official DCP
borough polygon.

No feed, cache, WordPress page, or public map surface is modified.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.audit_review_location_coverage import canonical_borough
    from scripts.resolve_remaining_review_locations import borough_for_point, load_boundaries
    from scripts.resolve_review_locations_from_lion import (
        MAX_PAIR_DISTANCE_M,
        MIN_PAIR_DISTANCE_M,
        normalized_words,
        parse_segment_location,
        street_variants,
    )
    from scripts.schema_v1_common import utc_now
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from audit_review_location_coverage import canonical_borough
    from resolve_remaining_review_locations import borough_for_point, load_boundaries
    from resolve_review_locations_from_lion import (
        MAX_PAIR_DISTANCE_M,
        MIN_PAIR_DISTANCE_M,
        normalized_words,
        parse_segment_location,
        street_variants,
    )
    from schema_v1_common import utc_now

LION_NODE_QUERY_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "LION_Node/FeatureServer/0/query"
)
LION_NODE_LAYER_URL = (
    "https://services5.arcgis.com/GfwWNkhOj9bNBqoJ/arcgis/rest/services/"
    "LION_Node/FeatureServer/0"
)
HTTP_TIMEOUT_SEC = 25
REQUEST_DELAY_SEC = 0.05
MAX_NODE_RESULTS = 16000

GENERIC_QUERY_WORDS = {
    "E",
    "W",
    "N",
    "S",
    "ST",
    "AVE",
    "BLVD",
    "RD",
    "PL",
    "PKWY",
    "DR",
    "LN",
    "TER",
    "CT",
    "SQ",
    "OF",
    "THE",
}


def sql_like_token(value: str) -> str:
    return str(value).replace("'", "''").replace("%", "").replace("_", "")


def distinctive_query_token(street: Any) -> str | None:
    words = normalized_words(street)
    candidates = [word for word in words if word not in GENERIC_QUERY_WORDS]
    if not candidates:
        return None
    alphabetic = [word for word in candidates if not word.isdigit()]
    if alphabetic:
        return max(alphabetic, key=lambda word: (len(word), word))
    return candidates[0]


def normalized_label(value: Any) -> str:
    return " ".join(normalized_words(value))


def label_contains_street(label: Any, street: Any) -> bool:
    label_words = normalized_label(label)
    if not label_words:
        return False
    padded = f" {label_words} "
    for variant in street_variants(street):
        key = normalized_label(variant)
        if key and f" {key} " in padded:
            return True
    return False


def label_matches_intersection(label: Any, street1: Any, street2: Any) -> bool:
    return label_contains_street(label, street1) and label_contains_street(label, street2)


def arcgis_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": "nycif-review-location-lion-node-audit/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SEC) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LION node request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"LION node response is not an object for {url}")
    if payload.get("error"):
        raise RuntimeError(f"LION node service error for {url}: {payload['error']}")
    time.sleep(REQUEST_DELAY_SEC)
    return payload


def fetch_intersection_nodes(
    street1: str,
    street2: str,
    *,
    request_cache: dict[tuple[str, str], tuple[list[dict[str, Any]], dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    key = tuple(sorted((normalized_label(street1), normalized_label(street2))))
    cached = request_cache.get(key)
    if cached is not None:
        return cached

    token1 = distinctive_query_token(street1)
    token2 = distinctive_query_token(street2)
    diagnostic: dict[str, Any] = {
        "street_1": street1,
        "street_2": street2,
        "query_token_1": token1,
        "query_token_2": token2,
    }
    if not token1 or not token2:
        diagnostic["reason"] = "No distinctive query token for one or both streets."
        result = ([], diagnostic)
        request_cache[key] = result
        return result

    clauses = [
        f"VIntersect LIKE '%{sql_like_token(token1)}%'",
        f"VIntersect LIKE '%{sql_like_token(token2)}%'",
    ]
    where = " AND ".join(clauses)
    diagnostic["where"] = where
    try:
        payload = arcgis_get(
            LION_NODE_QUERY_URL,
            {
                "where": where,
                "outFields": "NODEID,VIntersect",
                "returnGeometry": "true",
                "outSR": 4326,
                "resultRecordCount": MAX_NODE_RESULTS,
                "f": "json",
            },
        )
    except RuntimeError as exc:
        diagnostic["service_error"] = str(exc)
        result = ([], diagnostic)
        request_cache[key] = result
        return result

    features = payload.get("features") or []
    diagnostic["raw_feature_count"] = len(features) if isinstance(features, list) else 0
    nodes: dict[str, dict[str, Any]] = {}
    if isinstance(features, list):
        for feature in features:
            if not isinstance(feature, dict):
                continue
            attrs = feature.get("attributes") if isinstance(feature.get("attributes"), dict) else {}
            geometry = feature.get("geometry") if isinstance(feature.get("geometry"), dict) else {}
            label = attrs.get("VIntersect")
            if not label_matches_intersection(label, street1, street2):
                continue
            node_id = str(attrs.get("NODEID") or attrs.get("OBJECTID") or "").strip()
            try:
                lng = float(geometry.get("x"))
                lat = float(geometry.get("y"))
            except (TypeError, ValueError):
                continue
            if not node_id or not (-75.0 <= lng <= -73.0 and 40.0 <= lat <= 41.0):
                continue
            nodes[node_id] = {
                "node_id": node_id,
                "latitude": lat,
                "longitude": lng,
                "v_intersect": label,
            }
    diagnostic["verified_node_count"] = len(nodes)
    result = (list(nodes.values()), diagnostic)
    request_cache[key] = result
    return result


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    value = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius * math.asin(math.sqrt(value))


def choose_endpoint_pair(
    first_nodes: list[dict[str, Any]],
    second_nodes: list[dict[str, Any]],
    *,
    borough: str,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for first in first_nodes:
        if borough_for_point(boundaries, first["latitude"], first["longitude"]) != borough:
            continue
        for second in second_nodes:
            if first["node_id"] == second["node_id"]:
                continue
            if borough_for_point(boundaries, second["latitude"], second["longitude"]) != borough:
                continue
            distance = haversine_m(
                first["latitude"],
                first["longitude"],
                second["latitude"],
                second["longitude"],
            )
            if not (MIN_PAIR_DISTANCE_M <= distance <= MAX_PAIR_DISTANCE_M):
                continue
            midpoint_lat = round((first["latitude"] + second["latitude"]) / 2.0, 7)
            midpoint_lng = round((first["longitude"] + second["longitude"]) / 2.0, 7)
            if borough_for_point(boundaries, midpoint_lat, midpoint_lng) != borough:
                continue
            candidates.append(
                {
                    "first": first,
                    "second": second,
                    "distance_m": distance,
                    "midpoint_latitude": midpoint_lat,
                    "midpoint_longitude": midpoint_lng,
                }
            )
    if not candidates:
        return None
    return min(candidates, key=lambda item: item["distance_m"])


def resolve_payload(
    report: dict[str, Any],
    payload: dict[str, Any],
    *,
    boundaries: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposals = [dict(item) for item in payload.get("proposals") or [] if isinstance(item, dict)]
    before = sum(1 for item in proposals if item.get("disposition") == "unresolved")
    changed = 0
    diagnostics: list[dict[str, Any]] = []
    request_cache: dict[tuple[str, str], tuple[list[dict[str, Any]], dict[str, Any]]] = {}

    for index, proposal in enumerate(proposals):
        if proposal.get("disposition") != "unresolved":
            continue
        parsed = parse_segment_location(proposal.get("location"))
        if not parsed:
            continue
        main, cross1, cross2, suffix_borough = parsed
        borough = canonical_borough(proposal.get("proposed_borough")) or suffix_borough
        if not borough:
            continue

        first_nodes, first_diag = fetch_intersection_nodes(main, cross1, request_cache=request_cache)
        second_nodes, second_diag = fetch_intersection_nodes(main, cross2, request_cache=request_cache)
        pair = choose_endpoint_pair(
            first_nodes,
            second_nodes,
            borough=borough,
            boundaries=boundaries,
        )
        diagnostic = {
            "canonical_id": proposal.get("canonical_id"),
            "borough": borough,
            "main_street": main,
            "cross_street_1": cross1,
            "cross_street_2": cross2,
            "first_endpoint": first_diag,
            "second_endpoint": second_diag,
            "resolved": pair is not None,
        }
        if pair is None:
            diagnostics.append(diagnostic)
            continue

        first = pair["first"]
        second = pair["second"]
        out = dict(proposal)
        out.update(
            {
                "disposition": "mapped_from_nyc_lion_intersection_nodes",
                "proposed_borough": borough,
                "proposed_latitude": pair["midpoint_latitude"],
                "proposed_longitude": pair["midpoint_longitude"],
                "pin_eligible": True,
                "confidence": "high",
                "reason": (
                    "Current official NYC DCP LION intersection nodes identify both stated endpoints; "
                    "both endpoints and their midpoint fall inside the declared borough polygon."
                ),
                "lion_main_street": main,
                "lion_cross_streets": [cross1, cross2],
                "lion_endpoint_node_ids": [first["node_id"], second["node_id"]],
                "lion_endpoint_labels": [first.get("v_intersect"), second.get("v_intersect")],
                "lion_endpoint_coordinates": [
                    [first["latitude"], first["longitude"]],
                    [second["latitude"], second["longitude"]],
                ],
                "lion_segment_length_m": round(pair["distance_m"], 1),
                "evidence_source": "nyc_dcp_lion_node_feature_service",
                "official_boundary_borough": borough,
            }
        )
        proposals[index] = out
        changed += 1
        diagnostic.update(
            {
                "resolved": True,
                "selected_node_ids": [first["node_id"], second["node_id"]],
                "segment_length_m": round(pair["distance_m"], 1),
            }
        )
        diagnostics.append(diagnostic)

    counts = Counter(str(item.get("disposition") or "missing_disposition") for item in proposals)
    target = int(report.get("target_null_borough_count") or len(proposals))
    unresolved_after = counts.get("unresolved", 0)
    service_errors = [
        endpoint.get("service_error")
        for item in diagnostics
        for endpoint in (item.get("first_endpoint") or {}, item.get("second_endpoint") or {})
        if endpoint.get("service_error")
    ]
    final_report = dict(report)
    final_report.update(
        {
            "artifact_type": "review_location_coverage_audit_lion_nodes",
            "generated_at_utc": utc_now(),
            "accounted_count": len(proposals),
            "location_classified_count": sum(1 for item in proposals if item.get("location_classified") is True),
            "location_classified_pct": round((len(proposals) / target * 100.0), 4) if target else 100.0,
            "disposition_counts": dict(sorted(counts.items())),
            "proposed_borough_count": sum(1 for item in proposals if item.get("proposed_borough")),
            "proposed_coordinate_count": sum(
                1
                for item in proposals
                if item.get("proposed_latitude") is not None and item.get("proposed_longitude") is not None
            ),
            "unresolved_count": unresolved_after,
            "zero_silent_null_borough_records": len(proposals) == target,
            "qa_pass": len(proposals) == target and all(item.get("disposition") for item in proposals),
            "lion_resolution": {
                "method": "nyc_dcp_lion_node_label_midpoint_v2",
                "node_layer_url": LION_NODE_LAYER_URL,
                "unresolved_before": before,
                "unresolved_after": unresolved_after,
                "newly_resolved_count": changed,
                "request_count": len(request_cache),
                "service_error_count": len(set(service_errors)),
                "service_errors": sorted(set(service_errors)),
                "endpoint_diagnostics": diagnostics,
            },
        }
    )
    final_payload = dict(payload)
    final_payload.update(
        {
            "artifact_type": "review_location_resolution_proposals_lion_nodes",
            "generated_at_utc": final_report["generated_at_utc"],
            "target_count": target,
            "proposals": proposals,
        }
    )
    return final_report, final_payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-report", type=Path, required=True)
    parser.add_argument("--input-proposals", type=Path, required=True)
    parser.add_argument("--borough-boundaries", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.input_report.read_text(encoding="utf-8"))
    payload = json.loads(args.input_proposals.read_text(encoding="utf-8"))
    boundaries = load_boundaries(args.borough_boundaries)
    final_report, final_payload = resolve_payload(report, payload, boundaries=boundaries)
    write_json(args.report, final_report)
    write_json(args.proposals, final_payload)
    print(json.dumps(final_report, indent=2, sort_keys=True))
    return 0 if final_report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
