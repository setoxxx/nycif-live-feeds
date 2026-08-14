#!/usr/bin/env python3
"""Classify official LION source candidates for V5 ordered route edges.

V5 certifies route topology only. V6 asks a narrower question: for every
ordered consecutive GeoSupport 3S node pair, how many official LION rows exist,
and are multiple rows exact-equivalent source representations or genuinely
conflicting candidates?

This audit does NOT promote route geometry. It preserves candidate source
geometry only inside NONPUBLIC_EVIDENCE_ONLY evidence, and it fails closed on
missing or conflicting edge evidence. For blocked conflicts it records a
bounded diagnostic summary of the competing official rows so later review can
distinguish source semantics without choosing a winner.

No shortest-path search, midpoint/point generation, Projector consumption,
cache/public-map write, renderer enablement, or publication authority is
permitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_LION_ROUTE_EDGE_AUDIT_V6"
V5_SCHEMA = "NYCIF_STREET_SEGMENT_GEOSUPPORT_3S_ROUTE_AUDIT_V5"
SOURCE_DATASET_ID = "2v4z-66xt"
MAX_BLOCKED_CANDIDATE_DIAGNOSTICS = 8


def _node(value: Any) -> str:
    text = str(value or "").strip()
    return text.zfill(7) if text.isdigit() else text


def _pair(a: Any, b: Any) -> tuple[str, str]:
    left, right = _node(a), _node(b)
    return tuple(sorted((left, right)))


def _properties(feature: dict[str, Any]) -> dict[str, Any]:
    props = feature.get("properties")
    return props if isinstance(props, dict) else {}


def _feature_pair(feature: dict[str, Any]) -> tuple[str, str]:
    props = _properties(feature)
    return _pair(props.get("NodeIDFrom"), props.get("NodeIDTo"))


def _canonical_geometry(geometry: dict[str, Any]) -> str:
    return json.dumps(geometry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _geometry_hash(geometry: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_geometry(geometry).encode("utf-8")).hexdigest()


def _candidate_signature(feature: dict[str, Any]) -> tuple[str, tuple[str, str]] | None:
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("type") not in {"LineString", "MultiLineString"}:
        return None
    pair = _feature_pair(feature)
    if not all(pair):
        return None
    return _geometry_hash(geometry), pair


def _candidate_diagnostic(feature: dict[str, Any]) -> dict[str, Any]:
    """Return bounded, non-promotional source diagnostics for blocked rows."""
    props = _properties(feature)
    geometry = feature.get("geometry")
    geometry_valid = isinstance(geometry, dict) and geometry.get("type") in {"LineString", "MultiLineString"}
    return {
        "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
        "geometry_sha256": _geometry_hash(geometry) if geometry_valid else None,
        "source_segment_id": str(props.get("SegmentID") or "").strip(),
        "source_node_id_from": _node(props.get("NodeIDFrom")),
        "source_node_id_to": _node(props.get("NodeIDTo")),
        "source_street": props.get("Street"),
        "source_feature_type": props.get("FeatureTyp"),
        "source_segment_type": props.get("SegmentTyp"),
        "source_rb_layer": props.get("RB_Layer"),
        "source_physical_id": props.get("PhysicalID"),
        "source_generic_id": props.get("GenericID"),
        "source_join_id": props.get("Join_ID"),
    }


def audit(v5_report: dict[str, Any], lion_geojson: dict[str, Any]) -> dict[str, Any]:
    if v5_report.get("schema_version") != V5_SCHEMA:
        raise ValueError("unexpected V5 topology report schema")
    if v5_report.get("publication_authority_granted") is not False:
        raise ValueError("V5 unexpectedly grants publication authority")
    if v5_report.get("geometry_join_completed") is not False:
        raise ValueError("V5 must not already contain joined route geometry")
    if v5_report.get("shortest_path_algorithm_used") is not False:
        raise ValueError("V5 unexpectedly used shortest-path routing")

    features = lion_geojson.get("features")
    if lion_geojson.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("LION source must be a FeatureCollection")

    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    invalid_source_node_pair_count = 0
    for feature in features:
        if not isinstance(feature, dict):
            continue
        pair = _feature_pair(feature)
        if not all(pair):
            invalid_source_node_pair_count += 1
            continue
        by_pair[pair].append(feature)

    routes = [
        route for route in (v5_report.get("routes") or [])
        if isinstance(route, dict) and route.get("route_topology_certified") is True
    ]
    edge_rows: list[dict[str, Any]] = []
    route_rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    global_edge_pairs: Counter[tuple[str, str]] = Counter()

    for route in routes:
        route_edges = route.get("ordered_edge_node_pairs") or []
        accepted_edges = 0
        blocked_edges = 0
        route_edge_records: list[dict[str, Any]] = []
        for index, raw_pair in enumerate(route_edges):
            if not isinstance(raw_pair, list) or len(raw_pair) != 2:
                pair = ("", "")
            else:
                pair = _pair(raw_pair[0], raw_pair[1])
            global_edge_pairs[pair] += 1
            source_rows = by_pair.get(pair, [])
            record: dict[str, Any] = {
                "claim_key": route.get("claim_key"),
                "edge_index": index,
                "ordered_node_pair": raw_pair,
                "undirected_node_pair": list(pair),
                "source_candidate_count": len(source_rows),
                "edge_geometry_candidate_accepted": False,
                "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
                "publication_allowed": False,
                "projector_consumed": False,
            }
            if not all(pair):
                reason = "ROUTE_EDGE_NODE_PAIR_INVALID"
            elif not source_rows:
                reason = "LION_ROUTE_EDGE_NOT_FOUND"
            else:
                signatures = [_candidate_signature(feature) for feature in source_rows]
                if any(signature is None for signature in signatures):
                    reason = "LION_ROUTE_EDGE_SOURCE_INVALID"
                elif len(source_rows) == 1:
                    reason = "LION_ROUTE_EDGE_UNIQUE_SOURCE"
                elif len(set(signatures)) == 1:
                    reason = "LION_ROUTE_EDGE_EQUIVALENT_SOURCE_ROWS"
                else:
                    reason = "LION_ROUTE_EDGE_CONFLICTING_SOURCE_ROWS"

            if reason in {"LION_ROUTE_EDGE_UNIQUE_SOURCE", "LION_ROUTE_EDGE_EQUIVALENT_SOURCE_ROWS"}:
                accepted_edges += 1
                chosen = source_rows[0]
                geometry = chosen["geometry"]
                props = _properties(chosen)
                record.update({
                    "edge_geometry_candidate_accepted": True,
                    "source_equivalence_collapsed": len(source_rows) > 1,
                    "geometry_type": geometry.get("type"),
                    "geometry_sha256": _geometry_hash(geometry),
                    "geometry": geometry,
                    "source_segment_id": str(props.get("SegmentID") or "").strip(),
                    "source_node_id_from": _node(props.get("NodeIDFrom")),
                    "source_node_id_to": _node(props.get("NodeIDTo")),
                    "source_street": props.get("Street"),
                    "source_feature_type": props.get("FeatureTyp"),
                    "source_segment_type": props.get("SegmentTyp"),
                    "source_rb_layer": props.get("RB_Layer"),
                    "source_physical_id": props.get("PhysicalID"),
                    "source_generic_id": props.get("GenericID"),
                })
            else:
                blocked_edges += 1
                if source_rows:
                    diagnostics = [
                        _candidate_diagnostic(feature)
                        for feature in source_rows[:MAX_BLOCKED_CANDIDATE_DIAGNOSTICS]
                    ]
                    record.update({
                        "blocked_source_candidate_diagnostics": diagnostics,
                        "blocked_source_candidate_diagnostic_count": len(diagnostics),
                        "blocked_source_candidate_diagnostics_truncated": len(source_rows) > len(diagnostics),
                    })
            record["reason_code"] = reason
            reason_counts[reason] += 1
            route_edge_records.append(record)
            edge_rows.append(record)

        route_rows.append({
            "claim_key": route.get("claim_key"),
            "occurrence_count": route.get("occurrence_count"),
            "route_edge_count": len(route_edges),
            "accepted_edge_count": accepted_edges,
            "blocked_edge_count": blocked_edges,
            "all_route_edges_source_resolved": blocked_edges == 0 and accepted_edges == len(route_edges),
            "route_geometry_joined": False,
            "edges": route_edge_records,
        })

    total_edges = len(edge_rows)
    accepted = sum(1 for edge in edge_rows if edge.get("edge_geometry_candidate_accepted") is True)
    fully_resolved_routes = sum(1 for route in route_rows if route["all_route_edges_source_resolved"] is True)
    duplicate_route_edge_pair_count = sum(1 for count in global_edge_pairs.values() if count > 1)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset_id": SOURCE_DATASET_ID,
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "location_cache_modified": False,
        "public_map_modified": False,
        "route_geometry_join_completed": False,
        "shortest_path_algorithm_used": False,
        "blocked_candidate_diagnostic_limit": MAX_BLOCKED_CANDIDATE_DIAGNOSTICS,
        "certified_route_count": len(routes),
        "certified_route_occurrence_count": sum(int(route.get("occurrence_count") or 0) for route in routes),
        "ordered_route_edge_count": total_edges,
        "unique_undirected_route_edge_count": len(global_edge_pairs),
        "duplicate_route_edge_pair_count": duplicate_route_edge_pair_count,
        "source_feature_count": len(features),
        "source_feature_invalid_node_pair_count": invalid_source_node_pair_count,
        "accepted_edge_candidate_count": accepted,
        "blocked_edge_candidate_count": total_edges - accepted,
        "fully_source_resolved_route_count": fully_resolved_routes,
        "route_with_blocked_edge_count": len(routes) - fully_resolved_routes,
        "reason_counts": dict(sorted(reason_counts.items())),
        "hard_zero_gates": {
            "publication_count": 0,
            "exact_pin_eligible_count": 0,
            "point_generated_count": 0,
            "midpoint_publication_count": 0,
            "projector_consumed_count": 0,
            "location_cache_write_count": 0,
            "public_map_write_count": 0,
            "route_geometry_join_count": 0,
        },
        "routes": route_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v5-report", type=Path, required=True)
    parser.add_argument("--lion-geojson", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        json.loads(args.v5_report.read_text(encoding="utf-8")),
        json.loads(args.lion_geojson.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version", "certified_route_count", "certified_route_occurrence_count",
        "ordered_route_edge_count", "unique_undirected_route_edge_count",
        "duplicate_route_edge_pair_count", "accepted_edge_candidate_count",
        "blocked_edge_candidate_count", "fully_source_resolved_route_count",
        "route_with_blocked_edge_count", "reason_counts", "hard_zero_gates",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
