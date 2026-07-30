#!/usr/bin/env python3
"""Certify every current discovery exception class from one snapshot."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_stage9_uncapped_duplicate_queue import canonical_population

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = DATA / "reports"
OUT = REPORTS / "stage9_exception_ledger.json"
CERT = REPORTS / "stage9_exception_ledger_certificate.json"
CANONICAL_BOROUGHS = {"Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"}
PRIVATE_KEYS = {
    "internal_notes", "editorial_notes", "private_notes", "reviewer_notes",
    "operator_notes", "raw_payload", "debug", "debug_notes",
}

PATHS = {
    "reconciliation": DATA / "events_discovery_reconciliation_v02.json",
    "taxonomy": DATA / "events_discovery_taxonomy_v02_audit.json",
    "validation": DATA / "events_discovery_schema_validation_v02.json",
    "invalid": DATA / "events_discovery_invalid_records_v02.json",
    "low": DATA / "events_discovery_low_confidence_v02.json",
    "missing": DATA / "events_discovery_missing_coordinates_v02.json",
    "duplicates": DATA / "events_discovery_possible_duplicates_v02.json",
    "legacy": DATA / "events_discovery_legacy_major_quarantine_v02.json",
    "approved": DATA / "events_discovery_v02_approved.json",
    "review": DATA / "events_discovery_v02_review.json",
    "stage8_inventory": REPORTS / "stage8_list_only_coordinate_inventory.json",
    "stage8_certificate": REPORTS / "stage8_supported_coordinate_resolution_certificate.json",
    "approved_dedupe": REPORTS / "discovery_approved_dedupe_report.json",
    "shared_cems_dedupe": REPORTS / "discovery_shared_cems_occurrence_dedupe_report.json",
    "health": ROOT / "status" / "nycif-daily-data-health.json",
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
        for key in ("events", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def items(payload: Any, key: str = "items") -> list[dict[str, Any]]:
    value = payload.get(key) if isinstance(payload, dict) else []
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def generated(payload: Any) -> str:
    return str(payload.get("generated_at_utc") or payload.get("generated_at") or "") if isinstance(payload, dict) else ""


def nycif(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("nycif") if isinstance(row.get("nycif"), dict) else {}


def source(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def cid(row: dict[str, Any]) -> str:
    return str(row.get("canonical_id") or row.get("id") or "").strip()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def finite(value: Any) -> float | None:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def valid_nyc(row: dict[str, Any]) -> bool:
    lat = finite(row.get("latitude", row.get("lat")))
    lng = finite(row.get("longitude", row.get("lng")))
    return lat is not None and lng is not None and 40.45 <= lat <= 40.95 and -74.30 <= lng <= -73.65


def reason_present(row: dict[str, Any]) -> bool:
    return any(row.get(key) for key in (
        "reason_code", "reason_for_review", "reason", "disposition", "recommended_action"
    ))


def private_findings(value: Any) -> Counter[str]:
    found: Counter[str] = Counter()
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in PRIVATE_KEYS and child not in (None, "", [], {}):
                found[str(key).lower()] += 1
            found.update(private_findings(child))
    elif isinstance(value, list):
        for child in value:
            found.update(private_findings(child))
    return found


def stage8_reasons(payload: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in items(payload, "ledger"):
        reason = str(row.get("reason_code") or "").strip()
        if reason and reason != "supported_coordinate_proposal" and cid(row):
            out[cid(row)] = reason
    return out


def borough_reason(row: dict[str, Any]) -> str:
    text = " ".join(norm(row.get(key)) for key in ("title", "description", "location", "address", "venue"))
    if any(token in text for token in ("online event", "virtual event", "zoom", "webinar", "livestream", "live stream")):
        return "online_no_single_borough_required"
    if any(token in text for token in ("citywide", "multiple locations", "various locations", "multiple parks")):
        return "citywide_or_multi_location_no_single_borough"
    if valid_nyc(row):
        return "borough_normalization_pending_with_valid_nyc_coordinates"
    if nycif(row).get("coordinate_status") == "list_only":
        return "list_only_location_reason_coded_separately"
    if not str(row.get("location") or row.get("address") or "").strip():
        return "missing_location_text"
    return "physical_location_borough_unresolved"


def main() -> int:
    p = {name: load(path) for name, path in PATHS.items()}
    recon = p["reconciliation"]
    expected = int(recon.get("accepted_canonical_records") or 0)
    approved = rows(p["approved"])
    review = rows(p["review"])
    canonical, population = canonical_population(approved, review, expected)

    invalid = items(p["invalid"])
    low = items(p["low"])
    missing = items(p["missing"])
    duplicate_groups = items(p["duplicates"], "groups")
    legacy = items(p["legacy"])
    remaining_reasons = stage8_reasons(p["stage8_inventory"])
    missing_ids = {cid(row) for row in missing if cid(row)}
    missing_reason_ids = sorted(missing_ids - set(remaining_reasons))
    stale_reason_ids = sorted(set(remaining_reasons) - missing_ids)

    null_borough = [row for row in canonical if str(row.get("borough") or "").strip() not in CANONICAL_BOROUGHS]
    null_reason_counts = Counter(borough_reason(row) for row in null_borough)
    null_ledger = [{
        "canonical_id": cid(row),
        "source_dataset": source(row).get("dataset"),
        "source_event_id": source(row).get("source_event_id"),
        "title": row.get("title"),
        "date": nycif(row).get("event_date") or str(row.get("start_date_time") or "")[:10],
        "location": row.get("location") or row.get("address"),
        "coordinate_status": nycif(row).get("coordinate_status"),
        "reason_code": borough_reason(row),
    } for row in null_borough]

    lifecycle_counts: Counter[str] = Counter()
    for row in canonical:
        status = norm(row.get("status") or row.get("event_status") or nycif(row).get("lifecycle_status"))
        lifecycle_counts[status or "source_status_not_published"] += 1

    duplicate_ids = {
        str(identifier)
        for group in duplicate_groups
        for identifier in (group.get("ids") if isinstance(group.get("ids"), list) else [])
        if identifier
    }
    duplicate_records = sum(int(group.get("count") or 0) for group in duplicate_groups)
    taxonomy = p["taxonomy"]
    role_counts = taxonomy.get("event_role_counts") if isinstance(taxonomy.get("event_role_counts"), dict) else {}
    interest_counts = taxonomy.get("interest_counts") if isinstance(taxonomy.get("interest_counts"), dict) else {}

    classes = {
        "schema_invalid": {
            "count": int(p["invalid"].get("count") or 0), "queue_count": len(invalid),
            "disposition": "empty_pass" if not invalid else "reason_coded_rejection_queue",
            "complete": len(invalid) == int(p["invalid"].get("count") or 0),
            "reason_coded": all(reason_present(row) for row in invalid),
        },
        "low_classification_confidence": {
            "count": int(p["low"].get("count") or 0), "queue_count": len(low),
            "disposition": "manual_category_review",
            "complete": len(low) == int(p["low"].get("count") or 0),
            "reason_coded": all(reason_present(row) for row in low),
        },
        "list_only_coordinates": {
            "count": int(p["missing"].get("count") or 0), "queue_count": len(missing),
            "stage8_reason_count": len(remaining_reasons),
            "disposition": "retained_list_only_with_stage8_reason",
            "complete": len(missing) == int(p["missing"].get("count") or 0),
            "reason_coded": not missing_reason_ids and not stale_reason_ids,
        },
        "possible_duplicates": {
            "group_count": int(p["duplicates"].get("count") or 0),
            "queue_group_count": len(duplicate_groups),
            "candidate_record_count": int(p["duplicates"].get("candidate_record_count") or duplicate_records),
            "unique_candidate_id_count": len(duplicate_ids),
            "disposition": "manual_duplicate_review_no_auto_merge",
            "complete": len(duplicate_groups) == int(p["duplicates"].get("count") or 0)
                and p["duplicates"].get("truncated") is False,
            "reason_coded": all(reason_present(row) for row in duplicate_groups),
        },
        "legacy_major_quarantine": {
            "count": int((p["legacy"].get("summary") or {}).get("quarantined") or 0),
            "queue_count": len(legacy), "disposition": "quarantine_from_major_feed",
            "complete": len(legacy) == int((p["legacy"].get("summary") or {}).get("quarantined") or 0),
            "reason_coded": all(reason_present(row) for row in legacy),
        },
        "null_or_noncanonical_borough": {
            "count": len(null_borough), "reason_counts": dict(sorted(null_reason_counts.items())),
            "disposition": "reason_coded_location_exception",
            "complete": len(null_ledger) == len(null_borough),
            "reason_coded": all(row["reason_code"] for row in null_ledger),
        },
        "private_or_reserved": {
            "count": int(role_counts.get("private_or_reserved_activity") or 0),
            "disposition": "nonpublic_role_not_normal_public_marker", "complete": True, "reason_coded": True,
        },
        "maintenance_or_closure": {
            "count": int(role_counts.get("maintenance_or_closure") or 0),
            "disposition": "separate_non_event_display_role", "complete": True, "reason_coded": True,
        },
        "general_or_fallback_category": {
            "count": int(interest_counts.get("general") or 0),
            "disposition": "manual_category_review",
            "complete": int(interest_counts.get("general") or 0) == int(p["low"].get("count") or 0),
            "reason_coded": all(reason_present(row) for row in low),
        },
        "lifecycle_status": {
            "count": expected, "status_counts": dict(sorted(lifecycle_counts.items())),
            "disposition": "accepted_current_snapshot_or_explicit_invalid_queue",
            "complete": sum(lifecycle_counts.values()) == expected, "reason_coded": True,
        },
    }

    core_time = generated(recon)
    same_time = {
        name: generated(p[name])
        for name in ("reconciliation", "taxonomy", "invalid", "low", "missing", "duplicates")
    }
    private = private_findings(p["approved"])
    equations = {
        "canonical_population_exact": len(canonical) == expected,
        "strict_reconciliation_pass": bool(recon.get("reconciles_strict")),
        "accepted_equals_map_plus_list": expected == int(recon.get("map_ready_records") or 0)
            + int(recon.get("list_only_coordinate_records") or 0),
        "schema_validation_pass": p["validation"].get("qa_pass") is True
            and int(p["validation"].get("total_validated") or 0) == expected,
        "stage8_certificate_pass": p["stage8_certificate"].get("qa_pass") is True,
        "stage8_remaining_matches_current_missing": len(remaining_reasons)
            == int(recon.get("list_only_coordinate_records") or 0),
        "all_core_artifacts_same_generation": bool(core_time) and all(value == core_time for value in same_time.values()),
        "approved_dedupe_pass": p["approved_dedupe"].get("qa_pass") is True,
        "shared_cems_dedupe_pass": p["shared_cems_dedupe"].get("qa_pass") is True,
        "all_exception_classes_complete": all(row["complete"] for row in classes.values()),
        "all_exception_classes_reason_coded": all(row["reason_coded"] for row in classes.values()),
        "no_missing_stage8_reasons": not missing_reason_ids,
        "no_stale_stage8_reasons": not stale_reason_ids,
        "duplicate_report_uncapped": p["duplicates"].get("truncated") is False,
        "approved_private_keys_not_exposed": not private,
        "daily_health_ready": p["health"].get("status") == "READY"
            and p["health"].get("release_ready") is True and not p["health"].get("blockers"),
    }
    qa_pass = all(equations.values())
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "artifact_type": "stage9_complete_exception_ledger", "schema_version": "2.0.0",
        "generated_at_utc": now, "source_snapshot_generated_at_utc": core_time,
        "accepted_canonical_records": expected,
        "map_ready_records": int(recon.get("map_ready_records") or 0),
        "list_only_coordinate_records": int(recon.get("list_only_coordinate_records") or 0),
        "population_reconstruction": population,
        "exception_classes": classes,
        "null_borough_ledger": null_ledger,
        "missing_stage8_reason_ids": missing_reason_ids,
        "stale_stage8_reason_ids": stale_reason_ids,
        "duplicate_candidate_ids": sorted(duplicate_ids),
        "approved_private_key_findings": dict(sorted(private.items())),
        "core_generation_values": same_time,
        "equations": equations,
        "production_data_modified_by_certificate": False,
        "launch_authorized": False, "qa_pass": qa_pass,
    }
    certificate = {
        "artifact_type": "stage9_exception_ledger_certificate", "schema_version": "2.0.0",
        "generated_at_utc": now, "source_snapshot_generated_at_utc": core_time,
        "qa_pass": qa_pass, "accepted_canonical_records": expected,
        "map_ready_records": report["map_ready_records"],
        "list_only_coordinate_records": report["list_only_coordinate_records"],
        "exception_class_count": len(classes),
        "exception_classes_complete": equations["all_exception_classes_complete"],
        "exception_classes_reason_coded": equations["all_exception_classes_reason_coded"],
        "duplicate_group_count": classes["possible_duplicates"]["group_count"],
        "duplicate_candidate_record_count": classes["possible_duplicates"]["candidate_record_count"],
        "null_or_noncanonical_borough_count": classes["null_or_noncanonical_borough"]["count"],
        "strict_reconciliation_pass": equations["strict_reconciliation_pass"],
        "daily_health_ready": equations["daily_health_ready"],
        "launch_authorized": False, "equations": equations,
    }
    write(OUT, report)
    write(CERT, certificate)
    print(json.dumps(certificate, indent=2, sort_keys=True))
    if not qa_pass:
        raise RuntimeError("Stage 9 exception ledger certification failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
