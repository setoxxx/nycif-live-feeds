#!/usr/bin/env python3
"""Certify ordered GeoSupport 3S route topology for V4-blocked street claims.

This is a NONPUBLIC_EVIDENCE_ONLY topology audit. It targets only V4 entries
blocked by LION_GEOMETRY_ENDPOINT_DISAGREEMENT and asks NYC Planning Geosupport
Function 3S for the ordered list of intersections along the stated on/from/to
street stretch.

A route topology candidate survives only when:
- the original street-between claim parses;
- 3S returns a self-consistent intersection count;
- the ordered node list has at least two unique nodes and no repeated node;
- the first/last 3S nodes exactly equal the two independently certified V2
  endpoint nodes, in either forward or reverse order;
- the route remains below a conservative node-count cap.

This script does not join geometry, does not choose a shortest path, does not
create a point, and grants no Projector/publication authority.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.audit_street_segment_geosupport_recovery_v2 import borough_code
    from scripts.nyc_location_resolver import parse_street_between
except ModuleNotFoundError:  # pragma: no cover
    from audit_street_segment_geosupport_recovery_v2 import borough_code
    from nyc_location_resolver import parse_street_between

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_GEOSUPPORT_3S_ROUTE_AUDIT_V5"
MAX_ROUTE_NODES = 80
TARGET_V4_REASON = "LION_GEOMETRY_ENDPOINT_DISAGREEMENT"


def _node(value: Any) -> str:
    text = str(value or "").strip()
    return text.zfill(7) if text.isdigit() else text


def _intersection_node(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("Node Number", "Node Number of Intersection", "LION Node Number"):
        if key in row:
            return _node(row.get(key))
    return ""


class GeoSupport3SRouteEvidence:
    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.call_count = 0

    def resolve(self, v4_entry: dict[str, Any]) -> dict[str, Any]:
        display = str(v4_entry.get("event_location") or "").strip()
        borough = str(v4_entry.get("borough") or "").strip()
        parsed = parse_street_between(display)
        if not parsed:
            return {"route_topology_certified": False, "reason_code": "NOT_STREET_BETWEEN_CLAIM"}
        code = borough_code(borough)
        if not code:
            return {"route_topology_certified": False, "reason_code": "BOROUGH_UNSUPPORTED"}
        main_street, cross1, cross2 = parsed

        try:
            self.call_count += 1
            result = self.backend.call(
                {
                    "function": "3S",
                    "borough_code": code,
                    "on": main_street,
                    "from": cross1,
                    "to": cross2,
                }
            )
        except Exception:
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_UNRESOLVED"}
        if not isinstance(result, dict):
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_NONDICT"}

        rows = result.get("LIST OF INTERSECTIONS")
        if not isinstance(rows, list):
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_INTERSECTION_LIST_MISSING"}
        try:
            declared_count = int(str(result.get("Number of Intersections") or "").strip())
        except ValueError:
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_COUNT_INVALID"}
        if declared_count != len(rows):
            return {
                "route_topology_certified": False,
                "reason_code": "GEOSUPPORT_3S_COUNT_MISMATCH",
                "declared_intersection_count": declared_count,
                "returned_intersection_count": len(rows),
            }

        nodes = [_intersection_node(row) for row in rows]
        if any(not node for node in nodes):
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_NODE_MISSING"}
        if len(nodes) < 2:
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_ROUTE_TOO_SHORT"}
        if len(nodes) > MAX_ROUTE_NODES:
            return {
                "route_topology_certified": False,
                "reason_code": "GEOSUPPORT_3S_ROUTE_TOO_LONG",
                "route_node_count": len(nodes),
            }
        if len(set(nodes)) != len(nodes):
            return {"route_topology_certified": False, "reason_code": "GEOSUPPORT_3S_ROUTE_REPEATS_NODE"}

        expected_1 = _node((v4_entry.get("endpoint_1") or {}).get("node"))
        expected_2 = _node((v4_entry.get("endpoint_2") or {}).get("node"))
        if not expected_1 or not expected_2:
            return {"route_topology_certified": False, "reason_code": "CERTIFIED_ENDPOINT_NODE_MISSING"}

        if nodes[0] == expected_1 and nodes[-1] == expected_2:
            orientation = "FORWARD"
        elif nodes[0] == expected_2 and nodes[-1] == expected_1:
            orientation = "REVERSE"
        else:
            return {
                "route_topology_certified": False,
                "reason_code": "GEOSUPPORT_3S_ENDPOINT_NODE_MISMATCH",
                "expected_endpoint_nodes": [expected_1, expected_2],
                "returned_terminal_nodes": [nodes[0], nodes[-1]],
                "route_node_count": len(nodes),
            }

        edge_pairs = [[nodes[index], nodes[index + 1]] for index in range(len(nodes) - 1)]
        return {
            "route_topology_certified": True,
            "reason_code": "GEOSUPPORT_3S_ORDERED_ENDPOINTS_AGREE",
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "publication_allowed": False,
            "exact_pin_eligible": False,
            "projector_consumed": False,
            "public_renderer_enabled": False,
            "route_orientation": orientation,
            "ordered_node_numbers": nodes,
            "ordered_edge_node_pairs": edge_pairs,
            "route_node_count": len(nodes),
            "route_edge_count": len(edge_pairs),
            "geometry_joined": False,
            "shortest_path_algorithm_used": False,
        }


def audit(v4_report: dict[str, Any], backend: Any) -> dict[str, Any]:
    if v4_report.get("schema_version") != "NYCIF_STREET_SEGMENT_LION_GEOMETRY_AUDIT_V4":
        raise ValueError("unexpected V4 report schema")
    if v4_report.get("publication_authority_granted") is not False:
        raise ValueError("V4 report unexpectedly grants publication authority")
    if v4_report.get("projector_consumed") is not False:
        raise ValueError("V4 report unexpectedly consumed by Projector")

    targets = [
        entry for entry in (v4_report.get("entries") or [])
        if isinstance(entry, dict)
        and entry.get("geometry_joined") is not True
        and entry.get("reason_code") == TARGET_V4_REASON
    ]
    evidence = GeoSupport3SRouteEvidence(backend)
    rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    certified = 0
    certified_occurrences = 0

    for target in targets:
        result = evidence.resolve(target)
        reason = str(result.get("reason_code") or "UNSPECIFIED")
        reasons[reason] += 1
        if result.get("route_topology_certified") is True:
            certified += 1
            certified_occurrences += int(target.get("occurrence_count") or 0)
        rows.append(
            {
                "claim_key": target.get("claim_key"),
                "borough": target.get("borough"),
                "event_location": target.get("event_location"),
                "occurrence_count": target.get("occurrence_count"),
                "source_event_ids": target.get("source_event_ids"),
                "endpoint_1": target.get("endpoint_1"),
                "endpoint_2": target.get("endpoint_2"),
                "v4_reason_code": target.get("reason_code"),
                **result,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "parent_v4_schema_version": v4_report.get("schema_version"),
        "source_authority": "NYC Planning Geosupport Desktop Edition Function 3S",
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "location_cache_modified": False,
        "public_map_modified": False,
        "geometry_join_completed": False,
        "shortest_path_algorithm_used": False,
        "target_v4_reason": TARGET_V4_REASON,
        "target_claim_count": len(targets),
        "target_occurrence_count": sum(int(entry.get("occurrence_count") or 0) for entry in targets),
        "route_topology_certified_count": certified,
        "route_topology_certified_occurrence_count": certified_occurrences,
        "route_topology_blocked_count": len(targets) - certified,
        "geosupport_3s_call_count": evidence.call_count,
        "reason_counts": dict(sorted(reasons.items())),
        "hard_zero_gates": {
            "publication_count": 0,
            "exact_pin_eligible_count": 0,
            "point_generated_count": 0,
            "midpoint_publication_count": 0,
            "projector_consumed_count": 0,
            "location_cache_write_count": 0,
            "public_map_write_count": 0,
            "geometry_join_count": 0,
        },
        "routes": rows,
    }


def load_backend() -> Any:
    try:
        from geosupport import Geosupport
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("GeoSupport runtime is required for the live V5 audit") from exc
    return Geosupport()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v4-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    v4 = json.loads(args.v4_report.read_text(encoding="utf-8"))
    result = audit(v4, load_backend())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version",
        "target_claim_count",
        "target_occurrence_count",
        "route_topology_certified_count",
        "route_topology_certified_occurrence_count",
        "route_topology_blocked_count",
        "geosupport_3s_call_count",
        "reason_counts",
        "hard_zero_gates",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
