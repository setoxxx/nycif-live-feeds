#!/usr/bin/env python3
"""Audit GeoSupport street-segment recovery evidence against V1 contract.

Conformance means NONPUBLIC_EVIDENCE_ONLY. This audit cannot grant Projector,
MAP_READY, cache, renderer, or publication authority.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

CONTRACT_TYPE = "nycif_exact_event_street_segment_evidence_contract_v1"
REPORT_SCHEMA = "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def audit(contract: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if contract.get("artifact_type") != CONTRACT_TYPE:
        raise ValueError("wrong street-segment evidence contract type")
    if contract.get("status") != "recovery_evidence_only":
        raise ValueError("street-segment evidence contract is not recovery-only")
    scope = contract.get("scope") or {}
    if scope.get("publication_authority_granted") is not False:
        raise ValueError("contract unexpectedly grants publication authority")
    if scope.get("projector_consumption_enabled") is not False:
        raise ValueError("contract unexpectedly enables Projector consumption")
    if scope.get("official_centerline_geometry_join_completed") is not False:
        raise ValueError("identity contract must not claim centerline geometry is joined")

    if report.get("schema_version") != REPORT_SCHEMA:
        raise ValueError("wrong GeoSupport audit schema")
    if report.get("geometry_join_status") != "SEGMENT_IDENTIFIER_ONLY_GEOMETRY_NOT_YET_JOINED":
        raise ValueError("unexpected geometry join status")

    for field in (
        "read_only",
        "promotion_allowed",
        "publication_authority_granted",
        "public_map_modified",
        "location_cache_modified",
        "projector_consumed",
    ):
        expected = field == "read_only"
        if report.get(field) is not expected:
            raise ValueError(f"report safety field failed: {field}={report.get(field)!r}")

    hard_zeros = report.get("hard_zero_gates") or {}
    nonzero_hard_gates = {
        key: value for key, value in hard_zeros.items()
        if isinstance(value, bool) or not isinstance(value, int) or value != 0
    }

    required_fields = set(contract.get("required_strict_entry_fields") or [])
    required_endpoint_fields = set(contract.get("required_endpoint_fields") or [])
    required_values = contract.get("required_strict_values") or {}

    invalid_reasons: Counter[str] = Counter()
    strict_entries: list[dict[str, Any]] = []
    segment_ids: Counter[str] = Counter()
    node_pairs: Counter[tuple[str, str]] = Counter()

    for entry in report.get("claims") or []:
        if entry.get("strict_nonpublic_segment_evidence") is not True:
            continue
        strict_entries.append(entry)
        missing = sorted(field for field in required_fields if field not in entry)
        if missing:
            invalid_reasons["MISSING_REQUIRED_FIELD"] += 1
            continue
        if any(entry.get(key) != value for key, value in required_values.items()):
            invalid_reasons["REQUIRED_STRICT_VALUE_MISMATCH"] += 1
            continue

        endpoint_1 = entry.get("endpoint_1")
        endpoint_2 = entry.get("endpoint_2")
        if not isinstance(endpoint_1, dict) or not isinstance(endpoint_2, dict):
            invalid_reasons["ENDPOINT_OBJECT_MISSING"] += 1
            continue
        if any(field not in endpoint_1 for field in required_endpoint_fields) or any(
            field not in endpoint_2 for field in required_endpoint_fields
        ):
            invalid_reasons["ENDPOINT_FIELD_MISSING"] += 1
            continue

        node_1 = str(endpoint_1.get("node") or "").strip()
        node_2 = str(endpoint_2.get("node") or "").strip()
        from_node = str(entry.get("function_3_from_node") or "").strip()
        to_node = str(entry.get("function_3_to_node") or "").strip()
        if not node_1 or not node_2 or node_1 == node_2:
            invalid_reasons["ENDPOINT_NODE_INVALID"] += 1
            continue
        if {node_1, node_2} != {from_node, to_node}:
            invalid_reasons["FUNCTION_3_NODE_PAIR_MISMATCH"] += 1
            continue

        segment_id = str(entry.get("function_3_segment_identifier") or "").strip()
        if not segment_id:
            invalid_reasons["SEGMENT_IDENTIFIER_MISSING"] += 1
            continue
        segment_ids[segment_id] += 1
        node_pairs[tuple(sorted((node_1, node_2)))] += 1

        midpoint = entry.get("candidate_midpoint")
        if not isinstance(midpoint, dict) or midpoint.get(
            "must_not_be_used_as_public_exact_point"
        ) is not True:
            invalid_reasons["MIDPOINT_PUBLICATION_PROHIBITION_MISSING"] += 1

    duplicate_segment_ids = sum(1 for count in segment_ids.values() if count > 1)
    duplicate_node_pairs = sum(1 for count in node_pairs.values() if count > 1)
    reported_strict = report.get("strict_nonpublic_segment_evidence_count")
    count_mismatch = reported_strict != len(strict_entries)

    summary = {
        "artifact_type": "nycif_exact_event_street_segment_evidence_contract_audit_v1",
        "contract_status": contract.get("status"),
        "input_claim_count": len(report.get("claims") or []),
        "strict_entry_count": len(strict_entries),
        "reported_strict_entry_count": reported_strict,
        "strict_entry_count_mismatch": count_mismatch,
        "invalid_strict_entry_count": sum(invalid_reasons.values()),
        "invalid_reason_counts": dict(sorted(invalid_reasons.items())),
        "unique_segment_identifier_count": len(segment_ids),
        "duplicate_segment_identifier_count": duplicate_segment_ids,
        "unique_endpoint_node_pair_count": len(node_pairs),
        "duplicate_endpoint_node_pair_count": duplicate_node_pairs,
        "nonzero_or_malformed_hard_zero_gates": nonzero_hard_gates,
        "geometry_join_completed": False,
        "publication_authority_granted": False,
        "projector_consumed": False,
        "public_renderer_enabled": False,
        "conforms": (
            not count_mismatch
            and not invalid_reasons
            and duplicate_segment_ids == 0
            and duplicate_node_pairs == 0
            and not nonzero_hard_gates
        ),
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = audit(_load(args.contract), _load(args.report))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["conforms"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
