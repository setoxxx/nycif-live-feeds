from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import (
        build_stable_event_identity as stable_event_identity,
        event_cemsids,
        row_location,
    )
    from scripts.gps_snapshot_provenance import (
        provenance_failure_report,
        validate_bound_snapshot,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import (
        build_stable_event_identity as stable_event_identity,
        event_cemsids,
        row_location,
    )
    from gps_snapshot_provenance import (
        provenance_failure_report,
        validate_bound_snapshot,
    )

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ADJUDICATION_SUMMARY_PATH = DATA_DIR / "gps_staged_feed_integration_adjudication_summary.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
UPDATE_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_update_report.json"

EXPECTED_SAFE_UPDATE_READY_COUNT = 204
EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT = 20


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def failure_report(message: str, **extra: Any) -> dict[str, Any]:
    report = {
        "blocking_issues": [message],
        "conflict_count": int(extra.get("conflict_count", 0) or 0),
        "generated_at_utc": utc_now(),
        "input_adjudication_summary": str(ADJUDICATION_SUMMARY_PATH.relative_to(ROOT)),
        "input_staged_feed": str(STAGED_FEED_PATH.relative_to(ROOT)),
        "location_cache_modified": False,
        "next_required_step": "Inspect this report and fix only the adjudicated staged-feed update contract. Do not publish to the public map and do not run Phase 3A.",
        "phase": "gps_staged_feed_integration_update",
        "phase_3a_run": False,
        "public_map_modified": False,
        "qa_pass": False,
        "safe_update_contract_count": int(extra.get("safe_update_contract_count", 0) or 0),
        "safe_update_ready_identity_count": int(extra.get("safe_update_ready_identity_count", 0) or 0),
        "skipped_count": int(extra.get("skipped_count", EXPECTED_SAFE_UPDATE_READY_COUNT) or 0),
        "staged_feed_modified": False,
        "update_performed": False,
        "updated_staged_event_count": int(extra.get("updated_staged_event_count", 0) or 0),
    }
    report.update(extra)
    report["validated_conditions"] = {
        "adjudication_summary_qa_pass_true": bool(extra.get("adjudication_summary_qa_pass") is True),
        "conflict_count_is_0": report["conflict_count"] == 0,
        "location_cache_modified_false": True,
        "no_safe_staged_match_promoted_key_count_is_20": int(extra.get("no_safe_staged_match_promoted_key_count", 0) or 0) == EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT,
        "phase_3a_run_false": True,
        "public_map_modified_false": True,
        "qa_pass_true": False,
        "safe_update_contract_count_is_204": report["safe_update_contract_count"] == EXPECTED_SAFE_UPDATE_READY_COUNT,
        "safe_update_ready_identity_count_is_204": report["safe_update_ready_identity_count"] == EXPECTED_SAFE_UPDATE_READY_COUNT,
        "skipped_count_is_0": report["skipped_count"] == 0,
        "staged_feed_modified_true": False,
        "update_performed_true": False,
        "updated_staged_event_count_is_204": report["updated_staged_event_count"] == EXPECTED_SAFE_UPDATE_READY_COUNT,
    }
    return report


def safe_contract_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = summary.get("safe_update_ready_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def build_safe_identity_map(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    identity_map: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        identity = str(row.get("stable_event_identity") or "")
        if not identity:
            conflicts.append({"reason": "safe_row_missing_stable_event_identity", "row": row})
            continue
        existing = identity_map.get(identity)
        if existing is not None and existing != row:
            conflicts.append({
                "reason": "duplicate_safe_stable_event_identity_in_adjudication_summary",
                "stable_event_identity": identity,
            })
            continue
        identity_map[identity] = row
    return identity_map, conflicts


def main() -> int:
    try:
        summary = load_json(ADJUDICATION_SUMMARY_PATH, {})
        if not isinstance(summary, dict) or summary.get("qa_pass") is not True:
            save_json(UPDATE_REPORT_PATH, failure_report("Adjudication summary must exist and have qa_pass true", adjudication_summary_qa_pass=summary.get("qa_pass") if isinstance(summary, dict) else None))
            return 1

        snapshot_validation = validate_bound_snapshot(
            summary.get("staged_feed_provenance"),
            STAGED_FEED_PATH,
            repo_root=ROOT,
            contract_source=str(ADJUDICATION_SUMMARY_PATH.relative_to(ROOT)),
        )
        if not snapshot_validation.ok:
            save_json(
                UPDATE_REPORT_PATH,
                provenance_failure_report(
                    snapshot_validation,
                    input_adjudication_summary=str(ADJUDICATION_SUMMARY_PATH.relative_to(ROOT)),
                    input_staged_feed=str(STAGED_FEED_PATH.relative_to(ROOT)),
                ),
            )
            return 1

        staged_payload = load_json(STAGED_FEED_PATH, {})
        if not isinstance(staged_payload, dict) or not isinstance(staged_payload.get("events"), list):
            save_json(UPDATE_REPORT_PATH, failure_report("nycif_staged_live_events.json must be an object with an events list", adjudication_summary_qa_pass=True))
            return 1

        safe_rows = safe_contract_rows(summary)
        safe_identity_count = int(summary.get("safe_update_ready_identity_count") or 0)
        safe_count = int(summary.get("safe_update_ready_count") or 0)
        no_safe_match_count = int(summary.get("no_safe_staged_match_promoted_key_count") or 0)
        multi_key_conflict_count = int(summary.get("multi_key_conflict_count") or 0)
        old_dry_run_target_count = int(summary.get("old_dry_run_target_count") or 0)

        if safe_count != EXPECTED_SAFE_UPDATE_READY_COUNT or safe_identity_count != EXPECTED_SAFE_UPDATE_READY_COUNT or len(safe_rows) != EXPECTED_SAFE_UPDATE_READY_COUNT:
            save_json(
                UPDATE_REPORT_PATH,
                failure_report(
                    "Adjudication summary does not contain exactly 204 safe update rows and identities",
                    adjudication_summary_qa_pass=True,
                    old_dry_run_target_count=old_dry_run_target_count,
                    safe_update_contract_count=safe_count,
                    safe_update_ready_identity_count=safe_identity_count,
                    safe_update_ready_rows_length=len(safe_rows),
                    no_safe_staged_match_promoted_key_count=no_safe_match_count,
                    multi_key_conflict_count=multi_key_conflict_count,
                ),
            )
            return 1
        if no_safe_match_count != EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT or multi_key_conflict_count != 0:
            save_json(
                UPDATE_REPORT_PATH,
                failure_report(
                    "Adjudication summary no-safe-match or conflict counts do not match the 204-safe contract",
                    adjudication_summary_qa_pass=True,
                    old_dry_run_target_count=old_dry_run_target_count,
                    safe_update_contract_count=safe_count,
                    safe_update_ready_identity_count=safe_identity_count,
                    no_safe_staged_match_promoted_key_count=no_safe_match_count,
                    multi_key_conflict_count=multi_key_conflict_count,
                ),
            )
            return 1

        safe_by_identity, contract_conflicts = build_safe_identity_map(safe_rows)
        if contract_conflicts or len(safe_by_identity) != EXPECTED_SAFE_UPDATE_READY_COUNT:
            save_json(
                UPDATE_REPORT_PATH,
                failure_report(
                    "Adjudicated safe identity contract is not unique and complete",
                    adjudication_summary_qa_pass=True,
                    conflict_count=len(contract_conflicts),
                    conflicts=contract_conflicts[:50],
                    old_dry_run_target_count=old_dry_run_target_count,
                    safe_update_contract_count=len(safe_by_identity),
                    safe_update_ready_identity_count=safe_identity_count,
                    no_safe_staged_match_promoted_key_count=no_safe_match_count,
                    multi_key_conflict_count=multi_key_conflict_count,
                ),
            )
            return 1

        matched_identities: set[str] = set()
        duplicate_identity_hits: list[dict[str, Any]] = []
        invalid_coordinate_rows: list[dict[str, Any]] = []
        updated_rows: list[dict[str, Any]] = []
        now = utc_now()

        for event_row in staged_payload["events"]:
            if not isinstance(event_row, dict):
                continue
            identity = stable_event_identity(event_row)
            safe_row = safe_by_identity.get(identity)
            if safe_row is None:
                continue
            if identity in matched_identities:
                duplicate_identity_hits.append({
                    "display_location": row_location(event_row),
                    "reason": "staged_feed_contains_duplicate_safe_stable_event_identity",
                    "source_cemsid": sorted(event_cemsids(event_row)),
                    "source_event_id": event_row.get("source_event_id") or event_row.get("event_id") or event_row.get("id"),
                    "stable_event_identity": identity,
                })
                continue

            lat = safe_row.get("promoted_lat")
            lng = safe_row.get("promoted_lng")
            promoted_cache_key = str(safe_row.get("promoted_cache_key") or "")
            if not promoted_cache_key or not valid_nyc_lat_lng(lat, lng):
                invalid_coordinate_rows.append({
                    "promoted_cache_key": promoted_cache_key,
                    "promoted_lat": lat,
                    "promoted_lng": lng,
                    "reason": "safe_row_missing_valid_promoted_coordinate_or_key",
                    "stable_event_identity": identity,
                })
                continue

            lat_f = float(lat)
            lng_f = float(lng)
            event_row["lat"] = lat_f
            event_row["lng"] = lng_f
            event_row["stable_identity_key"] = promoted_cache_key
            event_row["matched_promoted_cache_keys"] = [promoted_cache_key]
            event_row["group_key"] = promoted_cache_key.removeprefix("group:")
            event_row["gps_integration_phase"] = "gps_staged_feed_integration_update"
            event_row["gps_integration_contract"] = "adjudicated_204_safe_identity_contract"
            event_row["gps_integration_source"] = str(ADJUDICATION_SUMMARY_PATH.relative_to(ROOT))
            event_row["gps_integration_updated_at_utc"] = now
            event_row["location_source"] = "phase_2e_promoted_location_cache"
            event_row["phase_2e_promotion_applied_to_staged_feed"] = True
            event_row["public_map_modified"] = False
            event_row["phase_3a_run"] = False

            matched_identities.add(identity)
            updated_rows.append({
                "current_lat_before_update": safe_row.get("current_lat"),
                "current_lng_before_update": safe_row.get("current_lng"),
                "display_location": row_location(event_row),
                "lat": lat_f,
                "lng": lng_f,
                "match_modes": safe_row.get("match_modes") or {},
                "matched_promoted_cache_keys": [promoted_cache_key],
                "promoted_display_location": safe_row.get("promoted_display_location"),
                "source_cemsid": sorted(event_cemsids(event_row)),
                "source_event_id": event_row.get("source_event_id") or event_row.get("event_id") or event_row.get("id"),
                "stable_event_identity": identity,
                "stable_identity_key": promoted_cache_key,
            })

        unmatched_safe_identities = sorted(set(safe_by_identity) - matched_identities)
        updated_count = len(updated_rows)
        skipped = max(EXPECTED_SAFE_UPDATE_READY_COUNT - updated_count, 0)
        conflict_count = len(duplicate_identity_hits) + len(invalid_coordinate_rows)
        qa_pass = (
            updated_count == EXPECTED_SAFE_UPDATE_READY_COUNT
            and not unmatched_safe_identities
            and skipped == 0
            and conflict_count == 0
        )

        report = {
            "adjudication_count_by_type": summary.get("adjudication_count_by_type") or {},
            "adjudication_summary_qa_pass": summary.get("qa_pass") is True,
            "blocking_issues": [] if qa_pass else ["Adjudicated 204-safe staged-feed update did not meet one or more required counts"],
            "conflict_count": conflict_count,
            "conflicts": (duplicate_identity_hits + invalid_coordinate_rows)[:50],
            "excluded_no_safe_match_promoted_key_count": no_safe_match_count,
            "excluded_no_safe_match_promoted_keys": summary.get("no_safe_staged_match_promoted_keys") or [],
            "generated_at_utc": now,
            "input_adjudication_summary": str(ADJUDICATION_SUMMARY_PATH.relative_to(ROOT)),
            "input_staged_feed": str(STAGED_FEED_PATH.relative_to(ROOT)),
            "location_cache_modified": False,
            "next_required_step": "Run staged-feed GPS integration post-update QA, then decide whether to run a public-map dry-run validation gate. Do not publish to the public map until that gate passes.",
            "old_dry_run_target_count": old_dry_run_target_count,
            "phase": "gps_staged_feed_integration_update",
            "phase_3a_run": False,
            "public_map_modified": False,
            "qa_pass": qa_pass,
            "safe_update_contract_count": len(safe_by_identity),
            "safe_update_ready_identity_count": safe_identity_count,
            "safe_update_source": "gps_staged_feed_integration_adjudication_summary_204_safe_identity_contract",
            "skipped_count": skipped,
            "staged_feed_modified": qa_pass,
            "unmatched_safe_identity_count": len(unmatched_safe_identities),
            "unmatched_safe_identities": unmatched_safe_identities[:50],
            "update_performed": qa_pass,
            "updated_staged_event_count": updated_count,
            "updated_staged_event_sample": updated_rows[:25],
            "validated_conditions": {
                "adjudication_summary_qa_pass_true": summary.get("qa_pass") is True,
                "conflict_count_is_0": conflict_count == 0,
                "excluded_no_safe_match_promoted_key_count_is_20": no_safe_match_count == EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT,
                "location_cache_modified_false": True,
                "old_dry_run_target_430_not_required": old_dry_run_target_count != EXPECTED_SAFE_UPDATE_READY_COUNT,
                "phase_3a_run_false": True,
                "public_map_modified_false": True,
                "qa_pass_true": qa_pass,
                "safe_update_contract_count_is_204": len(safe_by_identity) == EXPECTED_SAFE_UPDATE_READY_COUNT,
                "safe_update_ready_identity_count_is_204": safe_identity_count == EXPECTED_SAFE_UPDATE_READY_COUNT,
                "skipped_count_is_0": skipped == 0,
                "snapshot_contract_preflight_passed": True,
                "staged_feed_modified_true": qa_pass,
                "unmatched_safe_identity_count_is_0": len(unmatched_safe_identities) == 0,
                "update_performed_true": qa_pass,
                "updated_staged_event_count_is_204": updated_count == EXPECTED_SAFE_UPDATE_READY_COUNT,
            },
        }

        save_json(UPDATE_REPORT_PATH, report)
        if qa_pass:
            save_json(STAGED_FEED_PATH, staged_payload)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if qa_pass else 1
    except Exception as exc:
        save_json(
            UPDATE_REPORT_PATH,
            failure_report(
                "Unhandled staged-feed integration runtime exception",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                traceback=traceback.format_exc(),
            ),
        )
        raise


if __name__ == "__main__":
    sys.exit(main())
