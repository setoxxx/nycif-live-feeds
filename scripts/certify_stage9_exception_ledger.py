#!/usr/bin/env python3
"""Certify the complete, same-snapshot exception ledger for Sprint 2.1.5.

This audit does not promote records or invent data. It proves that every current
exception class is either empty, safely excluded, or represented by a complete
reason-coded queue generated from the same discovery projection.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = DATA / "reports"
OUT = REPORTS / "stage9_exception_ledger.json"
CERT = REPORTS / "stage9_exception_ledger_certificate.json"

PATHS = {
    "reconciliation": DATA / "events_discovery_reconciliation_v02.json",
    "taxonomy": DATA / "events_discovery_taxonomy_v02_audit.json",
    "validation": DATA / "events_discovery_schema_validation_v02.json",
    "invalid": DATA / "events_discovery_invalid_records_v02.json",
    "low_confidence": DATA / "events_discovery_low_confidence_v02.json",
    "missing_coordinates": DATA / "events_discovery_missing_coordinates_v02.json",
    "possible_duplicates": DATA / "events_discovery_possible_duplicates_v02.json",
    "legacy_quarantine": DATA / "events_discovery_legacy_major_quarantine_v02.json",
    "approved": DATA / "events_discovery_v02_approved.json",
    "review": DATA / "events_discovery_v02_review.json",
    "stage8_inventory": REPORTS / "stage8_list_only_coordinate_inventory.json",
    "stage8_certificate": REPORTS / "stage8_supported_coordinate_resolution_certificate.json",
    "approved_dedupe": REPORTS / "discovery_approved_dedupe_report.json",
    "shared_cems_dedupe": REPORTS / "discovery_shared_cems_occurrence_dedupe_report.json",
    "daily_health": ROOT / "status" / "nycif-daily-data-health.json",
}

CANONICAL_BOROUGHS = {"Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"}
PRIVATE_KEYS = {
    "internal_notes",
    "editorial_notes",
    "private_notes",
    "reviewer_notes",
    "operator_notes",
    "raw_payload",
    "debug",
    "debug_notes",
}


def load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "records", "features"):
            value = payload.get(key)
            if isinstance(value, list):
                if key == "features":
                    out = []
                    for feature in value:
                        if not isinstance(feature, dict):
                            continue
                        props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
                        merged = dict(props)
                        merged.setdefault("geometry", feature.get("geometry"))
                        out.append(merged)
                    return out
                return [row for row in value if isinstance(row, dict)]
    return []


def generated_at(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("generated_at_utc") or payload.get("generated_at") or "")


def item_count(payload: Any, key: str = "items") -> int:
    if not isinstance(payload, dict):
        return 0
    value = payload.get(key)
    return len(value) if isinstance(value, list) else 0


def as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def coords(row: dict[str, Any]) -> tuple[float | None, float | None]:
    return as_float(row.get("latitude", row.get("lat"))), as_float(row.get("longitude", row.get("lng")))


def valid_nyc(lat: float | None, lng: float | None) -> bool:
    return lat is not None and lng is not None and 40.45 <= lat <= 40.95 and -74.30 <= lng <= -73.65


def nycif(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("nycif") if isinstance(row.get("nycif"), dict) else {}


def source(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def canonical_id(row: dict[str, Any]) -> str:
    return str(row.get("canonical_id") or row.get("id") or "").strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def null_borough_reason(row: dict[str, Any]) -> str:
    text = " ".join(
        norm(row.get(key))
        for key in ("title", "description", "location", "address", "venue")
    )
    lat, lng = coords(row)
    if any(token in text for token in ("online event", "virtual event", "zoom", "webinar", "livestream", "live stream")):
        return "online_no_single_borough_required"
    if any(token in text for token in ("citywide", "multiple locations", "various locations", "multiple parks")):
        return "citywide_or_multi_location_no_single_borough"
    if valid_nyc(lat, lng):
        return "borough_normalization_pending_with_valid_nyc_coordinates"
    if nycif(row).get("coordinate_status") == "list_only":
        return "list_only_location_reason_coded_separately"
    if not str(row.get("location") or row.get("address") or "").strip():
        return "missing_location_text"
    return "physical_location_borough_unresolved"


def reason_present(item: dict[str, Any]) -> bool:
    return bool(
        item.get("reason_code")
        or item.get("reason_for_review")
        or item.get("reason")
        or item.get("disposition")
        or item.get("recommended_action")
    )


def count_private_keys(value: Any) -> Counter[str]:
    found: Counter[str] = Counter()
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in PRIVATE_KEYS and child not in (None, "", [], {}):
                found[str(key).lower()] += 1
            found.update(count_private_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(count_private_keys(child))
    return found


def stage8_remaining_reason_map(payload: Any) -> dict[str, str]:
    ledger = payload.get("ledger") if isinstance(payload, dict) else []
    out: dict[str, str] = {}
    for item in ledger if isinstance(ledger, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("reason_code") == "supported_coordinate_proposal":
            continue
        cid = canonical_id(item)
        reason = str(item.get("reason_code") or "").strip()
        if cid and reason:
            out[cid] = reason
    return out


def main() -> int:
    payloads = {name: load(path) for name, path in PATHS.items()}
    recon = payloads["reconciliation"]
    taxonomy = payloads["taxonomy"]
    validation = payloads["validation"]
    invalid = payloads["invalid"]
    low = payloads["low_confidence"]
    missing = payloads["missing_coordinates"]
    dupes = payloads["possible_duplicates"]
    legacy = payloads["legacy_quarantine"]
    stage8 = payloads["stage8_inventory"]
    stage8_cert = payloads["stage8_certificate"]
    health = payloads["daily_health"]

    approved_rows = rows(payloads["approved"])
    review_rows = rows(payloads["review"])
    visible_rows = approved_rows + review_rows

    core_generation = generated_at(recon)
    core_generated_values = {
        name: generated_at(payloads[name])
        for name in ("reconciliation", "taxonomy", "invalid", "low_confidence", "missing_coordinates", "possible_duplicates")
    }

    invalid_items = invalid.get("items") if isinstance(invalid, dict) else []
    low_items = low.get("items") if isinstance(low, dict) else []
    missing_items = missing.get("items") if isinstance(missing, dict) else []
    duplicate_groups = dupes.get("groups") if isinstance(dupes, dict) else []
    invalid_items = invalid_items if isinstance(invalid_items, list) else []
    low_items = low_items if isinstance(low_items, list) else []
    missing_items = missing_items if isinstance(missing_items, list) else []
    duplicate_groups = duplicate_groups if isinstance(duplicate_groups, list) else []

    duplicate_candidate_ids = {
        str(cid)
        for group in duplicate_groups
        if isinstance(group, dict)
        for cid in (group.get("ids") if isinstance(group.get("ids"), list) else [])
        if cid
    }
    duplicate_candidate_record_count = sum(int(group.get("count") or 0) for group in duplicate_groups if isinstance(group, dict))

    stage8_reasons = stage8_remaining_reason_map(stage8)
    missing_ids = {canonical_id(item) for item in missing_items if isinstance(item, dict) and canonical_id(item)}
    missing_without_stage8_reason = sorted(missing_ids - set(stage8_reasons))
    stale_stage8_reason_ids = sorted(set(stage8_reasons) - missing_ids)

    null_borough_rows = [row for row in visible_rows if str(row.get("borough") or "").strip() not in CANONICAL_BOROUGHS]
    null_borough_reasons = Counter(null_borough_reason(row) for row in null_borough_rows)
    null_borough_ledger = [
        {
            "canonical_id": canonical_id(row),
            "source_dataset": source(row).get("dataset"),
            "source_event_id": source(row).get("source_event_id"),
            "title": row.get("title"),
            "date": nycif(row).get("event_date") or str(row.get("start_date_time") or "")[:10],
            "location": row.get("location") or row.get("address"),
            "coordinate_status": nycif(row).get("coordinate_status"),
            "reason_code": null_borough_reason(row),
        }
        for row in null_borough_rows
    ]

    public_private_keys = count_private_keys(payloads["approved"])

    lifecycle_counts: Counter[str] = Counter()
    for row in visible_rows:
        status = norm(row.get("status") or row.get("event_status") or nycif(row).get("lifecycle_status")) or "unspecified"
        lifecycle_counts[status] += 1

    exception_classes = {
        "schema_invalid": {
            "count": int(invalid.get("count") or 0),
            "queue_count": len(invalid_items),
            "disposition": "empty_pass" if not invalid_items else "reason_coded_queue",
            "complete": len(invalid_items) == int(invalid.get("count") or 0),
            "all_reason_coded": all(reason_present(item) for item in invalid_items if isinstance(item, dict)),
        },
        "low_classification_confidence": {
            "count": int(low.get("count") or 0),
            "queue_count": len(low_items),
            "disposition": "manual_category_review",
            "complete": len(low_items) == int(low.get("count") or 0),
            "all_reason_coded": all(reason_present(item) for item in low_items if isinstance(item, dict)),
        },
        "list_only_coordinates": {
            "count": int(missing.get("count") or 0),
            "queue_count": len(missing_items),
            "stage8_reason_count": len(stage8_reasons),
            "disposition": "retained_list_only_with_stage8_reason",
            "complete": len(missing_items) == int(missing.get("count") or 0),
            "all_reason_coded": not missing_without_stage8_reason and not stale_stage8_reason_ids,
        },
        "possible_duplicates": {
            "group_count": int(dupes.get("count") or 0),
            "queue_group_count": len(duplicate_groups),
            "candidate_record_count": int(dupes.get("candidate_record_count") or duplicate_candidate_record_count),
            "unique_candidate_ids_listed": len(duplicate_candidate_ids),
            "truncated": bool(dupes.get("truncated", True)),
            "disposition": "manual_duplicate_review_no_auto_merge",
            "complete": len(duplicate_groups) == int(dupes.get("count") or 0) and dupes.get("truncated") is False,
            "all_reason_coded": all(reason_present(item) for item in duplicate_groups if isinstance(item, dict)),
        },
        "legacy_major_quarantine": {
            "count": int((legacy.get("summary") or {}).get("quarantined") or 0) if isinstance(legacy, dict) else 0,
            "queue_count": item_count(legacy),
            "disposition": "quarantine_from_major_feed",
            "complete": item_count(legacy) == int((legacy.get("summary") or {}).get("quarantined") or 0) if isinstance(legacy, dict) else True,
            "all_reason_coded": all(reason_present(item) for item in (legacy.get("items") or []) if isinstance(item, dict)) if isinstance(legacy, dict) else True,
        },
        "null_or_noncanonical_borough": {
            "count": len(null_borough_rows),
            "reason_counts": dict(sorted(null_borough_reasons.items())),
            "disposition": "reason_coded_location_exception",
            "complete": len(null_borough_ledger) == len(null_borough_rows),
            "all_reason_coded": all(item.get("reason_code") for item in null_borough_ledger),
        },
        "private_or_reserved": {
            "count": int((taxonomy.get("event_role_counts") or {}).get("private_or_reserved_activity") or 0),
            "disposition": "private_or_reserved_activity_not_normal_public_marker",
            "complete": True,
            "all_reason_coded": True,
        },
        "maintenance_or_closure": {
            "count": int((taxonomy.get("event_role_counts") or {}).get("maintenance_or_closure") or 0),
            "disposition": "maintenance_or_closure_separate_display_role",
            "complete": True,
            "all_reason_coded": True,
        },
        "general_or_fallback_category": {
            "count": int((taxonomy.get("interest_counts") or {}).get("general") or 0),
            "low_confidence_count": int(low.get("count") or 0),
            "disposition": "manual_category_review",
            "complete": int((taxonomy.get("interest_counts") or {}).get("general") or 0) == int(low.get("count") or 0),
            "all_reason_coded": all(reason_present(item) for item in low_items if isinstance(item, dict)),
        },
    }

    equations = {
        "strict_reconciliation_pass": bool(recon.get("reconciles_strict")),
        "accepted_equals_map_plus_list": int(recon.get("accepted_canonical_records") or 0)
        == int(recon.get("map_ready_records") or 0) + int(recon.get("list_only_coordinate_records") or 0),
        "stage8_certificate_pass": bool(stage8_cert.get("qa_pass")),
        "stage8_remaining_matches_current_missing": len(stage8_reasons) == int(recon.get("list_only_coordinate_records") or 0),
        "all_core_artifacts_same_generation": bool(core_generation) and all(value == core_generation for value in core_generated_values.values()),
        "schema_validation_pass": bool(validation.get("qa_pass", validation.get("valid", not validation.get("errors")))) if isinstance(validation, dict) else False,
        "every_exception_class_complete": all(bool(item.get("complete")) for item in exception_classes.values()),
        "every_exception_class_reason_coded": all(bool(item.get("all_reason_coded")) for item in exception_classes.values()),
        "no_missing_stage8_reasons": not missing_without_stage8_reason,
        "no_stale_stage8_reasons": not stale_stage8_reason_ids,
        "duplicate_report_uncapped": dupes.get("truncated") is False,
        "approved_private_keys_not_exposed": not public_private_keys,
        "daily_health_ready": str(health.get("status") or health.get("overall_status") or "").upper() == "READY",
    }
    qa_pass = all(equations.values())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    report = {
        "artifact_type": "stage9_complete_exception_ledger",
        "schema_version": "1.0.0",
        "generated_at_utc": now,
        "source_snapshot_generated_at_utc": core_generation,
        "accepted_canonical_records": int(recon.get("accepted_canonical_records") or 0),
        "map_ready_records": int(recon.get("map_ready_records") or 0),
        "list_only_coordinate_records": int(recon.get("list_only_coordinate_records") or 0),
        "approved_projection_rows": len(approved_rows),
        "review_projection_rows": len(review_rows),
        "exception_classes": exception_classes,
        "null_borough_ledger": null_borough_ledger,
        "missing_stage8_reason_ids": missing_without_stage8_reason,
        "stale_stage8_reason_ids": stale_stage8_reason_ids,
        "duplicate_candidate_ids_listed": sorted(duplicate_candidate_ids),
        "lifecycle_status_counts": dict(sorted(lifecycle_counts.items())),
        "approved_private_key_findings": dict(sorted(public_private_keys.items())),
        "core_generation_values": core_generated_values,
        "equations": equations,
        "production_data_modified_by_certificate": False,
        "launch_authorized": False,
        "qa_pass": qa_pass,
    }
    certificate = {
        "artifact_type": "stage9_exception_ledger_certificate",
        "schema_version": "1.0.0",
        "generated_at_utc": now,
        "source_snapshot_generated_at_utc": core_generation,
        "qa_pass": qa_pass,
        "accepted_canonical_records": report["accepted_canonical_records"],
        "map_ready_records": report["map_ready_records"],
        "list_only_coordinate_records": report["list_only_coordinate_records"],
        "exception_class_count": len(exception_classes),
        "exception_classes_complete": equations["every_exception_class_complete"],
        "exception_classes_reason_coded": equations["every_exception_class_reason_coded"],
        "duplicate_group_count": exception_classes["possible_duplicates"]["group_count"],
        "duplicate_candidate_record_count": exception_classes["possible_duplicates"]["candidate_record_count"],
        "null_or_noncanonical_borough_count": exception_classes["null_or_noncanonical_borough"]["count"],
        "strict_reconciliation_pass": equations["strict_reconciliation_pass"],
        "daily_health_ready": equations["daily_health_ready"],
        "launch_authorized": False,
        "equations": equations,
    }
    write(OUT, report)
    write(CERT, certificate)
    print(json.dumps(certificate, indent=2, sort_keys=True))
    if not qa_pass:
        raise RuntimeError("Stage 9 exception ledger certification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
