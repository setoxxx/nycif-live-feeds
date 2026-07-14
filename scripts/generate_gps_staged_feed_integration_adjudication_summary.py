from __future__ import annotations

import copy
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_count_contract import (
        ADJUDICATION_PRODUCER_SCRIPT,
        build_count_contract,
        canonicalize_adjudication_summary,
        finalize_count_contract_adjudication_hash,
        validate_count_contract_for_apply,
        validate_count_contract_internal,
    )
    from scripts.gps_snapshot_provenance import (
        DEFAULT_STAGED_FEED_RELATIVE_PATH,
        REGENERATE_ARTIFACTS_NEXT_STEP,
        sha256_file,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_count_contract import (
        ADJUDICATION_PRODUCER_SCRIPT,
        build_count_contract,
        canonicalize_adjudication_summary,
        finalize_count_contract_adjudication_hash,
        validate_count_contract_for_apply,
        validate_count_contract_internal,
    )
    from gps_snapshot_provenance import (
        DEFAULT_STAGED_FEED_RELATIVE_PATH,
        REGENERATE_ARTIFACTS_NEXT_STEP,
        sha256_file,
    )

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_SCRIPT = ADJUDICATION_PRODUCER_SCRIPT
DATA_DIR = ROOT / "data"
DIAGNOSTIC_PATH = DATA_DIR / "gps_staged_feed_integration_match_diagnostic.json"
SUMMARY_PATH = DATA_DIR / "gps_staged_feed_integration_adjudication_summary.json"


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


def slim_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_event_identity": row.get("stable_event_identity"),
        "source_event_id": row.get("source_event_id"),
        "display_location": row.get("display_location"),
        "source_cemsid": row.get("source_cemsid") or [],
        "promoted_cache_key": row.get("promoted_cache_key"),
        "promoted_display_location": row.get("promoted_display_location"),
        "promoted_lat": row.get("promoted_lat"),
        "promoted_lng": row.get("promoted_lng"),
        "current_lat": row.get("current_lat"),
        "current_lng": row.get("current_lng"),
        "match_modes": row.get("match_modes") or {},
    }


def sample_rows(rows: Any, limit: int = 5) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    sample: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        sample.append({
            "best_event_facility": row.get("best_event_facility"),
            "best_event_site": row.get("best_event_site"),
            "best_facility_score": row.get("best_facility_score"),
            "best_promoted_facility": row.get("best_promoted_facility"),
            "best_promoted_site": row.get("best_promoted_site"),
            "best_site_score": row.get("best_site_score"),
            "coordinate_distance_meters": row.get("coordinate_distance_meters"),
            "display_location": row.get("display_location"),
            "event_borough": row.get("event_borough"),
            "exact_coordinate_match": row.get("exact_coordinate_match"),
            "facility_number_match": row.get("facility_number_match"),
            "facility_type_match": row.get("facility_type_match"),
            "overlapping_cemsids": row.get("overlapping_cemsids") or [],
            "rejection_reasons": row.get("rejection_reasons") or [],
            "source_cemsid": row.get("source_cemsid") or [],
            "source_event_id": row.get("source_event_id"),
            "stable_event_identity": row.get("stable_event_identity"),
            "title": row.get("title"),
        })
    return sample


def adjudicate_unmatched_key(promoted_key: str, near_miss: dict[str, Any]) -> dict[str, Any]:
    reason_counts = near_miss.get("rejection_reason_counts") or {}
    same_site = near_miss.get("closest_same_site_candidates") or []
    same_coordinate = near_miss.get("same_coordinate_candidates") or []
    same_cemsid = near_miss.get("same_cemsid_candidates") or []
    same_facility = near_miss.get("closest_same_facility_candidates") or []

    same_site_wrong_facility = any(
        isinstance(row, dict)
        and row.get("best_site_score") == 100.0
        and ("facility_number_mismatch" in (row.get("rejection_reasons") or []) or "facility_type_mismatch" in (row.get("rejection_reasons") or []))
        for row in same_site
    )
    same_coordinate_wrong_facility = any(
        isinstance(row, dict)
        and row.get("exact_coordinate_match") is True
        and ("facility_number_mismatch" in (row.get("rejection_reasons") or []) or "facility_type_mismatch" in (row.get("rejection_reasons") or []))
        for row in same_coordinate
    )

    if same_site_wrong_facility:
        adjudication = "review_required_same_site_wrong_facility"
    elif same_coordinate_wrong_facility:
        adjudication = "review_required_same_coordinate_wrong_facility"
    elif same_facility or same_coordinate or same_site:
        adjudication = "review_required_possible_old_dry_run_overmatch"
    else:
        adjudication = "no_safe_match_do_not_update"

    return {
        "adjudication": adjudication,
        "closest_same_facility_sample": sample_rows(same_facility),
        "closest_same_site_sample": sample_rows(same_site),
        "promoted_cache_key": promoted_key,
        "rejection_reason_counts": reason_counts,
        "same_cemsid_candidate_count": len(same_cemsid) if isinstance(same_cemsid, list) else 0,
        "same_coordinate_sample": sample_rows(same_coordinate),
    }


