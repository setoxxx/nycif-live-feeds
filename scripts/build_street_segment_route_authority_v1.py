#!/usr/bin/env python3
"""Build publication-safe street route geometry from GeoSupport + NYC DCP LION.

This lane is intentionally separate from point-marker authority. It publishes only
LineString/MultiLineString geometry for current NYC Open Data street-segment
occurrences when all of the following agree:

1. the source location is a strict ``MAIN between CROSS1 and CROSS2`` claim;
2. NYC Planning GeoSupport resolves both intersections and Function 3 returns a
   segment identifier whose node pair matches those intersections;
3. the same SegmentID exists in the current official NYC DCP LION centerline
   extract; and
4. the official LION geometry endpoints agree with the GeoSupport endpoints.

No midpoint is emitted. Point geometry is forbidden. Existing MAP_READY/certified
point occurrences are protected and are never overridden by this route lane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.nyc_clock import nyc_today_iso
    from scripts.nyc_location_gazetteer import valid_nyc_lat_lng
    from scripts.nyc_location_resolver import (
        coordinate_matches_borough,
        haversine_m,
        parse_street_between,
    )
    from scripts.occurrence_identity_contract import occurrence_key_v2, occurrence_start, source_key
    from scripts.sync_nyc_open_data import fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from discovery_v02 import extract_rows  # type: ignore[no-redef]
    from nyc_clock import nyc_today_iso  # type: ignore[no-redef]
    from nyc_location_gazetteer import valid_nyc_lat_lng  # type: ignore[no-redef]
    from nyc_location_resolver import coordinate_matches_borough, haversine_m, parse_street_between  # type: ignore[no-redef]
    from occurrence_identity_contract import occurrence_key_v2, occurrence_start, source_key  # type: ignore[no-redef]
    from sync_nyc_open_data import fetch_raw_rows  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
DEFAULT_OUTPUT = ROOT / "data" / "reader-safe" / "street-segment-routes-v1.geojson"
DEFAULT_STATUS = ROOT / "data" / "reader-safe" / "street-segment-routes-v1-status.json"
SCHEMA_IDENTITY = "NYCIF_STREET_SEGMENT_ROUTE_IDENTITY_V1"
SCHEMA_READER = "NYCIF_STREET_SEGMENT_ROUTE_READER_V1"
SOURCE_DATASET_ID = "2v4z-66xt"
SOURCE_DATASET_NAME = "NYC DCP LION"
GEOSUPPORT_RUNTIME_IMAGE = "nycplanning/docker-geosupport:26.2.0"
ENDPOINT_TOLERANCE_M = 50.0
NYC_BOUNDS = (-74.30, 40.45, -73.65, 40.95)

BOROUGH_CODES = {
    "manhattan": "MN",
    "new york": "MN",
    "mn": "MN",
    "bronx": "BX",
    "bx": "BX",
    "brooklyn": "BK",
    "bk": "BK",
    "queens": "QN",
    "qn": "QN",
    "staten island": "SI",
    "si": "SI",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def borough_code(value: Any) -> str | None:
    return BOROUGH_CODES.get(norm_text(value))


def occurrence_id(row: dict[str, Any], *, raw_open_data: bool = False) -> str | None:
    dataset, source_event_id = source_key(row)
    if raw_open_data and dataset == "nyc-open-data":
        dataset = "tvpp-9vvx"
    start = occurrence_start(row)
    if not source_event_id or source_event_id == "missing" or not start:
        return None
    return "|".join((str(dataset), str(source_event_id), str(start)))


def current_segment_claims(rows: list[dict[str, Any]], today_nyc: str) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for row in rows:
        start = occurrence_start(row)
        if not start or start[:10] < today_nyc:
            continue
        location = str(row.get("event_location") or row.get("location") or "").strip()
        borough = str(row.get("event_borough") or row.get("borough") or "").strip()
        if not borough or not parse_street_between(location):
            continue
        oid = occurrence_id(row, raw_open_data=True)
        if not oid:
            continue
        key = f"{norm_text(borough)}|{norm_text(location)}"
        claim = claims.setdefault(
            key,
            {
                "claim_key": key,
                "borough": borough,
                "event_location": location,
                "occurrence_ids": [],
            },
        )
        if oid not in claim["occurrence_ids"]:
            claim["occurrence_ids"].append(oid)
    for claim in claims.values():
        claim["occurrence_ids"].sort()
        claim["occurrence_count"] = len(claim["occurrence_ids"])
    return claims


class GeoSupportStreetEvidence:
    """Strict wrapper around a python-geosupport-compatible backend."""

    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.call_count = 0

    def _call(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.call_count += 1
        result = self.backend.call(payload)
        if not isinstance(result, dict):
            raise RuntimeError("GeoSupport returned a non-dict result")
        return result

    def resolve_intersection(self, main: str, cross: str, borough: str) -> tuple[dict[str, Any] | None, str]:
        code = borough_code(borough)
        if not code:
            return None, "BOROUGH_UNSUPPORTED"
        try:
            base = self._call(
                {
                    "function": 2,
                    "borough_code": code,
                    "street_name": main,
                    "street_name_2": cross,
                }
            )
        except Exception:
            return None, "INTERSECTION_UNRESOLVED_OR_AMBIGUOUS"
        node = str(base.get("LION Node Number") or "").strip()
        if not node:
            return None, "INTERSECTION_NODE_MISSING"
        try:
            detail = self._call({"function": "2W", "node": node})
        except Exception:
            return None, "INTERSECTION_NODE_DETAIL_FAILED"
        try:
            lat = float(str(detail.get("Latitude") or "").strip())
            lng = float(str(detail.get("Longitude") or "").strip())
        except (TypeError, ValueError):
            return None, "INTERSECTION_COORDINATE_INVALID"
        if not valid_nyc_lat_lng(lat, lng):
            return None, "INTERSECTION_COORDINATE_INVALID"
        if not coordinate_matches_borough(lat, lng, borough):
            return None, "INTERSECTION_BOROUGH_CONTRADICTION"
        return {
            "node": node,
            "latitude": lat,
            "longitude": lng,
            "main_street": main,
            "cross_street": cross,
        }, "INTERSECTION_RESOLVED"

    def resolve_segment(self, claim: dict[str, Any]) -> dict[str, Any]:
        location = str(claim.get("event_location") or "").strip()
        borough = str(claim.get("borough") or "").strip()
        parsed = parse_street_between(location)
        if not parsed:
            return {"strict_segment_identity": False, "reason_code": "NOT_STREET_BETWEEN_CLAIM"}
        main, cross1, cross2 = parsed
        first, reason = self.resolve_intersection(main, cross1, borough)
        if first is None:
            return {"strict_segment_identity": False, "reason_code": reason}
        second, reason = self.resolve_intersection(main, cross2, borough)
        if second is None:
            return {
                "strict_segment_identity": False,
                "reason_code": reason,
                "endpoint_1": first,
            }
        if first["node"] == second["node"]:
            return {
                "strict_segment_identity": False,
                "reason_code": "SEGMENT_ENDPOINTS_COLLAPSE_TO_ONE_NODE",
                "endpoint_1": first,
                "endpoint_2": second,
            }
        code = borough_code(borough)
        if not code:
            return {"strict_segment_identity": False, "reason_code": "BOROUGH_UNSUPPORTED"}
        try:
            segment = self._call(
                {
                    "function": 3,
                    "borough_code": code,
                    "on": main,
                    "from": cross1,
                    "to": cross2,
                    "mode_switch": "X",
                }
            )
        except Exception:
            return {
                "strict_segment_identity": False,
                "reason_code": "SEGMENT_FUNCTION_3_UNRESOLVED",
                "endpoint_1": first,
                "endpoint_2": second,
            }
        from_node = str(segment.get("From Node") or "").strip()
        to_node = str(segment.get("To Node") or "").strip()
        if not from_node or not to_node or {from_node, to_node} != {first["node"], second["node"]}:
            return {
                "strict_segment_identity": False,
                "reason_code": "SEGMENT_NODE_PAIR_MISMATCH",
                "endpoint_1": first,
                "endpoint_2": second,
                "function_3_from_node": from_node,
                "function_3_to_node": to_node,
            }
        segment_id = str(segment.get("Segment Identifier") or "").strip()
        if not segment_id:
            return {
                "strict_segment_identity": False,
                "reason_code": "SEGMENT_IDENTIFIER_MISSING",
                "endpoint_1": first,
                "endpoint_2": second,
            }
        if segment_id.isdigit():
            segment_id = segment_id.zfill(7)
        distance_m = haversine_m(
            first["latitude"], first["longitude"], second["latitude"], second["longitude"]
        )
        if not 20.0 <= distance_m <= 5000.0:
            return {
                "strict_segment_identity": False,
                "reason_code": "SEGMENT_DISTANCE_OUT_OF_RANGE",
                "endpoint_1": first,
                "endpoint_2": second,
                "distance_m": round(distance_m, 3),
            }
        return {
            "strict_segment_identity": True,
            "reason_code": "GEOSUPPORT_ENDPOINTS_SEGMENT_IDENTITY_AGREE",
            "endpoint_1": first,
            "endpoint_2": second,
            "function_3_from_node": from_node,
            "function_3_to_node": to_node,
            "function_3_segment_identifier": segment_id,
            "distance_m": round(distance_m, 3),
        }


def audit_claims(claims: dict[str, dict[str, Any]], evidence: GeoSupportStreetEvidence) -> dict[str, Any]:
    if len(claims) > 5000:
        raise RuntimeError(f"street segment claim safety cap exceeded: {len(claims)}")
    reason_counts: Counter[str] = Counter()
    output: list[dict[str, Any]] = []
    strict = 0
    coverage = 0
    for key in sorted(claims):
        claim = claims[key]
        result = evidence.resolve_segment(claim)
        reason_counts[str(result.get("reason_code") or "UNSPECIFIED")] += 1
        if result.get("strict_segment_identity") is True:
            strict += 1
            coverage += int(claim.get("occurrence_count") or 0)
        output.append({**claim, **result})
    return {
        "schema_version": SCHEMA_IDENTITY,
        "generated_at_utc": utc_now_iso(),
        "source_authority": "NYC Planning GeoSupport",
        "geosupport_runtime_image": os.environ.get("GEOSUPPORT_RUNTIME_IMAGE", GEOSUPPORT_RUNTIME_IMAGE),
        "geometry_join_status": "SEGMENT_IDENTIFIER_ONLY_PENDING_LION_JOIN",
        "publication_authority_granted": False,
        "point_generation_allowed": False,
        "unique_segment_claim_count": len(claims),
        "strict_segment_identity_count": strict,
        "strict_occurrence_coverage": coverage,
        "unresolved_or_blocked_claim_count": len(claims) - strict,
        "geosupport_call_count": evidence.call_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "claims": output,
    }


def load_geosupport_backend() -> Any:
    try:
        from geosupport import Geosupport
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("GeoSupport runtime is required for identity acquisition") from exc
    return Geosupport()


def build_identity_report() -> dict[str, Any]:
    rows = fetch_raw_rows()
    today = nyc_today_iso()
    claims = current_segment_claims(rows, today)
    report = audit_claims(claims, GeoSupportStreetEvidence(load_geosupport_backend()))
    report["raw_rows_loaded"] = len(rows)
    report["today_nyc"] = today
    return report


def geometry_sha256(geometry: dict[str, Any]) -> str:
    raw = json.dumps(geometry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _valid_position(position: Any) -> bool:
    if not isinstance(position, list) or len(position) < 2:
        return False
    lng = _finite_number(position[0])
    lat = _finite_number(position[1])
    if lng is None or lat is None:
        return False
    min_lng, min_lat, max_lng, max_lat = NYC_BOUNDS
    return min_lng <= lng <= max_lng and min_lat <= lat <= max_lat


def valid_linear_geometry(geometry: Any) -> bool:
    if not isinstance(geometry, dict):
        return False
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geom_type == "LineString":
        return (
            isinstance(coordinates, list)
            and len(coordinates) >= 2
            and all(_valid_position(pos) for pos in coordinates)
            and len({tuple(pos[:2]) for pos in coordinates if isinstance(pos, list)}) >= 2
        )
    if geom_type == "MultiLineString":
        return (
            isinstance(coordinates, list)
            and bool(coordinates)
            and all(
                isinstance(line, list)
                and len(line) >= 2
                and all(_valid_position(pos) for pos in line)
                and len({tuple(pos[:2]) for pos in line if isinstance(pos, list)}) >= 2
                for line in coordinates
            )
        )
    return False


def line_endpoints(geometry: dict[str, Any]) -> list[tuple[float, float]]:
    coords = geometry.get("coordinates")
    lines: list[list[Any]]
    if geometry.get("type") == "LineString" and isinstance(coords, list):
        lines = [coords]
    elif geometry.get("type") == "MultiLineString" and isinstance(coords, list):
        lines = [line for line in coords if isinstance(line, list)]
    else:
        return []
    endpoints: list[tuple[float, float]] = []
    for line in lines:
        if len(line) < 2:
            continue
        for pos in (line[0], line[-1]):
            if _valid_position(pos):
                endpoints.append((float(pos[1]), float(pos[0])))
    return endpoints


def nearest_endpoint_distance_m(endpoint: dict[str, Any], source_endpoints: Iterable[tuple[float, float]]) -> float | None:
    try:
        lat = float(endpoint["latitude"])
        lng = float(endpoint["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    distances = [haversine_m(lat, lng, source_lat, source_lng) for source_lat, source_lng in source_endpoints]
    return min(distances) if distances else None


def feature_segment_id(feature: dict[str, Any]) -> str:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    for key in ("SegmentID", "SEGMENTID", "segmentid", "segment_id"):
        value = str(props.get(key) or "").strip()
        if value:
            return value.zfill(7) if value.isdigit() else value
    return ""


def feature_node_pair(feature: dict[str, Any]) -> tuple[str, str]:
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    return (
        str(props.get("NodeIDFrom") or "").strip(),
        str(props.get("NodeIDTo") or "").strip(),
    )


def equivalent_lion_feature(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    hashes: set[str] = set()
    node_pairs: set[tuple[str, str]] = set()
    for row in rows:
        geometry = row.get("geometry")
        if not valid_linear_geometry(geometry):
            return None
        hashes.add(geometry_sha256(geometry))
        pair = feature_node_pair(row)
        if not all(pair):
            return None
        node_pairs.add(pair)
    return rows[0] if len(hashes) == 1 and len(node_pairs) == 1 else None


def canonical_rows(payload: Any) -> list[dict[str, Any]]:
    return [row for row in extract_rows(payload) if isinstance(row, dict)]


def build_reader_artifact(
    identity: dict[str, Any],
    lion: dict[str, Any],
    canonical: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if identity.get("schema_version") != SCHEMA_IDENTITY:
        raise ValueError("unexpected street route identity schema")
    if identity.get("publication_authority_granted") is not False:
        raise ValueError("identity stage must not grant publication authority")
    features = lion.get("features")
    if lion.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("LION input must be a GeoJSON FeatureCollection")

    canonical_by_occurrence: dict[str, dict[str, Any]] = {}
    canonical_duplicate_ids = 0
    for event in canonical:
        oid = occurrence_id(event)
        if not oid:
            continue
        if oid in canonical_by_occurrence:
            canonical_duplicate_ids += 1
            continue
        canonical_by_occurrence[oid] = event

    lion_by_segment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in features:
        if not isinstance(feature, dict):
            continue
        segment_id = feature_segment_id(feature)
        if segment_id:
            lion_by_segment[segment_id].append(feature)

    output_features: list[dict[str, Any]] = []
    emitted_ids: set[str] = set()
    duplicate_occurrence_count = 0
    invalid_geometry_count = 0
    point_geometry_count = 0
    exact_point_protected_count = 0
    unmatched_occurrence_count = 0
    location_mismatch_count = 0
    joined_segment_count = 0
    blocked_reasons: Counter[str] = Counter()

    strict_claims = [
        claim for claim in (identity.get("claims") or [])
        if isinstance(claim, dict) and claim.get("strict_segment_identity") is True
    ]

    for claim in strict_claims:
        segment_id = str(claim.get("function_3_segment_identifier") or "").strip()
        if segment_id.isdigit():
            segment_id = segment_id.zfill(7)
        source_feature = equivalent_lion_feature(lion_by_segment.get(segment_id, []))
        if source_feature is None:
            blocked_reasons["LION_SEGMENT_MISSING_OR_CONFLICTING"] += 1
            continue
        geometry = source_feature.get("geometry")
        if not valid_linear_geometry(geometry):
            blocked_reasons["LION_GEOMETRY_INVALID"] += 1
            continue
        source_endpoints = line_endpoints(geometry)
        first_distance = nearest_endpoint_distance_m(claim.get("endpoint_1") or {}, source_endpoints)
        second_distance = nearest_endpoint_distance_m(claim.get("endpoint_2") or {}, source_endpoints)
        if first_distance is None or second_distance is None:
            blocked_reasons["ENDPOINT_VALIDATION_MISSING"] += 1
            continue
        if max(first_distance, second_distance) > ENDPOINT_TOLERANCE_M:
            blocked_reasons["LION_GEOSUPPORT_ENDPOINT_DISAGREEMENT"] += 1
            continue
        joined_segment_count += 1
        digest = geometry_sha256(geometry)

        for oid in claim.get("occurrence_ids") or []:
            oid = str(oid)
            event = canonical_by_occurrence.get(oid)
            if event is None:
                unmatched_occurrence_count += 1
                continue
            nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
            if nycif.get("map_eligibility_state") == "MAP_READY" or nycif.get("certified_pin") is True:
                exact_point_protected_count += 1
                continue
            event_location = str(event.get("location") or event.get("display_location") or "").strip()
            event_borough = str(event.get("borough") or "").strip()
            if norm_text(event_location) != norm_text(claim.get("event_location")) or norm_text(event_borough) != norm_text(claim.get("borough")):
                location_mismatch_count += 1
                continue
            if oid in emitted_ids:
                duplicate_occurrence_count += 1
                continue
            emitted_ids.add(oid)
            dataset, source_event_id = source_key(event)
            emitted_geometry = json.loads(json.dumps(geometry))
            if emitted_geometry.get("type") == "Point":
                point_geometry_count += 1
                continue
            if not valid_linear_geometry(emitted_geometry):
                invalid_geometry_count += 1
                continue
            output_features.append(
                {
                    "type": "Feature",
                    "id": oid,
                    "geometry": emitted_geometry,
                    "properties": {
                        "occurrence_id": oid,
                        "title": event.get("title"),
                        "location": event_location,
                        "borough": event_borough,
                        "start_date_time": event.get("start_date_time"),
                        "end_date_time": event.get("end_date_time"),
                        "source_dataset": dataset,
                        "source_event_id": source_event_id,
                        "display_geometry_role": "route",
                        "geometry_precision": "official_centerline",
                        "geometry_authority": "nyc_dcp_geosupport_plus_lion",
                        "source_geometry_dataset_id": SOURCE_DATASET_ID,
                        "source_geometry_dataset_name": SOURCE_DATASET_NAME,
                        "source_segment_id": segment_id,
                        "geometry_sha256": digest,
                        "validation_state": "validated",
                        "publication_allowed": True,
                        "certified_pin": False,
                        "exact_pin_eligible": False,
                        "endpoint_tolerance_m": ENDPOINT_TOLERANCE_M,
                        "endpoint_1_nearest_source_endpoint_m": round(first_distance, 3),
                        "endpoint_2_nearest_source_endpoint_m": round(second_distance, 3),
                    },
                }
            )

    qa_pass = (
        canonical_duplicate_ids == 0
        and duplicate_occurrence_count == 0
        and invalid_geometry_count == 0
        and point_geometry_count == 0
        and (not strict_claims or bool(features))
    )
    generated = utc_now_iso()
    status = {
        "schema_version": SCHEMA_READER,
        "generated_at_utc": generated,
        "publication_authority_granted": True,
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_dataset_name": SOURCE_DATASET_NAME,
        "source_geometry_crs": "EPSG:4326",
        "strict_segment_identity_count": len(strict_claims),
        "strict_occurrence_coverage": int(identity.get("strict_occurrence_coverage") or 0),
        "lion_source_feature_count": len(features),
        "joined_segment_count": joined_segment_count,
        "route_geometry_count": len(output_features),
        "area_geometry_count": 0,
        "point_geometry_count": point_geometry_count,
        "invalid_geometry_count": invalid_geometry_count,
        "duplicate_occurrence_count": duplicate_occurrence_count,
        "canonical_duplicate_occurrence_count": canonical_duplicate_ids,
        "exact_point_protected_count": exact_point_protected_count,
        "unmatched_occurrence_count": unmatched_occurrence_count,
        "location_mismatch_count": location_mismatch_count,
        "blocked_reason_counts": dict(sorted(blocked_reasons.items())),
        "midpoint_publication_count": 0,
        "qa_pass": qa_pass,
        "operating_rule": (
            "Only official LION line geometry whose endpoints agree with strict GeoSupport segment identity may publish. "
            "Point geometry and midpoint substitution are forbidden."
        ),
    }
    collection = {
        "type": "FeatureCollection",
        "metadata": {
            "schema_version": SCHEMA_READER,
            "generated_at_utc": generated,
            "geometry_roles": ["route"],
            "point_geometry_allowed": False,
            "source_dataset_id": SOURCE_DATASET_ID,
        },
        "features": output_features,
    }
    return collection, status


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-output", type=Path)
    parser.add_argument("--identity-report", type=Path)
    parser.add_argument("--lion-geojson", type=Path)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    args = parser.parse_args()

    if args.identity_output:
        report = build_identity_report()
        write_json(args.identity_output, report)
        print(json.dumps({
            "identity_output": str(args.identity_output),
            "strict_segment_identity_count": report["strict_segment_identity_count"],
            "strict_occurrence_coverage": report["strict_occurrence_coverage"],
        }, indent=2, sort_keys=True))
        if not args.identity_report and not args.lion_geojson:
            return 0

    if not args.identity_report or not args.lion_geojson:
        parser.error("reader build requires --identity-report and --lion-geojson")

    identity = json.loads(args.identity_report.read_text(encoding="utf-8"))
    lion = json.loads(args.lion_geojson.read_text(encoding="utf-8"))
    canonical_payload = json.loads(args.canonical.read_text(encoding="utf-8"))
    collection, status = build_reader_artifact(identity, lion, canonical_rows(canonical_payload))
    write_json(args.output, collection)
    write_json(args.status, status)
    print(json.dumps(status, indent=2, sort_keys=True))
    if not status["qa_pass"]:
        raise RuntimeError(f"street route authority QA failed: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
