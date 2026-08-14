#!/usr/bin/env python3
"""Build a read-only one-to-one Parks/CEMS facility-area evidence registry.

V6 establishes strict candidate claims but deliberately does not publish them.
V7 further requires one source claim <-> one source CEMSID <-> one official
Athletic Facilities SYSTEM row before preserving the official MultiPolygon in a
separate evidence registry.

The registry is explicitly non-public. It is not consumed by the projector and
never derives a point or centroid from an official area geometry.
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
    from scripts.probe_parks_cems_athletic_facilities_v2 import (
        DATASET_ID as ATHLETIC_DATASET_ID,
        fetch_facilities,
        official_descriptor,
    )
    from scripts.probe_parks_cems_facility_area_v3 import PARK_PROPERTIES_DATASET_ID, _first
    from scripts.probe_parks_cems_permit_flag_v5 import permitted_for_sport
    from scripts.probe_parks_cems_strict_facility_area_v6 import (
        feature_status,
        geometry_from_row,
        official_field_id,
    )
except ModuleNotFoundError:  # pragma: no cover
    from probe_parks_cems_athletic_facilities_v2 import (
        DATASET_ID as ATHLETIC_DATASET_ID,
        fetch_facilities,
        official_descriptor,
    )
    from probe_parks_cems_facility_area_v3 import PARK_PROPERTIES_DATASET_ID, _first
    from probe_parks_cems_permit_flag_v5 import permitted_for_sport
    from probe_parks_cems_strict_facility_area_v6 import (
        feature_status,
        geometry_from_row,
        official_field_id,
    )

V6_SCHEMA = "NYCIF_PARKS_CEMS_STRICT_FACILITY_AREA_PROBE_V6"
V7_SCHEMA = "NYCIF_PARKS_CEMS_AREA_EVIDENCE_REGISTRY_V7"
TVPP_DATASET_ID = "tvpp-9vvx"


def canonical_geometry_sha256(geometry: Any) -> str:
    payload = json.dumps(
        geometry,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _candidate_system(candidate: dict[str, Any]) -> str:
    evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    return str(evidence.get("official_system_id") or "").strip()


def build_registry(
    v6_report: dict[str, Any],
    facilities: list[dict[str, Any]],
) -> dict[str, Any]:
    if v6_report.get("schema_version") != V6_SCHEMA:
        raise RuntimeError("V7 requires a V6 strict facility-area report")
    if v6_report.get("publication_eligible_count") != 0:
        raise RuntimeError("V6 publication eligibility must remain zero")
    if v6_report.get("exact_pin_candidate_count") != 0:
        raise RuntimeError("V6 exact-pin candidate count must remain zero")

    candidates = [
        item for item in v6_report.get("candidates", []) if isinstance(item, dict)
    ]

    candidate_by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    candidate_by_cemsid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        system = _candidate_system(candidate)
        if system:
            candidate_by_system[system].append(candidate)
        for cemsid in candidate.get("source_cemsids") or []:
            value = str(cemsid).strip()
            if value:
                candidate_by_cemsid[value].append(candidate)

    official_by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in facilities:
        if not isinstance(row, dict):
            continue
        _, _, system, _ = official_descriptor(row)
        if system:
            official_by_system[system].append(row)

    entries: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    block_reason_counts: Counter[str] = Counter()

    for candidate in candidates:
        evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
        system = str(evidence.get("official_system_id") or "").strip()
        cemsids = [str(value).strip() for value in candidate.get("source_cemsids") or [] if str(value).strip()]
        reasons: list[str] = []

        if not system:
            reasons.append("OFFICIAL_SYSTEM_ID_MISSING")
        elif len(candidate_by_system.get(system, [])) != 1:
            reasons.append("SYSTEM_SHARED_ACROSS_SOURCE_CLAIMS")

        if len(cemsids) != 1:
            reasons.append("SOURCE_CEMSID_NOT_SINGLE")
        elif len(candidate_by_cemsid.get(cemsids[0], [])) != 1:
            reasons.append("SOURCE_CEMSID_SHARED_ACROSS_STRICT_CANDIDATES")

        official_rows = official_by_system.get(system, []) if system else []
        if len(official_rows) != 1:
            reasons.append("OFFICIAL_SYSTEM_NOT_UNIQUE")

        row = official_rows[0] if len(official_rows) == 1 else None
        geometry = None
        matched_permit_fields: list[str] = []
        if row is not None:
            _, _, row_system, row_gispropnum = official_descriptor(row)
            expected_gispropnum = str(evidence.get("official_gispropnum") or "").strip()
            expected_field_id = str(candidate.get("parsed_field_id") or "").strip()
            sport = str(candidate.get("parsed_sport") or "").strip()

            if row_system != system:
                reasons.append("OFFICIAL_SYSTEM_REVALIDATION_MISMATCH")
            if not expected_gispropnum or row_gispropnum != expected_gispropnum:
                reasons.append("OFFICIAL_GISPROPNUM_REVALIDATION_MISMATCH")
            if not expected_field_id or official_field_id(row) != expected_field_id:
                reasons.append("OFFICIAL_FIELD_ID_REVALIDATION_MISMATCH")

            status = feature_status(row)
            if not status:
                reasons.append("OFFICIAL_FEATURESTATUS_MISSING")
            elif status != "active":
                reasons.append("OFFICIAL_FEATURESTATUS_NOT_ACTIVE")

            permitted, matched_permit_fields = permitted_for_sport(row, sport)
            if not permitted:
                reasons.append("OFFICIAL_SPORT_PERMIT_REVALIDATION_FAILED")

            geometry = geometry_from_row(row)
            geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
            if geometry_type != "MultiPolygon":
                reasons.append("OFFICIAL_MULTIPOLYGON_REVALIDATION_FAILED")

        if reasons:
            for reason in sorted(set(reasons)):
                block_reason_counts[reason] += 1
            blocked.append(
                {
                    "claim_key": candidate.get("claim_key"),
                    "borough_code": candidate.get("borough_code"),
                    "park_name": candidate.get("park_name"),
                    "facility_descriptor": candidate.get("facility_descriptor"),
                    "parsed_sport": candidate.get("parsed_sport"),
                    "parsed_field_id": candidate.get("parsed_field_id"),
                    "occurrence_count": int(candidate.get("occurrence_count") or 0),
                    "source_cemsids": cemsids,
                    "official_system_id": system or None,
                    "block_reasons": sorted(set(reasons)),
                }
            )
            continue

        assert row is not None
        assert isinstance(geometry, dict)
        cemsid = cemsids[0]
        geometry_sha256 = canonical_geometry_sha256(geometry)
        _, _, _, row_gispropnum = official_descriptor(row)
        entry = {
            "registry_key": f"parks-cems-area:{cemsid}:{system}",
            "evidence_class": "OFFICIAL_PARKS_FACILITY_AREA",
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "claim_key": candidate.get("claim_key"),
            "borough_code": candidate.get("borough_code"),
            "park_name": candidate.get("park_name"),
            "facility_descriptor": candidate.get("facility_descriptor"),
            "parsed_sport": candidate.get("parsed_sport"),
            "parsed_field_id": candidate.get("parsed_field_id"),
            "occurrence_count": int(candidate.get("occurrence_count") or 0),
            "source_event_ids_sample": list(candidate.get("source_event_ids") or []),
            "source_cemsid": cemsid,
            "official_system_id": system,
            "official_gispropnum": row_gispropnum,
            "official_field_number_raw": _first(
                row, "field_number", "fieldnumber", "field_no", "fieldnum"
            ) or None,
            "official_primary_sport_code": _first(
                row, "primary_sport", "primarysport", "sport"
            ) or None,
            "official_featurestatus": _first(
                row, "featurestatus", "feature_status", "status"
            ) or None,
            "matched_permit_fields": sorted(matched_permit_fields),
            "geometry_type": "MultiPolygon",
            "geometry_source_field": "multipolygon",
            "geometry_sha256": geometry_sha256,
            "geometry": geometry,
            "event_site_agreement": {
                "property_name_and_borough_unique": True,
                "sport_field_pair_strict": True,
                "field_identifier_exact": True,
                "sport_permit_explicit": True,
                "source_cemsid_singleton": True,
                "official_system_one_to_one": True,
                "featurestatus_active": True,
            },
            "point_generated": False,
            "centroid_generated": False,
            "publication_eligible": False,
            "exact_pin_eligible": False,
        }
        entries.append(entry)

    entries.sort(key=lambda item: item["registry_key"])
    blocked.sort(
        key=lambda item: (
            str(item.get("official_system_id") or ""),
            str(item.get("claim_key") or ""),
        )
    )

    systems = [entry["official_system_id"] for entry in entries]
    cemsids = [entry["source_cemsid"] for entry in entries]
    geometry_hashes = [entry["geometry_sha256"] for entry in entries]
    duplicate_system_count = sum(count > 1 for count in Counter(systems).values())
    duplicate_cemsid_count = sum(count > 1 for count in Counter(cemsids).values())
    shared_geometry_hash_group_count = sum(count > 1 for count in Counter(geometry_hashes).values())

    registry_payload_for_digest = [
        {
            "registry_key": entry["registry_key"],
            "geometry_sha256": entry["geometry_sha256"],
            "occurrence_count": entry["occurrence_count"],
        }
        for entry in entries
    ]
    registry_sha256 = hashlib.sha256(
        json.dumps(
            registry_payload_for_digest,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": V7_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_datasets": {
            "tvpp": TVPP_DATASET_ID,
            "parks_properties": PARK_PROPERTIES_DATASET_ID,
            "parks_athletic_facilities": ATHLETIC_DATASET_ID,
        },
        "input_v6_schema_version": v6_report.get("schema_version"),
        "input_v6_candidate_count": len(candidates),
        "input_v6_occurrence_coverage": int(v6_report.get("strict_occurrence_coverage") or 0),
        "registry_entry_count": len(entries),
        "registry_occurrence_coverage": sum(entry["occurrence_count"] for entry in entries),
        "registry_unique_system_count": len(set(systems)),
        "registry_unique_source_cemsid_count": len(set(cemsids)),
        "registry_multipolygon_count": sum(entry["geometry_type"] == "MultiPolygon" for entry in entries),
        "duplicate_registry_system_count": duplicate_system_count,
        "duplicate_registry_source_cemsid_count": duplicate_cemsid_count,
        "shared_geometry_hash_group_count": shared_geometry_hash_group_count,
        "blocked_candidate_count": len(blocked),
        "blocked_occurrence_coverage": sum(int(item.get("occurrence_count") or 0) for item in blocked),
        "block_reason_counts": dict(sorted(block_reason_counts.items())),
        "registry_sha256": registry_sha256,
        "read_only": True,
        "promotion_allowed": False,
        "publication_eligible_count": 0,
        "exact_pin_candidate_count": 0,
        "point_generated_count": 0,
        "centroid_generated_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "projector_consumed": False,
        "entries": entries,
        "blocked": blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v6-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.v6_report.open("r", encoding="utf-8") as handle:
        v6_report = json.load(handle)
    if not isinstance(v6_report, dict):
        raise RuntimeError("V6 report must be a JSON object")

    facilities = fetch_facilities()
    report = build_registry(v6_report, facilities)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "input_v6_candidate_count": report["input_v6_candidate_count"],
                "registry_entry_count": report["registry_entry_count"],
                "registry_occurrence_coverage": report["registry_occurrence_coverage"],
                "registry_unique_system_count": report["registry_unique_system_count"],
                "registry_unique_source_cemsid_count": report["registry_unique_source_cemsid_count"],
                "duplicate_registry_system_count": report["duplicate_registry_system_count"],
                "duplicate_registry_source_cemsid_count": report["duplicate_registry_source_cemsid_count"],
                "blocked_candidate_count": report["blocked_candidate_count"],
                "blocked_occurrence_coverage": report["blocked_occurrence_coverage"],
                "block_reason_counts": report["block_reason_counts"],
                "publication_eligible_count": report["publication_eligible_count"],
                "exact_pin_candidate_count": report["exact_pin_candidate_count"],
                "point_generated_count": report["point_generated_count"],
                "centroid_generated_count": report["centroid_generated_count"],
                "projector_consumed": report["projector_consumed"],
                "registry_sha256": report["registry_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
