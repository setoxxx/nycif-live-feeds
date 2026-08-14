#!/usr/bin/env python3
"""Audit V7 Parks/CEMS area registry against the exact-area evidence contract."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "NYCIF_PARKS_CEMS_AREA_EVIDENCE_REGISTRY_V7"
CONTRACT_TYPE = "nycif_exact_event_area_evidence_contract_v1"


def geometry_sha256(geometry: Any) -> str:
    return hashlib.sha256(
        json.dumps(geometry, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def audit(contract: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    if contract.get("artifact_type") != CONTRACT_TYPE:
        raise RuntimeError("unexpected exact-area evidence contract")
    if registry.get("schema_version") != REGISTRY_SCHEMA:
        raise RuntimeError("unexpected V7 registry schema")

    required_fields = list(contract.get("required_registry_entry_fields") or [])
    required_flags = list(contract.get("required_event_site_agreement_flags") or [])
    allowed_geometry = set(contract.get("allowed_geometry_types") or [])
    entries = [item for item in registry.get("entries", []) if isinstance(item, dict)]

    invalid: list[dict[str, Any]] = []
    hash_mismatch_count = 0
    systems: list[str] = []
    cemsids: list[str] = []

    for entry in entries:
        reasons: list[str] = []
        missing = [field for field in required_fields if field not in entry]
        if missing:
            reasons.append("MISSING_REQUIRED_FIELDS:" + ",".join(sorted(missing)))

        system = str(entry.get("official_system_id") or "").strip()
        cemsid = str(entry.get("source_cemsid") or "").strip()
        if system:
            systems.append(system)
        else:
            reasons.append("OFFICIAL_SYSTEM_ID_EMPTY")
        if cemsid:
            cemsids.append(cemsid)
        else:
            reasons.append("SOURCE_CEMSID_EMPTY")

        if entry.get("evidence_class") != "OFFICIAL_PARKS_FACILITY_AREA":
            reasons.append("EVIDENCE_CLASS_INVALID")
        if entry.get("publication_state") != "NONPUBLIC_EVIDENCE_ONLY":
            reasons.append("PUBLICATION_STATE_INVALID")
        if entry.get("official_featurestatus") != "Active":
            reasons.append("FEATURESTATUS_NOT_ACTIVE")
        if entry.get("geometry_type") not in allowed_geometry:
            reasons.append("GEOMETRY_TYPE_NOT_ALLOWED")
        if entry.get("geometry_source_field") != "multipolygon":
            reasons.append("GEOMETRY_SOURCE_FIELD_INVALID")
        if not entry.get("matched_permit_fields"):
            reasons.append("PERMIT_EVIDENCE_MISSING")

        agreement = entry.get("event_site_agreement")
        if not isinstance(agreement, dict):
            reasons.append("EVENT_SITE_AGREEMENT_MISSING")
        else:
            for flag in required_flags:
                if agreement.get(flag) is not True:
                    reasons.append("AGREEMENT_FLAG_FALSE:" + flag)

        actual_hash = geometry_sha256(entry.get("geometry"))
        if actual_hash != entry.get("geometry_sha256"):
            hash_mismatch_count += 1
            reasons.append("GEOMETRY_HASH_MISMATCH")

        if entry.get("point_generated") is not False:
            reasons.append("POINT_GENERATED_NOT_FALSE")
        if entry.get("centroid_generated") is not False:
            reasons.append("CENTROID_GENERATED_NOT_FALSE")
        if entry.get("publication_eligible") is not False:
            reasons.append("PUBLICATION_ELIGIBLE_NOT_FALSE")
        if entry.get("exact_pin_eligible") is not False:
            reasons.append("EXACT_PIN_ELIGIBLE_NOT_FALSE")

        if reasons:
            invalid.append({"registry_key": entry.get("registry_key"), "reasons": reasons})

    duplicate_system_count = sum(count > 1 for count in Counter(systems).values())
    duplicate_cemsid_count = sum(count > 1 for count in Counter(cemsids).values())

    gates = contract.get("contract_audit_gates") if isinstance(contract.get("contract_audit_gates"), dict) else {}
    gate_results = {
        "invalid_registry_entry_count": len(invalid),
        "duplicate_registry_system_count": duplicate_system_count,
        "duplicate_registry_source_cemsid_count": duplicate_cemsid_count,
        "geometry_hash_mismatch_count": hash_mismatch_count,
        "point_generated_count": int(registry.get("point_generated_count") or 0),
        "centroid_generated_count": int(registry.get("centroid_generated_count") or 0),
        "publication_eligible_count": int(registry.get("publication_eligible_count") or 0),
        "exact_pin_candidate_count": int(registry.get("exact_pin_candidate_count") or 0),
        "projector_consumed": registry.get("projector_consumed"),
    }

    passed = (
        gate_results["invalid_registry_entry_count"] == int(gates.get("invalid_registry_entry_count_required", 0))
        and gate_results["duplicate_registry_system_count"] == int(gates.get("duplicate_registry_system_count_required", 0))
        and gate_results["duplicate_registry_source_cemsid_count"] == int(gates.get("duplicate_registry_source_cemsid_count_required", 0))
        and gate_results["geometry_hash_mismatch_count"] == int(gates.get("geometry_hash_mismatch_count_required", 0))
        and gate_results["point_generated_count"] == int(gates.get("point_generated_count_required", 0))
        and gate_results["centroid_generated_count"] == int(gates.get("centroid_generated_count_required", 0))
        and gate_results["publication_eligible_count"] == int(gates.get("publication_eligible_count_required", 0))
        and gate_results["exact_pin_candidate_count"] == int(gates.get("exact_pin_candidate_count_required", 0))
        and gate_results["projector_consumed"] is bool(gates.get("projector_consumed_required", False))
        and gate_results["projector_consumed"] == gates.get("projector_consumed_required", False)
    )

    return {
        "schema_version": "NYCIF_EXACT_EVENT_AREA_EVIDENCE_AUDIT_V1",
        "contract_artifact_type": contract.get("artifact_type"),
        "registry_schema_version": registry.get("schema_version"),
        "registry_entry_count": len(entries),
        "registry_occurrence_coverage": int(registry.get("registry_occurrence_coverage") or 0),
        "blocked_candidate_count": int(registry.get("blocked_candidate_count") or 0),
        "gate_results": gate_results,
        "invalid_entries": invalid,
        "pass": passed,
        "publication_authority_granted": False,
        "projector_consumption_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    report = audit(contract, registry)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "pass": report["pass"],
        "registry_entry_count": report["registry_entry_count"],
        "registry_occurrence_coverage": report["registry_occurrence_coverage"],
        "blocked_candidate_count": report["blocked_candidate_count"],
        **report["gate_results"],
    }, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
