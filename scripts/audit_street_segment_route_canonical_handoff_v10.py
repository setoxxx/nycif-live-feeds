#!/usr/bin/env python3
"""Audit V9 route occurrences against canonical event records without mutation.

V10 proves that each NONPUBLIC V9 occurrence binds to exactly one canonical
occurrence using the repository occurrence_key_v2 contract. It classifies any
existing canonical location authority but never overrides it. A hypothetical
sidecar route-evidence reference is added only to an in-memory copy and must not
change the reader-visible projection fingerprint.

This audit does not modify canonical data, Projector output, reader-safe files,
location caches, map feeds, or publication state.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.occurrence_identity_contract import occurrence_key_v2
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows
    from occurrence_identity_contract import occurrence_key_v2

SCHEMA_VERSION = "NYCIF_STREET_SEGMENT_ROUTE_CANONICAL_HANDOFF_AUDIT_V10"
V9_SCHEMA = "NYCIF_STREET_SEGMENT_ROUTE_OCCURRENCE_REGISTRY_V9"
SIDECAR_FIELD = "nonpublic_route_evidence"

# Exact reader-safe fields consumed by build_maplibre_reader_safe_v03.py.
PUBLIC_TOP_LEVEL_FIELDS = (
    "id", "title", "category", "borough", "neighborhood", "location",
    "start_date_time", "end_date_time", "timezone", "significance",
    "public_url", "permalink", "link", "website", "url",
    "source_dataset", "source_event_id", "event_role", "parent_event_id",
    "latitude", "longitude", "location_evidence", "source",
)
PUBLIC_NYCIF_FIELDS = (
    "map_eligibility_state", "certified_pin", "location_authority",
    "display_disposition", "is_major", "photo_pick",
)


def _sha(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def reader_projection(event: dict[str, Any]) -> dict[str, Any]:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return {
        "top": {key: event.get(key) for key in PUBLIC_TOP_LEVEL_FIELDS},
        "nycif": {key: nycif.get(key) for key in PUBLIC_NYCIF_FIELDS},
    }


def _point_authority(event: dict[str, Any]) -> bool:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    evidence = event.get("location_evidence") if isinstance(event.get("location_evidence"), dict) else {}
    return (
        nycif.get("map_eligibility_state") == "MAP_READY"
        and nycif.get("certified_pin") is True
        and str(nycif.get("location_authority") or "").strip() != ""
        and evidence.get("exact_pin_eligible") is True
        and str(evidence.get("validation_state") or "").lower() == "validated"
    )


def _area_authority(event: dict[str, Any]) -> bool:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    geometry = event.get("geometry")
    evidence = event.get("location_evidence") if isinstance(event.get("location_evidence"), dict) else {}
    geometry_type = ""
    if isinstance(geometry, dict):
        geometry_type = str(geometry.get("type") or "")
    elif isinstance(evidence.get("geometry"), dict):
        geometry_type = str(evidence["geometry"].get("type") or "")
    return geometry_type in {"Polygon", "MultiPolygon"} or str(nycif.get("geometry_role") or "") == "event_site_area_evidence"


def audit(v9: dict[str, Any], canonical_payload: Any) -> dict[str, Any]:
    if v9.get("schema_version") != V9_SCHEMA:
        raise ValueError("unexpected V9 schema")
    if v9.get("registry_conformance_pass") is not True:
        raise ValueError("V9 registry is not conformant")
    if v9.get("release_status") != "NONPUBLIC_EVIDENCE_ONLY":
        raise ValueError("V9 release boundary is not non-public")
    for key in ("publication_authority_granted", "public_renderer_enabled", "projector_consumed", "promotion_allowed"):
        if v9.get(key) is not False:
            raise ValueError(f"V9 safety boundary violated: {key}")

    canonical = extract_rows(canonical_payload)
    by_occurrence: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    canonical_ambiguous = 0
    for event in canonical:
        if not isinstance(event, dict):
            continue
        key = occurrence_key_v2(event)
        if key[2] == "identity_ambiguous":
            canonical_ambiguous += 1
            continue
        by_occurrence[key].append(event)

    gates: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    existing_point_authority_count = 0
    existing_area_authority_count = 0
    no_existing_exact_geometry_authority_count = 0

    registry = [row for row in (v9.get("registry") or []) if isinstance(row, dict)]
    seen_registry_keys: Counter[tuple[str, str, str]] = Counter()

    for entry in registry:
        raw_key = entry.get("occurrence_key_v2")
        if not isinstance(raw_key, list) or len(raw_key) != 3:
            gates["invalid_v9_occurrence_key_count"] += 1
            continue
        key = tuple(str(value or "").strip() for value in raw_key)
        if not all(key) or key[2] == "identity_ambiguous":
            gates["invalid_v9_occurrence_key_count"] += 1
            continue
        seen_registry_keys[key] += 1
        matches = by_occurrence.get(key, [])
        if len(matches) == 0:
            gates["canonical_occurrence_missing_count"] += 1
            continue
        if len(matches) != 1:
            gates["canonical_occurrence_not_unique_count"] += 1
            continue

        event = matches[0]
        before = reader_projection(event)
        augmented = copy.deepcopy(event)
        nycif = augmented.get("nycif") if isinstance(augmented.get("nycif"), dict) else {}
        nycif = dict(nycif)
        nycif[SIDECAR_FIELD] = {
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "registry_key": entry.get("registry_key"),
            "route_bundle_sha256": entry.get("route_bundle_sha256"),
        }
        augmented["nycif"] = nycif
        after = reader_projection(augmented)
        if before != after or _sha(before) != _sha(after):
            gates["reader_projection_changed_by_sidecar_count"] += 1
            continue

        original_nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        state = str(original_nycif.get("map_eligibility_state") or "UNSPECIFIED")
        disposition = str(original_nycif.get("display_disposition") or "UNSPECIFIED")
        state_counts[state] += 1
        disposition_counts[disposition] += 1

        point = _point_authority(event)
        area = _area_authority(event)
        if point:
            existing_point_authority_count += 1
            precedence = "EXISTING_POINT_AUTHORITY_WINS"
        elif area:
            existing_area_authority_count += 1
            precedence = "EXISTING_AREA_AUTHORITY_WINS"
        else:
            no_existing_exact_geometry_authority_count += 1
            precedence = "ROUTE_EVIDENCE_REMAINS_NONPUBLIC_SIDECAR_ONLY"

        rows.append({
            "occurrence_key_v2": list(key),
            "registry_key": entry.get("registry_key"),
            "route_bundle_sha256": entry.get("route_bundle_sha256"),
            "canonical_event_id": event.get("id"),
            "canonical_map_state": state,
            "canonical_display_disposition": disposition,
            "existing_point_authority": point,
            "existing_area_authority": area,
            "authority_precedence": precedence,
            "reader_projection_sha256": _sha(before),
            "canonical_handoff_certified": True,
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
        })

    gates["duplicate_v9_occurrence_key_count"] = sum(1 for count in seen_registry_keys.values() if count > 1)
    expected = int(v9.get("registry_occurrence_count") or 0)
    if len(registry) != expected:
        gates["v9_registry_count_mismatch_count"] += abs(len(registry) - expected)
    if len(rows) != expected:
        gates["silent_canonical_handoff_loss_count"] += max(expected - len(rows), 0)
        if len(rows) > expected:
            gates["unexpected_canonical_handoff_gain_count"] += len(rows) - expected

    required = (
        "invalid_v9_occurrence_key_count",
        "duplicate_v9_occurrence_key_count",
        "v9_registry_count_mismatch_count",
        "canonical_occurrence_missing_count",
        "canonical_occurrence_not_unique_count",
        "reader_projection_changed_by_sidecar_count",
        "silent_canonical_handoff_loss_count",
        "unexpected_canonical_handoff_gain_count",
    )
    hard_zero = {name: int(gates[name]) for name in required}
    hard_zero.update({
        "publication_count": 0,
        "exact_pin_candidate_count": 0,
        "public_renderer_count": 0,
        "projector_consumed_count": 0,
        "location_cache_write_count": 0,
        "public_map_write_count": 0,
        "canonical_write_count": 0,
    })
    conformant = all(value == 0 for value in hard_zero.values())

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "canonical_modified": False,
        "reader_safe_modified": False,
        "handoff_conformance_pass": conformant,
        "input_v9_occurrence_count": expected,
        "canonical_event_count": len(canonical),
        "canonical_ambiguous_occurrence_count_total": canonical_ambiguous,
        "canonical_handoff_certified_count": len(rows),
        "existing_point_authority_count": existing_point_authority_count,
        "existing_area_authority_count": existing_area_authority_count,
        "no_existing_exact_geometry_authority_count": no_existing_exact_geometry_authority_count,
        "canonical_map_state_counts": dict(sorted(state_counts.items())),
        "canonical_display_disposition_counts": dict(sorted(disposition_counts.items())),
        "hard_zero_gates": hard_zero,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "handoffs": sorted(rows, key=lambda row: tuple(row["occurrence_key_v2"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v9-registry", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        json.loads(args.v9_registry.read_text(encoding="utf-8")),
        json.loads(args.canonical.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    keys = (
        "schema_version", "handoff_conformance_pass", "input_v9_occurrence_count",
        "canonical_handoff_certified_count", "existing_point_authority_count",
        "existing_area_authority_count", "no_existing_exact_geometry_authority_count",
        "canonical_map_state_counts", "canonical_display_disposition_counts",
        "hard_zero_gates", "release_status",
    )
    print(json.dumps({key: result[key] for key in keys}, indent=2, sort_keys=True))
    return 0 if result["handoff_conformance_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