def recommended_next_action_for_contract(
    *,
    safe_identity_count: int,
    no_safe_match_count: int,
    old_target: int,
    multi_key_conflict_count: int,
) -> str:
    if multi_key_conflict_count != 0:
        return "Do not patch update workflow; inspect adjudication summary first."
    return (
        f"Patch staged-feed update to apply only the {safe_identity_count} adjudicated "
        f"safe identities, with the old {old_target}-row dry-run target replaced by a new "
        f"{safe_identity_count}-row adjudicated-safe contract. Keep the {no_safe_match_count} "
        "unmatched promoted keys out of the staged-feed update and carry them forward for "
        "human review."
    )


def main() -> int:
    diagnostic = load_json(DIAGNOSTIC_PATH, {})
    if not isinstance(diagnostic, dict):
        diagnostic = {}

    selected_rows_raw = diagnostic.get("selected_stable_identity_rows") or []
    selected_rows = [slim_safe_row(row) for row in selected_rows_raw if isinstance(row, dict)]
    selected_identity_count = len({row.get("stable_event_identity") for row in selected_rows if row.get("stable_event_identity")})

    unmatched_keys = diagnostic.get("unmatched_promoted_cache_keys") or []
    if not isinstance(unmatched_keys, list):
        unmatched_keys = []

    near_misses = diagnostic.get("near_miss_diagnostics_by_promoted_cache_key") or {}
    if not isinstance(near_misses, dict):
        near_misses = {}

    unmatched_adjudication = [
        adjudicate_unmatched_key(str(key), near_misses.get(str(key)) or {})
        for key in unmatched_keys
    ]
    adjudication_counts = Counter(item["adjudication"] for item in unmatched_adjudication)
    adjudication_count_by_type = dict(sorted(adjudication_counts.items()))

    old_target = int(diagnostic.get("dry_run_expected_matched_staged_event_count") or 0)
    safe_count = int(diagnostic.get("selected_candidate_count") or len(selected_rows))
    safe_identity_count = int(diagnostic.get("selected_stable_event_identity_count") or selected_identity_count)
    multi_key_conflict_count = int(diagnostic.get("multi_key_conflict_count") or 0)
    no_safe_match_count = int(diagnostic.get("unmatched_promoted_cache_key_count") or len(unmatched_keys))

    location_cache_modified = False
    staged_feed_modified = False
    public_map_modified = False
    phase_3a_run = False

    diagnostic_provenance = diagnostic.get("staged_feed_provenance")
    provenance_present = isinstance(diagnostic_provenance, dict) and bool(
        (diagnostic_provenance.get("staged_feed") or {}).get("sha256")
    )
    diagnostic_artifact_sha256 = sha256_file(DIAGNOSTIC_PATH) if DIAGNOSTIC_PATH.exists() else None

    if provenance_present:
        staged_feed_provenance = copy.deepcopy(diagnostic_provenance)
        staged_feed_provenance["producer"] = {
            "script": PRODUCER_SCRIPT,
            "generated_at_utc": utc_now(),
            "upstream_artifact_sha256": diagnostic_artifact_sha256,
        }
    else:
        staged_feed_provenance = None

    generated_at = utc_now()
    safe_update_count_contract = None
    count_contract_valid = False
    if provenance_present and staged_feed_provenance is not None:
        safe_update_count_contract = build_count_contract(
            staged_feed_provenance=staged_feed_provenance,
            diagnostic_artifact_sha256=diagnostic_artifact_sha256,
            selected_rows=selected_rows,
            no_safe_match_count=no_safe_match_count,
            multi_key_conflict_count=multi_key_conflict_count,
            adjudication_count_by_type=adjudication_count_by_type,
            generated_at_utc=generated_at,
        )

    blocking_issues: list[str] = []
    if not provenance_present:
        blocking_issues.append(
            "Diagnostic artifact is missing staged_feed_provenance; regenerate diagnostic "
            "against the current staged feed"
        )
    if safe_count != safe_identity_count or safe_count != len(selected_rows):
        blocking_issues.append("Selected safe rows and identity counts are inconsistent")
    if multi_key_conflict_count != 0:
        blocking_issues.append("Multi-key conflicts must remain zero for safe-update contracts")

    summary: dict[str, Any] = {
        "adjudication_count_by_type": adjudication_count_by_type,
        "blocking_issues": blocking_issues,
        "diagnostic_artifact_sha256": diagnostic_artifact_sha256,
        "generated_at_utc": generated_at,
        "input_diagnostic": str(DIAGNOSTIC_PATH.relative_to(ROOT)),
        "location_cache_modified": location_cache_modified,
        "multi_key_conflict_count": multi_key_conflict_count,
        "no_safe_staged_match_adjudication": unmatched_adjudication,
        "no_safe_staged_match_promoted_key_count": no_safe_match_count,
        "no_safe_staged_match_promoted_keys": unmatched_keys,
        "old_dry_run_target_count": old_target,
        "phase": "gps_staged_feed_integration_adjudication_summary",
        "phase_3a_run": phase_3a_run,
        "public_map_modified": public_map_modified,
        "safe_update_count_contract": safe_update_count_contract,
        "safe_update_ready_count": safe_count,
        "safe_update_ready_identity_count": safe_identity_count,
        "safe_update_ready_rows": selected_rows,
        "staged_feed_modified": staged_feed_modified,
        "staged_feed_provenance": staged_feed_provenance,
    }

    if safe_update_count_contract is not None:
        count_validation = validate_count_contract_internal(
            safe_update_count_contract,
            summary,
        )
        count_contract_valid = count_validation.ok
        if not count_contract_valid:
            blocking_issues.append(count_validation.message or "Count contract internal validation failed")

    contract_counts = (
        (safe_update_count_contract or {}).get("counts") or {}
        if isinstance(safe_update_count_contract, dict)
        else {}
    )
    contract_safe_identity_count = int(contract_counts.get("safe_update_ready_identity_count") or 0)
    contract_no_safe_match_count = int(contract_counts.get("no_safe_match_promoted_key_count") or 0)

    qa_pass = (
        provenance_present
        and count_contract_valid
        and safe_update_count_contract is not None
        and multi_key_conflict_count == 0
        and not blocking_issues
        and location_cache_modified is False
        and staged_feed_modified is False
        and public_map_modified is False
        and phase_3a_run is False
    )

    if not provenance_present:
        recommended_next_action = REGENERATE_ARTIFACTS_NEXT_STEP
    elif qa_pass:
        recommended_next_action = recommended_next_action_for_contract(
            safe_identity_count=contract_safe_identity_count,
            no_safe_match_count=contract_no_safe_match_count,
            old_target=old_target,
            multi_key_conflict_count=multi_key_conflict_count,
        )
    else:
        recommended_next_action = "Do not patch update workflow; inspect adjudication summary first."

    summary.update(
        {
            "blocking_issues": blocking_issues,
            "qa_pass": qa_pass,
            "recommended_next_action": recommended_next_action,
            "validated_conditions": {
                "adjudication_artifact_hash_finalized": safe_update_count_contract is not None,
                "count_contract_internally_consistent": count_contract_valid,
                "count_contract_present": safe_update_count_contract is not None,
                "diagnostic_staged_feed_provenance_present": provenance_present,
                "location_cache_modified_false": location_cache_modified is False,
                "multi_key_conflict_count_is_0": multi_key_conflict_count == 0,
                "no_safe_staged_match_promoted_key_count_matches_contract": (
                    contract_no_safe_match_count == no_safe_match_count
                ),
                "phase_3a_run_false": phase_3a_run is False,
                "public_map_modified_false": public_map_modified is False,
                "qa_pass_true": qa_pass,
                "safe_update_ready_count_matches_contract": contract_safe_identity_count == safe_count,
                "safe_update_ready_identity_count_matches_contract": (
                    contract_safe_identity_count == safe_identity_count
                ),
                "staged_feed_modified_false": staged_feed_modified is False,
            },
        }
    )

    if safe_update_count_contract is not None:
        summary = canonicalize_adjudication_summary(summary)
        finalize_count_contract_adjudication_hash(summary)
        apply_validation = validate_count_contract_for_apply(summary)
        if not apply_validation.ok:
            blocking_issues.append(
                apply_validation.message or "Adjudication artifact finalization validation failed"
            )
            summary["blocking_issues"] = blocking_issues
            summary["qa_pass"] = False
            summary["validated_conditions"]["qa_pass_true"] = False
            summary["validated_conditions"]["adjudication_artifact_hash_finalized"] = False
            summary = canonicalize_adjudication_summary(summary)
            finalize_count_contract_adjudication_hash(summary)
            retry_validation = validate_count_contract_for_apply(summary)
            if not retry_validation.ok:
                save_json(
                    SUMMARY_PATH,
                    {
                        **summary,
                        "validated_conditions": {
                            **summary["validated_conditions"],
                            "adjudication_artifact_finalization_failed": True,
                        },
                    },
                )
                printable = {
                    k: v
                    for k, v in summary.items()
                    if k not in {"safe_update_ready_rows", "no_safe_staged_match_adjudication"}
                }
                print(json.dumps(printable, indent=2, ensure_ascii=False))
                return 1

    save_json(SUMMARY_PATH, summary)
    if safe_update_count_contract is not None:
        reloaded = load_json(SUMMARY_PATH, {})
        if not validate_count_contract_for_apply(reloaded).ok:
            return 1
    printable = {k: v for k, v in summary.items() if k not in {"safe_update_ready_rows", "no_safe_staged_match_adjudication"}}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
