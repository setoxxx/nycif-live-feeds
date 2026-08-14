#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_ROUTE_EVIDENCE_CONTRACT_AUDIT_V8"
V7_SCHEMA = "NYCIF_STREET_SEGMENT_ROUTE_GEOMETRY_BUNDLE_AUDIT_V7"
CONTRACT_TYPE = "nycif_exact_event_route_evidence_contract_v1"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def audit(contract: dict[str, Any], v7: dict[str, Any]) -> dict[str, Any]:
    if contract.get("artifact_type") != CONTRACT_TYPE:
        raise ValueError("unexpected route contract")
    if contract.get("release_status") != "NONPUBLIC_EVIDENCE_ONLY":
        raise ValueError("route contract must remain non-public")
    scope = contract.get("scope") or {}
    if (
        scope.get("publication_authority_granted") is not False
        or scope.get("public_renderer_enabled") is not False
        or scope.get("projector_consumption_enabled") is not False
    ):
        raise ValueError("route contract safety scope violated")
    if v7.get("schema_version") != V7_SCHEMA:
        raise ValueError("unexpected V7 schema")
    for key in ("publication_authority_granted", "public_renderer_enabled", "projector_consumed"):
        if v7.get(key) is not False:
            raise ValueError(f"V7 safety boundary violated: {key}")
    if any(
        v7.get(key) not in (False, 0)
        for key in (
            "dissolved_geometry_created",
            "concatenated_geometry_created",
            "endpoint_snapping_used",
            "synthetic_coordinate_count",
        )
    ):
        raise ValueError("V7 transformation boundary violated")

    allowed = set(contract.get("allowed_geometry_types") or [])
    required_route = set(contract.get("required_route_fields") or [])
    required_component = set(contract.get("required_component_fields") or [])
    counts: Counter[str] = Counter()
    claim_counts: Counter[str] = Counter()
    validated = 0
    component_count = 0
    route_summaries: list[dict[str, Any]] = []

    for route in v7.get("routes") or []:
        if not isinstance(route, dict):
            counts["invalid_route_entry_count"] += 1
            continue
        missing = sorted(key for key in required_route if key not in route)
        claim = str(route.get("claim_key") or "").strip()
        claim_counts[claim] += 1
        valid = True
        reasons: list[str] = []
        if missing:
            valid = False
            reasons.append("REQUIRED_ROUTE_FIELD_MISSING")
        if route.get("route_geometry_bundle_certified") is not True:
            valid = False
            reasons.append("ROUTE_NOT_CERTIFIED")
        if (
            route.get("publication_state") != "NONPUBLIC_EVIDENCE_ONLY"
            or route.get("publication_allowed") is not False
            or route.get("projector_consumed") is not False
            or route.get("public_renderer_enabled") is not False
        ):
            valid = False
            reasons.append("ROUTE_PUBLICATION_BOUNDARY_INVALID")
        if (
            route.get("dissolved_geometry_created") is not False
            or route.get("concatenated_geometry_created") is not False
            or route.get("endpoint_snapping_used") is not False
            or route.get("synthetic_coordinate_count") != 0
        ):
            valid = False
            reasons.append("ROUTE_TRANSFORMATION_BOUNDARY_INVALID")

        edges = route.get("ordered_source_edges")
        if not isinstance(edges, list) or not edges or len(edges) != int(route.get("route_edge_count") or 0):
            valid = False
            reasons.append("ROUTE_EDGE_COUNT_INVALID")
            edges = [] if not isinstance(edges, list) else edges

        hash_input: list[dict[str, Any]] = []
        previous_to: Any = None
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                counts["invalid_component_entry_count"] += 1
                valid = False
                reasons.append("COMPONENT_NOT_OBJECT")
                continue
            component_count += 1
            if any(key not in edge for key in required_component):
                counts["invalid_component_entry_count"] += 1
                valid = False
                reasons.append("COMPONENT_FIELD_MISSING")
            pair = edge.get("ordered_node_pair")
            geometry = edge.get("geometry")
            stored_hash = edge.get("geometry_sha256")
            if edge.get("edge_index") != index:
                counts["invalid_component_entry_count"] += 1
                valid = False
                reasons.append("COMPONENT_INDEX_INVALID")
            if not isinstance(pair, list) or len(pair) != 2 or not all(str(value or "").strip() for value in pair):
                counts["invalid_component_entry_count"] += 1
                valid = False
                reasons.append("COMPONENT_NODE_PAIR_INVALID")
                pair = ["", ""]
            if index > 0 and previous_to is not None and pair[0] != previous_to:
                counts["route_topology_discontinuity_count"] += 1
                valid = False
                reasons.append("ROUTE_TOPOLOGY_DISCONTINUITY")
            previous_to = pair[1] if len(pair) == 2 else None
            if not isinstance(geometry, dict) or geometry.get("type") not in allowed:
                counts["invalid_component_entry_count"] += 1
                valid = False
                reasons.append("COMPONENT_GEOMETRY_INVALID")
            elif not isinstance(stored_hash, str) or digest(geometry) != stored_hash:
                counts["component_geometry_hash_mismatch_count"] += 1
                valid = False
                reasons.append("COMPONENT_GEOMETRY_HASH_MISMATCH")
            hash_input.append({
                "edge_index": index,
                "ordered_node_pair": pair,
                "geometry_sha256": stored_hash,
            })

        stored_bundle_hash = route.get("route_bundle_sha256")
        if isinstance(stored_bundle_hash, str) and digest(hash_input) != stored_bundle_hash:
            counts["route_bundle_hash_mismatch_count"] += 1
            valid = False
            reasons.append("ROUTE_BUNDLE_HASH_MISMATCH")
        elif not isinstance(stored_bundle_hash, str):
            counts["route_bundle_hash_mismatch_count"] += 1
            valid = False
            reasons.append("ROUTE_BUNDLE_HASH_MISSING")

        if valid:
            validated += 1
        else:
            counts["invalid_route_entry_count"] += 1
        route_summaries.append({
            "claim_key": claim,
            "contract_conformant": valid,
            "reason_codes": sorted(set(reasons)),
        })

    duplicate_claims = sum(1 for key, count in claim_counts.items() if not key or count > 1)
    counts["duplicate_claim_key_count"] = duplicate_claims
    gates = {
        "invalid_route_entry_count": counts["invalid_route_entry_count"],
        "invalid_component_entry_count": counts["invalid_component_entry_count"],
        "component_geometry_hash_mismatch_count": counts["component_geometry_hash_mismatch_count"],
        "route_bundle_hash_mismatch_count": counts["route_bundle_hash_mismatch_count"],
        "route_topology_discontinuity_count": counts["route_topology_discontinuity_count"],
        "duplicate_claim_key_count": duplicate_claims,
        "point_generated_count": 0,
        "midpoint_publication_count": 0,
        "dissolved_route_geometry_count": 0,
        "concatenated_route_geometry_count": 0,
        "synthetic_coordinate_count": 0,
        "publication_eligible_count": 0,
        "exact_pin_candidate_count": 0,
        "public_renderer_enabled": False,
        "projector_consumed": False,
    }
    expected = contract.get("contract_audit_gates") or {}
    expected_gates = {key.removesuffix("_required"): value for key, value in expected.items()}
    contract_pass = all(gates.get(key) == value for key, value in expected_gates.items())

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "contract_artifact_type": CONTRACT_TYPE,
        "contract_conformance_pass": contract_pass,
        "input_route_count": len([route for route in (v7.get("routes") or []) if isinstance(route, dict)]),
        "validated_route_count": validated,
        "validated_component_count": component_count,
        "audit_gates": gates,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "promotion_allowed": False,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "routes": route_summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--v7-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        json.loads(args.contract.read_text(encoding="utf-8")),
        json.loads(args.v7_report.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version",
        "contract_conformance_pass",
        "input_route_count",
        "validated_route_count",
        "validated_component_count",
        "audit_gates",
        "release_status",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0 if result["contract_conformance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
