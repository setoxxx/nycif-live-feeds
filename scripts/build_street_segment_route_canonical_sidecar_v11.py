#!/usr/bin/env python3
"""Build a NONPUBLIC canonical sidecar registry from certified V10 handoffs.

V11 stores references only. It does not copy route geometry, coordinates, or
public fields into canonical events. Every row is bound to an already-certified
V10 canonical occurrence and its frozen V9 route registry/bundle identifiers.
No Projector, renderer, cache, map, publication, or canonical-write authority is
granted by this registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_ROUTE_CANONICAL_SIDECAR_V11"
V10_SCHEMA = "NYCIF_STREET_SEGMENT_ROUTE_CANONICAL_HANDOFF_AUDIT_V10"
EVIDENCE_CLASS = "NYCIF_CANONICAL_ROUTE_SIDECAR_NONPUBLIC_V1"


def _sha(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def build(v10: dict[str, Any]) -> dict[str, Any]:
    if v10.get("schema_version") != V10_SCHEMA:
        raise ValueError("unexpected V10 schema")
    if v10.get("handoff_conformance_pass") is not True:
        raise ValueError("V10 handoff is not conformant")
    if v10.get("release_status") != "NONPUBLIC_EVIDENCE_ONLY":
        raise ValueError("V10 release boundary is not non-public")
    for key in (
        "publication_authority_granted",
        "public_renderer_enabled",
        "projector_consumed",
        "promotion_allowed",
        "canonical_modified",
        "reader_safe_modified",
    ):
        if v10.get(key) is not False:
            raise ValueError(f"V10 safety boundary violated: {key}")
    upstream_gates = v10.get("hard_zero_gates") if isinstance(v10.get("hard_zero_gates"), dict) else {}
    if not upstream_gates or any(int(value or 0) != 0 for value in upstream_gates.values()):
        raise ValueError("V10 hard-zero gates are not all zero")

    expected = int(v10.get("canonical_handoff_certified_count") or 0)
    if expected <= 0 or expected != int(v10.get("input_v9_occurrence_count") or 0):
        raise ValueError("V10 handoff count mismatch")

    handoffs = [row for row in (v10.get("handoffs") or []) if isinstance(row, dict)]
    gates: Counter[str] = Counter()
    entries: list[dict[str, Any]] = []
    occurrence_keys: Counter[tuple[str, str, str]] = Counter()
    canonical_ids: Counter[str] = Counter()
    registry_keys: Counter[str] = Counter()
    sidecar_keys: Counter[str] = Counter()
    route_bundle_hashes: Counter[str] = Counter()

    for row in handoffs:
        raw_occurrence = row.get("occurrence_key_v2")
        if not isinstance(raw_occurrence, list) or len(raw_occurrence) != 3:
            gates["invalid_occurrence_key_count"] += 1
            continue
        occurrence = tuple(str(value or "").strip() for value in raw_occurrence)
        if not all(occurrence) or occurrence[2] == "identity_ambiguous":
            gates["invalid_occurrence_key_count"] += 1
            continue

        canonical_id = str(row.get("canonical_event_id") or "").strip()
        registry_key = str(row.get("registry_key") or "").strip()
        bundle_hash = str(row.get("route_bundle_sha256") or "").strip()
        reader_hash = str(row.get("reader_projection_sha256") or "").strip()
        if not canonical_id:
            gates["missing_canonical_event_id_count"] += 1
            continue
        if len(registry_key) != 64:
            gates["invalid_v9_registry_key_count"] += 1
            continue
        if len(bundle_hash) != 64:
            gates["invalid_route_bundle_hash_count"] += 1
            continue
        if len(reader_hash) != 64:
            gates["invalid_reader_projection_hash_count"] += 1
            continue
        if row.get("canonical_handoff_certified") is not True:
            gates["uncertified_v10_handoff_count"] += 1
            continue
        if row.get("publication_state") != "NONPUBLIC_EVIDENCE_ONLY":
            gates["invalid_publication_state_count"] += 1
            continue
        if row.get("canonical_map_state") != "LIST_ONLY":
            gates["non_list_only_map_state_count"] += 1
            continue
        if row.get("canonical_display_disposition") != "list_only":
            gates["non_list_only_display_disposition_count"] += 1
            continue
        if row.get("existing_point_authority") is not False:
            gates["existing_point_authority_count"] += 1
            continue
        if row.get("existing_area_authority") is not False:
            gates["existing_area_authority_count"] += 1
            continue
        if row.get("authority_precedence") != "ROUTE_EVIDENCE_REMAINS_NONPUBLIC_SIDECAR_ONLY":
            gates["invalid_authority_precedence_count"] += 1
            continue

        sidecar_key = _sha({
            "canonical_event_id": canonical_id,
            "occurrence_key_v2": list(occurrence),
            "v9_registry_key": registry_key,
            "route_bundle_sha256": bundle_hash,
            "reader_projection_sha256": reader_hash,
        })
        entry = {
            "sidecar_key": sidecar_key,
            "evidence_class": EVIDENCE_CLASS,
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "attachment_state": "REFERENCE_ONLY_NOT_ATTACHED_TO_CANONICAL",
            "canonical_event_id": canonical_id,
            "occurrence_key_v2": list(occurrence),
            "v9_registry_key": registry_key,
            "route_bundle_sha256": bundle_hash,
            "reader_projection_sha256": reader_hash,
            "canonical_map_state": "LIST_ONLY",
            "canonical_display_disposition": "list_only",
            "authority_precedence": "ROUTE_EVIDENCE_REMAINS_NONPUBLIC_SIDECAR_ONLY",
            "contains_geometry": False,
            "contains_coordinates": False,
            "publication_allowed": False,
            "exact_pin_eligible": False,
            "public_renderer_enabled": False,
            "projector_consumed": False,
            "canonical_write_allowed": False,
            "reader_write_allowed": False,
            "location_cache_write_allowed": False,
            "public_map_write_allowed": False,
        }
        entries.append(entry)
        occurrence_keys[occurrence] += 1
        canonical_ids[canonical_id] += 1
        registry_keys[registry_key] += 1
        sidecar_keys[sidecar_key] += 1
        route_bundle_hashes[bundle_hash] += 1

    gates["duplicate_occurrence_key_count"] = sum(1 for count in occurrence_keys.values() if count > 1)
    gates["duplicate_canonical_event_id_count"] = sum(1 for count in canonical_ids.values() if count > 1)
    gates["duplicate_v9_registry_key_count"] = sum(1 for count in registry_keys.values() if count > 1)
    gates["duplicate_sidecar_key_count"] = sum(1 for count in sidecar_keys.values() if count > 1)
    if len(handoffs) != expected:
        gates["v10_handoff_input_count_mismatch_count"] += abs(len(handoffs) - expected)
    if len(entries) != expected:
        gates["silent_sidecar_loss_count"] += max(expected - len(entries), 0)
        if len(entries) > expected:
            gates["unexpected_sidecar_gain_count"] += len(entries) - expected

    required = (
        "invalid_occurrence_key_count",
        "missing_canonical_event_id_count",
        "invalid_v9_registry_key_count",
        "invalid_route_bundle_hash_count",
        "invalid_reader_projection_hash_count",
        "uncertified_v10_handoff_count",
        "invalid_publication_state_count",
        "non_list_only_map_state_count",
        "non_list_only_display_disposition_count",
        "existing_point_authority_count",
        "existing_area_authority_count",
        "invalid_authority_precedence_count",
        "duplicate_occurrence_key_count",
        "duplicate_canonical_event_id_count",
        "duplicate_v9_registry_key_count",
        "duplicate_sidecar_key_count",
        "v10_handoff_input_count_mismatch_count",
        "silent_sidecar_loss_count",
        "unexpected_sidecar_gain_count",
    )
    hard_zero = {name: int(gates[name]) for name in required}
    hard_zero.update({
        "geometry_embedded_count": 0,
        "coordinate_embedded_count": 0,
        "canonical_write_count": 0,
        "reader_write_count": 0,
        "publication_count": 0,
        "exact_pin_candidate_count": 0,
        "public_renderer_count": 0,
        "projector_consumed_count": 0,
        "location_cache_write_count": 0,
        "public_map_write_count": 0,
    })
    conformant = all(value == 0 for value in hard_zero.values())

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "reference_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "canonical_modified": False,
        "reader_safe_modified": False,
        "location_cache_modified": False,
        "public_map_modified": False,
        "sidecar_conformance_pass": conformant,
        "input_v10_handoff_count": expected,
        "sidecar_entry_count": len(entries),
        "unique_occurrence_key_count": len(occurrence_keys),
        "unique_canonical_event_id_count": len(canonical_ids),
        "unique_v9_registry_key_count": len(registry_keys),
        "unique_sidecar_key_count": len(sidecar_keys),
        "unique_route_bundle_hash_count": len(route_bundle_hashes),
        "hard_zero_gates": hard_zero,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "sidecar": sorted(entries, key=lambda row: tuple(row["occurrence_key_v2"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v10-handoff", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(json.loads(args.v10_handoff.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version", "sidecar_conformance_pass", "input_v10_handoff_count",
        "sidecar_entry_count", "unique_occurrence_key_count", "unique_canonical_event_id_count",
        "unique_v9_registry_key_count", "unique_sidecar_key_count", "unique_route_bundle_hash_count",
        "hard_zero_gates", "release_status",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0 if result["sidecar_conformance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
