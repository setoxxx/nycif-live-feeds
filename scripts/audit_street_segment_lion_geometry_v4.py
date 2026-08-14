#!/usr/bin/env python3
"""Join strict GeoSupport blockface identities to official LION line geometry.

This is a NONPUBLIC_EVIDENCE_ONLY geometry audit. It accepts only source-faithful
LineString/MultiLineString geometry keyed by the Function 3 Segment Identifier,
requires one source feature per strict identity, hashes the preserved geometry,
and checks that both independently resolved GeoSupport endpoint nodes agree with
the source line endpoints within a conservative tolerance.

It never converts a line to a public point and never grants Projector or
publication authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_LION_GEOMETRY_AUDIT_V4"
SOURCE_DATASET_ID = "2v4z-66xt"
SOURCE_DATASET_NAME = "NYC DCP LION"
SOURCE_VERSION_EXPECTED = "26B"
MAX_ENDPOINT_DISTANCE_M = 50.0


def _norm_segment_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return text.zfill(7)
    return text


def _canonical_geometry_bytes(geometry: dict[str, Any]) -> bytes:
    return json.dumps(
        geometry,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def geometry_sha256(geometry: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_geometry_bytes(geometry)).hexdigest()


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * radius_m * math.asin(math.sqrt(a))


def _line_endpoints(geometry: dict[str, Any]) -> list[tuple[float, float]]:
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    lines: list[list[Any]] = []
    if geom_type == "LineString" and isinstance(coordinates, list):
        lines = [coordinates]
    elif geom_type == "MultiLineString" and isinstance(coordinates, list):
        lines = [line for line in coordinates if isinstance(line, list)]
    else:
        return []

    endpoints: list[tuple[float, float]] = []
    for line in lines:
        if len(line) < 2:
            continue
        for coordinate in (line[0], line[-1]):
            if not isinstance(coordinate, list) or len(coordinate) < 2:
                continue
            try:
                lon = float(coordinate[0])
                lat = float(coordinate[1])
            except (TypeError, ValueError):
                continue
            endpoints.append((lat, lon))
    return endpoints


def _nearest_endpoint_distance_m(endpoint: dict[str, Any], source_endpoints: Iterable[tuple[float, float]]) -> float | None:
    try:
        lat = float(endpoint["latitude"])
        lon = float(endpoint["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    distances = [haversine_m(lat, lon, source_lat, source_lon) for source_lat, source_lon in source_endpoints]
    return min(distances) if distances else None


def _feature_segment_id(feature: dict[str, Any]) -> str:
    props = feature.get("properties")
    if not isinstance(props, dict):
        return ""
    for key in ("SegmentID", "SEGMENTID", "segmentid", "segment_id"):
        if key in props:
            return _norm_segment_id(props.get(key))
    return ""


def audit(identity_report: dict[str, Any], lion_geojson: dict[str, Any]) -> dict[str, Any]:
    if identity_report.get("schema_version") != "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2":
        raise ValueError("unexpected GeoSupport identity report schema")
    if identity_report.get("geometry_join_status") != "SEGMENT_IDENTIFIER_ONLY_GEOMETRY_NOT_YET_JOINED":
        raise ValueError("identity report must not already claim geometry join")
    if identity_report.get("publication_authority_granted") is not False:
        raise ValueError("identity report unexpectedly grants publication authority")
    if identity_report.get("projector_consumed") is not False:
        raise ValueError("identity report unexpectedly consumed by Projector")

    features = lion_geojson.get("features")
    if lion_geojson.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("LION source must be a GeoJSON FeatureCollection")

    by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_source_segment_id = 0
    for feature in features:
        if not isinstance(feature, dict):
            continue
        segment_id = _feature_segment_id(feature)
        if not segment_id:
            missing_source_segment_id += 1
            continue
        by_segment[segment_id].append(feature)

    reason_counts: Counter[str] = Counter()
    entries: list[dict[str, Any]] = []
    geometry_hashes: Counter[str] = Counter()
    joined_segment_ids: Counter[str] = Counter()

    strict_claims = [
        claim for claim in (identity_report.get("claims") or [])
        if isinstance(claim, dict) and claim.get("strict_nonpublic_segment_evidence") is True
    ]

    for claim in strict_claims:
        segment_id = _norm_segment_id(claim.get("function_3_segment_identifier"))
        source_rows = by_segment.get(segment_id, [])
        base = {
            "claim_key": claim.get("claim_key"),
            "borough": claim.get("borough"),
            "event_location": claim.get("event_location"),
            "occurrence_count": claim.get("occurrence_count"),
            "source_event_ids": claim.get("source_event_ids"),
            "function_3_segment_identifier": segment_id,
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "publication_allowed": False,
            "exact_pin_eligible": False,
            "projector_consumed": False,
            "point_generated": False,
            "midpoint_used_as_geometry": False,
        }
        if not segment_id:
            reason_counts["SEGMENT_IDENTIFIER_MISSING"] += 1
            entries.append({**base, "geometry_joined": False, "reason_code": "SEGMENT_IDENTIFIER_MISSING"})
            continue
        if not source_rows:
            reason_counts["OFFICIAL_LION_SEGMENT_NOT_FOUND"] += 1
            entries.append({**base, "geometry_joined": False, "reason_code": "OFFICIAL_LION_SEGMENT_NOT_FOUND"})
            continue
        if len(source_rows) != 1:
            reason_counts["OFFICIAL_LION_SEGMENT_NOT_UNIQUE"] += 1
            entries.append({**base, "geometry_joined": False, "reason_code": "OFFICIAL_LION_SEGMENT_NOT_UNIQUE", "source_feature_count": len(source_rows)})
            continue

        feature = source_rows[0]
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in {"LineString", "MultiLineString"}:
            reason_counts["OFFICIAL_LION_GEOMETRY_INVALID_TYPE"] += 1
            entries.append({**base, "geometry_joined": False, "reason_code": "OFFICIAL_LION_GEOMETRY_INVALID_TYPE"})
            continue
        source_endpoints = _line_endpoints(geometry)
        if len(source_endpoints) < 2:
            reason_counts["OFFICIAL_LION_GEOMETRY_ENDPOINTS_INVALID"] += 1
            entries.append({**base, "geometry_joined": False, "reason_code": "OFFICIAL_LION_GEOMETRY_ENDPOINTS_INVALID"})
            continue

        endpoint_1_distance = _nearest_endpoint_distance_m(claim.get("endpoint_1") or {}, source_endpoints)
        endpoint_2_distance = _nearest_endpoint_distance_m(claim.get("endpoint_2") or {}, source_endpoints)
        if endpoint_1_distance is None or endpoint_2_distance is None:
            reason_counts["GEOSUPPORT_ENDPOINT_COORDINATE_MISSING"] += 1
            entries.append({**base, "geometry_joined": False, "reason_code": "GEOSUPPORT_ENDPOINT_COORDINATE_MISSING"})
            continue
        max_distance = max(endpoint_1_distance, endpoint_2_distance)
        if max_distance > MAX_ENDPOINT_DISTANCE_M:
            reason_counts["LION_GEOMETRY_ENDPOINT_DISAGREEMENT"] += 1
            entries.append({
                **base,
                "geometry_joined": False,
                "reason_code": "LION_GEOMETRY_ENDPOINT_DISAGREEMENT",
                "endpoint_1_nearest_source_endpoint_m": round(endpoint_1_distance, 3),
                "endpoint_2_nearest_source_endpoint_m": round(endpoint_2_distance, 3),
            })
            continue

        digest = geometry_sha256(geometry)
        geometry_hashes[digest] += 1
        joined_segment_ids[segment_id] += 1
        reason_counts["OFFICIAL_LION_SEGMENT_GEOMETRY_JOINED"] += 1
        entries.append({
            **base,
            "geometry_joined": True,
            "reason_code": "OFFICIAL_LION_SEGMENT_GEOMETRY_JOINED",
            "source_dataset_id": SOURCE_DATASET_ID,
            "source_dataset_name": SOURCE_DATASET_NAME,
            "source_version_expected": SOURCE_VERSION_EXPECTED,
            "geometry_type": geometry.get("type"),
            "geometry_sha256": digest,
            "geometry": geometry,
            "endpoint_1_nearest_source_endpoint_m": round(endpoint_1_distance, 3),
            "endpoint_2_nearest_source_endpoint_m": round(endpoint_2_distance, 3),
            "endpoint_tolerance_m": MAX_ENDPOINT_DISTANCE_M,
        })

    joined = [entry for entry in entries if entry.get("geometry_joined") is True]
    duplicate_joined_segment_ids = sum(1 for count in joined_segment_ids.values() if count > 1)
    duplicate_geometry_hashes = sum(1 for count in geometry_hashes.values() if count > 1)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_dataset_name": SOURCE_DATASET_NAME,
        "source_version_expected": SOURCE_VERSION_EXPECTED,
        "source_geometry_crs": "EPSG:4326",
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "location_cache_modified": False,
        "public_map_modified": False,
        "point_generated_count": 0,
        "midpoint_publication_count": 0,
        "input_strict_identity_count": len(strict_claims),
        "source_feature_count": len(features),
        "source_feature_without_segment_identifier_count": missing_source_segment_id,
        "joined_geometry_count": len(joined),
        "unresolved_or_blocked_geometry_count": len(strict_claims) - len(joined),
        "unique_joined_segment_identifier_count": len(joined_segment_ids),
        "duplicate_joined_segment_identifier_count": duplicate_joined_segment_ids,
        "unique_geometry_hash_count": len(geometry_hashes),
        "duplicate_geometry_hash_group_count": duplicate_geometry_hashes,
        "endpoint_tolerance_m": MAX_ENDPOINT_DISTANCE_M,
        "reason_counts": dict(sorted(reason_counts.items())),
        "hard_zero_gates": {
            "publication_count": 0,
            "exact_pin_eligible_count": 0,
            "point_generated_count": 0,
            "midpoint_publication_count": 0,
            "projector_consumed_count": 0,
            "location_cache_write_count": 0,
            "public_map_write_count": 0,
        },
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-report", type=Path, required=True)
    parser.add_argument("--lion-geojson", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    identity = json.loads(args.identity_report.read_text(encoding="utf-8"))
    lion = json.loads(args.lion_geojson.read_text(encoding="utf-8"))
    result = audit(identity, lion)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {key: result[key] for key in (
        "schema_version",
        "source_dataset_id",
        "source_version_expected",
        "input_strict_identity_count",
        "source_feature_count",
        "joined_geometry_count",
        "unresolved_or_blocked_geometry_count",
        "unique_joined_segment_identifier_count",
        "duplicate_joined_segment_identifier_count",
        "unique_geometry_hash_count",
        "duplicate_geometry_hash_group_count",
        "endpoint_tolerance_m",
        "reason_counts",
        "hard_zero_gates",
    )}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
