#!/usr/bin/env python3
"""Phase 2E GPS promotion dry-run only.

Reads the reviewed Phase 2D approval artifact, the Phase 2E readiness report,
and the current location cache, then writes a dry-run report showing what would
be added or updated in a future promotion.

This script does not modify data/location_cache.json, does not modify the
staged feed, does not publish anything to the public map, and does not perform
Phase 2E promotion.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APPROVAL_ARTIFACT_PATH = DATA_DIR / "gps_reviewed_approval_artifact.json"
READINESS_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_readiness_report.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
DRY_RUN_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_dry_run_report.json"

EXPECTED_APPROVED_COUNT = 25
EXPECTED_REVIEWER = "Howard Weiss"


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def missing_required_metadata(row: dict[str, Any]) -> list[str]:
    required = [
        "stable_identity_key",
        "group_key",
        "display_location",
        "borough",
        "proposed_lat",
        "proposed_lng",
        "geocoder_source",
        "geocoder_confidence",
        "confidence_reason",
        "manual_review_status",
        "manual_reviewer",
        "manual_reviewed_at_utc",
        "approval_decision_reason",
        "promotion_allowed",
        "promotion_scope",
    ]
    return [field for field in required if row.get(field) in (None, "")]


def cache_entries_by_key(cache_payload: Any) -> dict[str, Any]:
    """Normalize a location cache into stable identity lookup form.

    The current cache may be empty, dict-like, or list-like. This function only
    reads it and never mutates it.
    """
    output: dict[str, Any] = {}

    if isinstance(cache_payload, dict):
        for key, value in cache_payload.items():
            if isinstance(value, dict):
                stable_key = value.get("stable_identity_key") or value.get("group_key") or key
                output[str(stable_key)] = value
            else:
                output[str(key)] = value
        return output

    if isinstance(cache_payload, list):
        for value in cache_payload:
            if not isinstance(value, dict):
                continue
            stable_key = value.get("stable_identity_key") or value.get("group_key") or value.get("display_location")
            if stable_key:
                output[str(stable_key)] = value

    return output


def candidate_cache_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_identity_key": row.get("stable_identity_key"),
        "group_key": row.get("group_key"),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "lat": row.get("proposed_lat"),
        "lng": row.get("proposed_lng"),
        "geocoder_source": row.get("geocoder_source"),
        "geocoder_confidence": row.get("geocoder_confidence"),
        "source_phase": "phase_2e_promotion_from_reviewed_approval_artifact",
        "manual_reviewer": row.get("manual_reviewer"),
        "manual_reviewed_at_utc": row.get("manual_reviewed_at_utc"),
    }


def existing_coordinates(entry: Any) -> tuple[Any, Any]:
    if not isinstance(entry, dict):
        return None, None
    return entry.get("lat", entry.get("proposed_lat")), entry.get("lng", entry.get("proposed_lng"))


def main() -> int:
    approval_artifact = load_json_file(APPROVAL_ARTIFACT_PATH, {})
    readiness_report = load_json_file(READINESS_REPORT_PATH, {})
    location_cache = load_json_file(LOCATION_CACHE_PATH, {})

    approved_rows = rows_from_payload(approval_artifact, "approved_rows")
    cache_lookup = cache_entries_by_key(location_cache)
    generated_at = datetime.now(timezone.utc).isoformat()

    duplicate_stable_keys = [
        key
        for key, count in Counter(row.get("stable_identity_key") for row in approved_rows).items()
        if key and count > 1
    ]

    proposed_updates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    missing_metadata_rows: list[dict[str, Any]] = []

    for row in approved_rows:
        stable_key = row.get("stable_identity_key")
        metadata_missing = missing_required_metadata(row)
        if metadata_missing:
            missing_metadata_rows.append(
                {
                    "stable_identity_key": stable_key,
                    "display_location": row.get("display_location"),
                    "missing_fields": metadata_missing,
                }
            )

        if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
            invalid_rows.append(
                {
                    "stable_identity_key": stable_key,
                    "display_location": row.get("display_location"),
                    "proposed_lat": row.get("proposed_lat"),
                    "proposed_lng": row.get("proposed_lng"),
                }
            )
            continue

        if row.get("manual_review_status") != "approved" or row.get("manual_reviewer") != EXPECTED_REVIEWER:
            skipped.append(
                {
                    "stable_identity_key": stable_key,
                    "display_location": row.get("display_location"),
                    "reason": "not_approved_by_expected_reviewer",
                }
            )
            continue

        if row.get("promotion_allowed") is not True:
            skipped.append(
                {
                    "stable_identity_key": stable_key,
                    "display_location": row.get("display_location"),
                    "reason": "promotion_allowed_not_true_in_reviewed_artifact",
                }
            )
            continue

        existing = cache_lookup.get(str(stable_key)) if stable_key else None
        action = "add"
        if existing is not None:
            existing_lat, existing_lng = existing_coordinates(existing)
            action = "update"
            if existing_lat != row.get("proposed_lat") or existing_lng != row.get("proposed_lng"):
                conflicts.append(
                    {
                        "stable_identity_key": stable_key,
                        "display_location": row.get("display_location"),
                        "existing_lat": existing_lat,
                        "existing_lng": existing_lng,
                        "proposed_lat": row.get("proposed_lat"),
                        "proposed_lng": row.get("proposed_lng"),
                        "reason": "existing_cache_coordinate_differs_from_reviewed_approval",
                    }
                )
                continue

        proposed_updates.append(
            {
                "action": action,
                "stable_identity_key": stable_key,
                "display_location": row.get("display_location"),
                "cache_record_preview": candidate_cache_record(row),
            }
        )

    qa_pass = (
        readiness_report.get("qa_pass") is True
        and len(approved_rows) == EXPECTED_APPROVED_COUNT
        and len(proposed_updates) == EXPECTED_APPROVED_COUNT
        and not skipped
        and not conflicts
        and not duplicate_stable_keys
        and not invalid_rows
        and not missing_metadata_rows
    )

    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2e_promotion_dry_run_only",
        "qa_pass": qa_pass,
        "readiness_report_qa_pass": readiness_report.get("qa_pass") is True,
        "approved_input_count": len(approved_rows),
        "proposed_cache_update_count": len(proposed_updates),
        "skipped_count": len(skipped),
        "conflict_count": len(conflicts),
        "duplicate_stable_key_count": len(duplicate_stable_keys),
        "invalid_coordinate_count": len(invalid_rows),
        "missing_required_metadata_count": len(missing_metadata_rows),
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "promotion_performed": False,
        "promotion_script_executed": False,
        "input_artifact": str(APPROVAL_ARTIFACT_PATH.relative_to(ROOT)),
        "input_readiness_report": str(READINESS_REPORT_PATH.relative_to(ROOT)),
        "input_location_cache": str(LOCATION_CACHE_PATH.relative_to(ROOT)),
        "proposed_cache_updates": proposed_updates,
        "proposed_cache_update_stable_keys": [row.get("stable_identity_key") for row in proposed_updates],
        "cache_key_conflicts_requiring_human_review": conflicts,
        "skipped_rows": skipped,
        "duplicate_stable_keys": duplicate_stable_keys,
        "invalid_coordinate_rows": invalid_rows,
        "missing_required_metadata_rows": missing_metadata_rows,
        "next_required_step": "If dry-run qa_pass is true, the next step is explicit human authorization for real Phase 2E promotion, or pause GPS and move to Phase 3A Tourist Mode foundation.",
    }

    save_json_file(DRY_RUN_REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
