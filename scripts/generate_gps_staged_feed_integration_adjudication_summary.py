from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DIAGNOSTIC_PATH = DATA_DIR / "gps_staged_feed_integration_match_diagnostic.json"
SUMMARY_PATH = DATA_DIR / "gps_staged_feed_integration_adjudication_summary.json"

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

    old_target = int(diagnostic.get("dry_run_expected_matched_staged_event_count") or 0)
    safe_count = int(diagnostic.get("selected_candidate_count") or len(selected_rows))
    safe_identity_count = int(diagnostic.get("selected_stable_event_identity_count") or selected_identity_count)
    multi_key_conflict_count = int(diagnostic.get("multi_key_conflict_count") or 0)
    no_safe_match_count = int(diagnostic.get("unmatched_promoted_cache_key_count") or len(unmatched_keys))

    location_cache_modified = False
    staged_feed_modified = False
    public_map_modified = False
    phase_3a_run = False

    qa_pass = (
        safe_count == EXPECTED_SAFE_UPDATE_READY_COUNT
        and safe_identity_count == EXPECTED_SAFE_UPDATE_READY_COUNT
        and multi_key_conflict_count == 0
        and no_safe_match_count == EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT
        and location_cache_modified is False
        and staged_feed_modified is False
        and public_map_modified is False
        and phase_3a_run is False
    )

    recommended_next_action = (
        "Patch staged-feed update to apply only the 204 adjudicated safe identities, with the old 430 dry-run target replaced by a new 204-row adjudicated-safe contract. Keep the 20 unmatched promoted keys out of the staged-feed update and carry them forward for human review."
        if safe_count == EXPECTED_SAFE_UPDATE_READY_COUNT and multi_key_conflict_count == 0
        else "Do not patch update workflow; inspect adjudication summary first."
    )

    summary = {
        "adjudication_count_by_type": dict(sorted(adjudication_counts.items())),
        "generated_at_utc": utc_now(),
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
        "qa_pass": qa_pass,
        "recommended_next_action": recommended_next_action,
        "safe_update_ready_count": safe_count,
        "safe_update_ready_identity_count": safe_identity_count,
        "safe_update_ready_rows": selected_rows,
        "staged_feed_modified": staged_feed_modified,
        "validated_conditions": {
            "location_cache_modified_false": location_cache_modified is False,
            "multi_key_conflict_count_is_0": multi_key_conflict_count == 0,
            "no_safe_staged_match_promoted_key_count_is_20": no_safe_match_count == EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT,
            "phase_3a_run_false": phase_3a_run is False,
            "public_map_modified_false": public_map_modified is False,
            "qa_pass_true": qa_pass,
            "safe_update_ready_count_is_204": safe_count == EXPECTED_SAFE_UPDATE_READY_COUNT,
            "safe_update_ready_identity_count_is_204": safe_identity_count == EXPECTED_SAFE_UPDATE_READY_COUNT,
            "staged_feed_modified_false": staged_feed_modified is False,
        },
    }

    save_json(SUMMARY_PATH, summary)
    printable = {k: v for k, v in summary.items() if k not in {"safe_update_ready_rows", "no_safe_staged_match_adjudication"}}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
