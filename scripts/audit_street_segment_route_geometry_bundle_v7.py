#!/usr/bin/env python3
"""Certify non-public ordered source-geometry bundles from V6 route edges.

V7 does not dissolve, concatenate, snap, interpolate, or otherwise synthesize a
route line. A route is certifiable only when V6 says every ordered edge is
source-resolved and each edge carries accepted official LION geometry plus its
source hash. V7 preserves those edge geometries verbatim in route order and
computes a deterministic bundle hash over the ordered node-pair/hash evidence.

Any blocked or incomplete edge withholds the entire route. No public renderer,
Projector, point generation, cache write, public-map write, or publication
authority is granted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_ROUTE_GEOMETRY_BUNDLE_AUDIT_V7"
V6_SCHEMA = "NYCIF_STREET_SEGMENT_LION_ROUTE_EDGE_AUDIT_V6"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def audit(v6: dict[str, Any]) -> dict[str, Any]:
    if v6.get("schema_version") != V6_SCHEMA:
        raise ValueError("unexpected V6 schema")
    for key in ("publication_authority_granted", "projector_consumed", "route_geometry_join_completed"):
        if v6.get(key) is not False:
            raise ValueError(f"V6 safety boundary violated: {key}")
    if v6.get("shortest_path_algorithm_used") is not False:
        raise ValueError("V6 unexpectedly used shortest-path routing")

    routes: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    certified = 0
    occurrence_coverage = 0
    component_edge_count = 0

    for row in v6.get("routes") or []:
        if not isinstance(row, dict):
            continue
        base = {
            "claim_key": row.get("claim_key"),
            "occurrence_count": row.get("occurrence_count"),
        }
        edges = row.get("edges") or []
        if row.get("all_route_edges_source_resolved") is not True:
            reason = "V6_ROUTE_HAS_BLOCKED_EDGE"
            reasons[reason] += 1
            routes.append({**base, "route_geometry_bundle_certified": False, "reason_code": reason, "publication_allowed": False})
            continue
        if int(row.get("blocked_edge_count") or 0) != 0:
            reason = "V6_ROUTE_BLOCK_COUNT_CONTRADICTION"
            reasons[reason] += 1
            routes.append({**base, "route_geometry_bundle_certified": False, "reason_code": reason, "publication_allowed": False})
            continue
        if len(edges) != int(row.get("route_edge_count") or 0) or not edges:
            reason = "V6_ROUTE_EDGE_COUNT_CONTRADICTION"
            reasons[reason] += 1
            routes.append({**base, "route_geometry_bundle_certified": False, "reason_code": reason, "publication_allowed": False})
            continue

        ordered: list[dict[str, Any]] = []
        invalid = False
        for index, edge in enumerate(edges):
            geometry = edge.get("geometry")
            digest = edge.get("geometry_sha256")
            pair = edge.get("ordered_node_pair")
            if (
                edge.get("edge_geometry_candidate_accepted") is not True
                or not isinstance(geometry, dict)
                or geometry.get("type") not in {"LineString", "MultiLineString"}
                or not isinstance(digest, str)
                or len(digest) != 64
                or not isinstance(pair, list)
                or len(pair) != 2
            ):
                invalid = True
                break
            if _hash(geometry) != digest:
                invalid = True
                break
            ordered.append({
                "edge_index": index,
                "ordered_node_pair": pair,
                "geometry_type": geometry.get("type"),
                "geometry_sha256": digest,
                "geometry": geometry,
                "source_segment_id": edge.get("source_segment_id"),
                "source_physical_id": edge.get("source_physical_id"),
                "source_generic_id": edge.get("source_generic_id"),
                "source_street": edge.get("source_street"),
                "source_feature_type": edge.get("source_feature_type"),
                "source_segment_type": edge.get("source_segment_type"),
                "source_rb_layer": edge.get("source_rb_layer"),
            })

        if invalid:
            reason = "V6_ACCEPTED_EDGE_EVIDENCE_INVALID"
            reasons[reason] += 1
            routes.append({**base, "route_geometry_bundle_certified": False, "reason_code": reason, "publication_allowed": False})
            continue

        hash_input = [
            {
                "edge_index": edge["edge_index"],
                "ordered_node_pair": edge["ordered_node_pair"],
                "geometry_sha256": edge["geometry_sha256"],
            }
            for edge in ordered
        ]
        bundle_hash = _hash(hash_input)
        reason = "ORDERED_SOURCE_GEOMETRY_BUNDLE_CERTIFIED"
        reasons[reason] += 1
        certified += 1
        occurrence_coverage += int(row.get("occurrence_count") or 0)
        component_edge_count += len(ordered)
        routes.append({
            **base,
            "route_geometry_bundle_certified": True,
            "reason_code": reason,
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "publication_allowed": False,
            "projector_consumed": False,
            "public_renderer_enabled": False,
            "route_edge_count": len(ordered),
            "route_bundle_sha256": bundle_hash,
            "ordered_source_edges": ordered,
            "dissolved_geometry_created": False,
            "concatenated_geometry_created": False,
            "endpoint_snapping_used": False,
            "synthetic_coordinate_count": 0,
        })

    input_routes = len([row for row in (v6.get("routes") or []) if isinstance(row, dict)])
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "location_cache_modified": False,
        "public_map_modified": False,
        "dissolved_geometry_created": False,
        "concatenated_geometry_created": False,
        "endpoint_snapping_used": False,
        "synthetic_coordinate_count": 0,
        "input_v6_route_count": input_routes,
        "route_geometry_bundle_certified_count": certified,
        "route_geometry_bundle_certified_occurrence_count": occurrence_coverage,
        "certified_component_edge_count": component_edge_count,
        "route_geometry_bundle_blocked_count": len(routes) - certified,
        "reason_counts": dict(sorted(reasons.items())),
        "hard_zero_gates": {
            "publication_count": 0,
            "exact_pin_eligible_count": 0,
            "point_generated_count": 0,
            "midpoint_publication_count": 0,
            "projector_consumed_count": 0,
            "location_cache_write_count": 0,
            "public_map_write_count": 0,
            "public_renderer_count": 0,
            "dissolved_route_geometry_count": 0,
            "concatenated_route_geometry_count": 0,
            "synthetic_coordinate_count": 0,
        },
        "routes": routes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v6-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(json.loads(args.v6_report.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version",
        "input_v6_route_count",
        "route_geometry_bundle_certified_count",
        "route_geometry_bundle_certified_occurrence_count",
        "certified_component_edge_count",
        "route_geometry_bundle_blocked_count",
        "reason_counts",
        "hard_zero_gates",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
