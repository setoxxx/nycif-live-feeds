#!/usr/bin/env python3
"""Build a NONPUBLIC occurrence-level registry for certified route evidence.

V9 does not infer occurrence identity from aggregate counts or repeated source
IDs. It rebinds every V8-conformant route one-to-one through V7, V5, and V2,
then reconstructs the exact current/future raw rows for that claim and applies
the repository's occurrence_key_v2 contract:

    (dataset, source_event_id, exact source occurrence start)

This lane is specific to the NYC Open Data Permitted Event Information feed
(`tvpp-9vvx`). Live Socrata resource rows do not necessarily carry a dataset
field, so V9 restores that known source provenance only when it is absent. It
never rewrites an explicit source dataset supplied by an input row.

Any ambiguous occurrence start, duplicate occurrence key, source-ID multiset
mismatch, claim-count mismatch, or upstream handoff mismatch blocks registry
conformance. The registry stores route bundle hashes only; it grants no public
renderer, Projector, MAP_READY, point, cache, map, or publication authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.audit_street_segment_geoclient_recovery import claim_key
    from scripts.nyc_location_resolver import parse_street_between
    from scripts.occurrence_identity_contract import identity_precision, occurrence_key_v2
    from scripts.sync_nyc_open_data import date_key
except ModuleNotFoundError:  # pragma: no cover
    from audit_street_segment_geoclient_recovery import claim_key
    from nyc_location_resolver import parse_street_between
    from occurrence_identity_contract import identity_precision, occurrence_key_v2
    from sync_nyc_open_data import date_key

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_ROUTE_OCCURRENCE_REGISTRY_V9"
V2_SCHEMA = "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2"
V5_SCHEMA = "NYCIF_STREET_SEGMENT_GEOSUPPORT_3S_ROUTE_AUDIT_V5"
V7_SCHEMA = "NYCIF_STREET_SEGMENT_ROUTE_GEOMETRY_BUNDLE_AUDIT_V7"
V8_SCHEMA = "NYCIF_STREET_SEGMENT_ROUTE_EVIDENCE_CONTRACT_AUDIT_V8"
EVIDENCE_CLASS = "NYCIF_EXACT_ROUTE_OCCURRENCE_NONPUBLIC_V1"
TVPP_DATASET_ID = "tvpp-9vvx"


def _sha(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _single_by_claim(rows: list[dict[str, Any]], predicate) -> tuple[dict[str, dict[str, Any]], set[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row, dict) and predicate(row):
            grouped[str(row.get("claim_key") or "").strip()].append(row)
    mapping: dict[str, dict[str, Any]] = {}
    non_unique: set[str] = set()
    for key, values in grouped.items():
        if key and len(values) == 1:
            mapping[key] = values[0]
        else:
            non_unique.add(key)
    return mapping, non_unique


def _with_tvpp_provenance(row: dict[str, Any]) -> dict[str, Any]:
    """Restore known TVPP dataset provenance only when the source omitted it."""
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    explicit = row.get("source_dataset") or row.get("dataset") or source.get("dataset")
    if str(explicit or "").strip():
        return row
    normalized = dict(row)
    normalized["source_dataset"] = TVPP_DATASET_ID
    return normalized


def _raw_current_street_rows(raw_rows: list[dict[str, Any]], today_nyc: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for original in raw_rows:
        if not isinstance(original, dict):
            continue
        row = _with_tvpp_provenance(original)
        if date_key(row.get("start_date_time")) < today_nyc:
            continue
        location = str(row.get("event_location") or row.get("location") or "").strip()
        borough = str(row.get("event_borough") or row.get("borough") or "").strip()
        if not borough or not parse_street_between(location):
            continue
        grouped[claim_key(row)].append(row)
    return grouped


def audit(
    *,
    v2: dict[str, Any],
    v5: dict[str, Any],
    v7: dict[str, Any],
    v8: dict[str, Any],
    raw_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if v2.get("schema_version") != V2_SCHEMA:
        raise ValueError("unexpected V2 schema")
    if v5.get("schema_version") != V5_SCHEMA:
        raise ValueError("unexpected V5 schema")
    if v7.get("schema_version") != V7_SCHEMA:
        raise ValueError("unexpected V7 schema")
    if v8.get("schema_version") != V8_SCHEMA:
        raise ValueError("unexpected V8 schema")
    if v8.get("contract_conformance_pass") is not True:
        raise ValueError("V8 contract is not conformant")
    if v8.get("release_status") != "NONPUBLIC_EVIDENCE_ONLY":
        raise ValueError("V8 release boundary is not non-public")
    for obj, keys in (
        (v5, ("publication_authority_granted", "projector_consumed")),
        (v7, ("publication_authority_granted", "public_renderer_enabled", "projector_consumed")),
        (v8, ("publication_authority_granted", "public_renderer_enabled", "projector_consumed", "promotion_allowed")),
    ):
        for key in keys:
            if obj.get(key) is not False:
                raise ValueError(f"upstream safety boundary violated: {key}")

    today_nyc = str(v2.get("today_nyc") or "").strip()
    if not today_nyc:
        raise ValueError("V2 today_nyc missing")

    v2_map, v2_non_unique = _single_by_claim(
        v2.get("claims") or [], lambda row: row.get("strict_nonpublic_segment_evidence") is True
    )
    v5_map, v5_non_unique = _single_by_claim(
        v5.get("routes") or [], lambda row: row.get("route_topology_certified") is True
    )
    v7_map, v7_non_unique = _single_by_claim(
        v7.get("routes") or [], lambda row: row.get("route_geometry_bundle_certified") is True
    )
    v8_conformant = [
        row for row in (v8.get("routes") or [])
        if isinstance(row, dict) and row.get("contract_conformant") is True
    ]
    v8_claim_counts = Counter(str(row.get("claim_key") or "").strip() for row in v8_conformant)
    raw_by_claim = _raw_current_street_rows(raw_rows, today_nyc)

    gates: Counter[str] = Counter()
    registry: list[dict[str, Any]] = []
    registry_occurrence_keys: Counter[tuple[str, str, str]] = Counter()
    registry_claim_counts: Counter[str] = Counter()
    source_id_counts: Counter[tuple[str, str]] = Counter()
    exact_start_count = 0
    day_precision_count = 0

    for claim in sorted(v8_claim_counts):
        if not claim or v8_claim_counts[claim] != 1:
            gates["v8_claim_handoff_not_unique_count"] += 1
            continue
        if claim in v2_non_unique or claim not in v2_map:
            gates["v2_claim_handoff_not_unique_count"] += 1
            continue
        if claim in v5_non_unique or claim not in v5_map:
            gates["v5_claim_handoff_not_unique_count"] += 1
            continue
        if claim in v7_non_unique or claim not in v7_map:
            gates["v7_claim_handoff_not_unique_count"] += 1
            continue

        c2, c5, c7 = v2_map[claim], v5_map[claim], v7_map[claim]
        counts = [
            int(c2.get("occurrence_count") or 0),
            int(c5.get("occurrence_count") or 0),
            int(c7.get("occurrence_count") or 0),
        ]
        if len(set(counts)) != 1 or counts[0] <= 0:
            gates["claim_occurrence_count_mismatch_count"] += 1
            continue
        expected_count = counts[0]

        ids2 = [str(value or "").strip() for value in (c2.get("source_event_ids") or [])]
        ids5 = [str(value or "").strip() for value in (c5.get("source_event_ids") or [])]
        if Counter(ids2) != Counter(ids5) or len(ids2) != expected_count or any(not value for value in ids2):
            gates["source_event_id_multiset_mismatch_count"] += 1
            continue

        raw_claim_rows = raw_by_claim.get(claim, [])
        if len(raw_claim_rows) != expected_count:
            gates["raw_claim_occurrence_count_mismatch_count"] += 1
            continue
        raw_ids = [str(row.get("event_id") or row.get("source_event_id") or "").strip() for row in raw_claim_rows]
        if Counter(raw_ids) != Counter(ids2):
            gates["raw_source_event_id_multiset_mismatch_count"] += 1
            continue

        bundle_hash = str(c7.get("route_bundle_sha256") or "").strip()
        if len(bundle_hash) != 64:
            gates["route_bundle_hash_missing_count"] += 1
            continue

        claim_entries: list[dict[str, Any]] = []
        claim_failed = False
        for raw in raw_claim_rows:
            precision = identity_precision(raw)
            if precision == "AMBIGUOUS":
                gates["ambiguous_occurrence_identity_count"] += 1
                claim_failed = True
                break
            occurrence = occurrence_key_v2(raw)
            if not all(str(value or "").strip() for value in occurrence):
                gates["ambiguous_occurrence_identity_count"] += 1
                claim_failed = True
                break
            dataset, event_id, start = occurrence
            registry_key = _sha({
                "occurrence_key_v2": [dataset, event_id, start],
                "claim_key": claim,
                "route_bundle_sha256": bundle_hash,
            })
            claim_entries.append({
                "registry_key": registry_key,
                "evidence_class": EVIDENCE_CLASS,
                "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
                "publication_allowed": False,
                "exact_pin_eligible": False,
                "public_renderer_enabled": False,
                "projector_consumed": False,
                "claim_key": claim,
                "route_bundle_sha256": bundle_hash,
                "source_dataset": dataset,
                "source_event_id": event_id,
                "occurrence_start": start,
                "occurrence_identity_precision": precision,
                "occurrence_key_v2": [dataset, event_id, start],
            })

        if claim_failed:
            continue
        for entry in claim_entries:
            occurrence_tuple = tuple(entry["occurrence_key_v2"])
            registry_occurrence_keys[occurrence_tuple] += 1
            registry_claim_counts[claim] += 1
            source_id_counts[(entry["source_dataset"], entry["source_event_id"])] += 1
            if entry["occurrence_identity_precision"] == "EXACT_START":
                exact_start_count += 1
            elif entry["occurrence_identity_precision"] == "DAY":
                day_precision_count += 1
            registry.append(entry)

    gates["duplicate_occurrence_key_count"] = sum(
        1 for count in registry_occurrence_keys.values() if count > 1
    )
    gates["duplicate_registry_key_count"] = len(registry) - len({entry["registry_key"] for entry in registry})

    for claim, count in v8_claim_counts.items():
        if count == 1 and claim in v2_map:
            expected = int(v2_map[claim].get("occurrence_count") or 0)
            actual = registry_claim_counts[claim]
            if actual != expected:
                gates["silent_occurrence_identity_loss_count"] += max(expected - actual, 0)
                gates["unexpected_occurrence_identity_gain_count"] += max(actual - expected, 0)

    required_gate_names = (
        "v8_claim_handoff_not_unique_count",
        "v2_claim_handoff_not_unique_count",
        "v5_claim_handoff_not_unique_count",
        "v7_claim_handoff_not_unique_count",
        "claim_occurrence_count_mismatch_count",
        "source_event_id_multiset_mismatch_count",
        "raw_claim_occurrence_count_mismatch_count",
        "raw_source_event_id_multiset_mismatch_count",
        "route_bundle_hash_missing_count",
        "ambiguous_occurrence_identity_count",
        "duplicate_occurrence_key_count",
        "duplicate_registry_key_count",
        "silent_occurrence_identity_loss_count",
        "unexpected_occurrence_identity_gain_count",
    )
    hard_gates = {name: int(gates[name]) for name in required_gate_names}
    hard_gates.update({
        "publication_count": 0,
        "exact_pin_candidate_count": 0,
        "public_renderer_count": 0,
        "projector_consumed_count": 0,
        "location_cache_write_count": 0,
        "public_map_write_count": 0,
        "point_generated_count": 0,
    })
    conformant = all(value == 0 for value in hard_gates.values())

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_nyc": today_nyc,
        "source_dataset_authority": TVPP_DATASET_ID,
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "location_cache_modified": False,
        "public_map_modified": False,
        "registry_conformance_pass": conformant,
        "input_v8_conformant_route_count": len(v8_conformant),
        "registry_route_count": len(registry_claim_counts),
        "registry_occurrence_count": len(registry),
        "unique_occurrence_key_v2_count": len(registry_occurrence_keys),
        "unique_source_event_id_count": len(source_id_counts),
        "recurring_source_event_id_count": sum(1 for count in source_id_counts.values() if count > 1),
        "exact_start_occurrence_count": exact_start_count,
        "day_precision_occurrence_count": day_precision_count,
        "hard_zero_gates": hard_gates,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "registry": sorted(
            registry,
            key=lambda row: (row["claim_key"], row["occurrence_start"], row["source_event_id"]),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v2-report", type=Path, required=True)
    parser.add_argument("--v5-report", type=Path, required=True)
    parser.add_argument("--v7-report", type=Path, required=True)
    parser.add_argument("--v8-report", type=Path, required=True)
    parser.add_argument("--raw-rows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = json.loads(args.raw_rows.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("raw rows input must be a list")
    result = audit(
        v2=json.loads(args.v2_report.read_text(encoding="utf-8")),
        v5=json.loads(args.v5_report.read_text(encoding="utf-8")),
        v7=json.loads(args.v7_report.read_text(encoding="utf-8")),
        v8=json.loads(args.v8_report.read_text(encoding="utf-8")),
        raw_rows=raw,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version", "registry_conformance_pass", "source_dataset_authority",
        "input_v8_conformant_route_count", "registry_route_count", "registry_occurrence_count",
        "unique_occurrence_key_v2_count", "unique_source_event_id_count",
        "recurring_source_event_id_count", "exact_start_occurrence_count",
        "day_precision_occurrence_count", "hard_zero_gates", "release_status",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0 if result["registry_conformance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
