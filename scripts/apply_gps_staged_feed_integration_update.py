from __future__ import annotations

import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
PROMOTION_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_report.json"
DRY_RUN_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_dry_run_report.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
UPDATE_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_update_report.json"

EXPECTED_PROMOTED_CACHE_KEYS = 25
EXPECTED_UPDATED_STAGED_EVENTS = 430


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


def normalize(text: Any) -> str:
    text = str(text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: Any) -> list[str]:
    return normalize(text).split()


def stable_key(borough: Any, location: Any) -> str:
    return f"group:{normalize(borough)}|{normalize(location)}"


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def unwrap_location_cache(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return payload["entries"]
    if isinstance(payload, dict):
        return payload
    return {}


def event_locations(row: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for field in ("display_location", "location", "event_location"):
        value = row.get(field)
        if value:
            norm = normalize(value)
            if norm and norm not in seen:
                seen.add(norm)
                values.append(str(value))
    return values


def event_aliases(row: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for field in (
        "stable_identity_key",
        "group_key",
        "cache_key",
        "gps_cache_key",
        "gps_group_key",
        "review_group_key",
    ):
        value = row.get(field)
        if value:
            aliases.add(str(value))
            if not str(value).startswith("group:"):
                aliases.add(f"group:{value}")

    borough = row.get("borough") or row.get("event_borough")
    for value in event_locations(row):
        if borough and value:
            aliases.add(stable_key(borough, value))
    return aliases


def cache_aliases(key: str, row: dict[str, Any]) -> set[str]:
    aliases = {key}
    for field in ("stable_identity_key", "group_key", "cache_key", "gps_cache_key", "key_value"):
        value = row.get(field)
        if value:
            aliases.add(str(value))
            if not str(value).startswith("group:"):
                aliases.add(f"group:{value}")

    borough = row.get("borough") or row.get("event_borough")
    for field in ("display_location", "location", "event_location"):
        value = row.get(field)
        if borough and value:
            aliases.add(stable_key(borough, value))
    return aliases


def borough_of(row: dict[str, Any]) -> str:
    return normalize(row.get("borough") or row.get("event_borough"))


def component_location_match(cache_row: dict[str, Any], event_row: dict[str, Any]) -> bool:
    if borough_of(cache_row) != borough_of(event_row):
        return False
    cache_location = cache_row.get("display_location") or cache_row.get("location") or cache_row.get("event_location")
    cache_norm = normalize(cache_location)
    if not cache_norm:
        return False

    cache_tokens = tokens(cache_location)
    if not cache_tokens:
        return False

    for event_location in event_locations(event_row):
        event_norm = normalize(event_location)
        if not event_norm:
            continue
        if cache_norm in event_norm or event_norm in cache_norm:
            return True
        event_token_set = set(tokens(event_location))
        if all(token in event_token_set for token in cache_tokens):
            return True
    return False


def extract_promoted_cache(location_cache_payload: Any, promotion_report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    location_entries = unwrap_location_cache(location_cache_payload)

    flagged = {
        key: value
        for key, value in location_entries.items()
        if isinstance(value, dict) and value.get("phase_2e_promotion_performed") is True
    }
    if flagged:
        return flagged, "location_cache_phase_2e_flags"

    promoted_rows = promotion_report.get("promoted_rows")
    if isinstance(promoted_rows, list):
        promoted: dict[str, dict[str, Any]] = {}
        for row in promoted_rows:
            if not isinstance(row, dict):
                continue
            key = row.get("stable_identity_key") or row.get("key_value")
            if not key:
                key = stable_key(row.get("borough"), row.get("display_location"))
            promoted[str(key)] = dict(row)
        return promoted, "phase_2e_promotion_report_promoted_rows"

    promoted_stable_keys = promotion_report.get("promoted_stable_keys")
    if isinstance(promoted_stable_keys, list):
        promoted = {}
        for key in promoted_stable_keys:
            cache_row = location_entries.get(str(key))
            if isinstance(cache_row, dict):
                promoted[str(key)] = cache_row
        return promoted, "phase_2e_promotion_report_keys_plus_location_cache_entries"

    return {}, "none"


def build_failure_report(message: str, **extra: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "blocking_issues": [message],
        "conflict_count": int(extra.get("conflict_count", 0) or 0),
        "dry_run_report": str(DRY_RUN_REPORT_PATH.relative_to(ROOT)),
        "generated_at_utc": utc_now(),
        "input_location_cache": str(LOCATION_CACHE_PATH.relative_to(ROOT)),
        "input_promotion_report": str(PROMOTION_REPORT_PATH.relative_to(ROOT)),
        "input_staged_feed": str(STAGED_FEED_PATH.relative_to(ROOT)),
        "location_cache_modified": False,
        "next_required_step": "Inspect this report, fix only the staged-feed integration workflow/script, then rerun GPS Staged Feed Integration Update. Do not publish to the public map and do not run Phase 3A.",
        "phase": "gps_staged_feed_integration_update",
        "phase_3a_run": False,
        "promoted_cache_key_count": int(extra.get("promoted_cache_key_count", 0) or 0),
        "public_map_modified": False,
        "qa_pass": False,
        "skipped_count": int(extra.get("skipped_count", EXPECTED_UPDATED_STAGED_EVENTS) or 0),
        "staged_feed_modified": False,
        "unmatched_promoted_cache_key_count": int(extra.get("unmatched_promoted_cache_key_count", 0) or 0),
        "unmatched_promoted_cache_keys": extra.get("unmatched_promoted_cache_keys", []),
        "update_performed": False,
        "updated_staged_event_count": int(extra.get("updated_staged_event_count", 0) or 0),
        "validated_conditions": {
            "conflict_count_is_0": int(extra.get("conflict_count", 0) or 0) == 0,
            "location_cache_modified_false": True,
            "phase_3a_run_false": True,
            "promoted_cache_key_count_is_25": int(extra.get("promoted_cache_key_count", 0) or 0) == EXPECTED_PROMOTED_CACHE_KEYS,
            "public_map_modified_false": True,
            "qa_pass_true": False,
            "skipped_count_is_0": int(extra.get("skipped_count", EXPECTED_UPDATED_STAGED_EVENTS) or 0) == 0,
            "staged_feed_modified_true": False,
            "unmatched_promoted_cache_key_count_is_0": int(extra.get("unmatched_promoted_cache_key_count", 0) or 0) == 0,
            "update_performed_true": False,
            "updated_staged_event_count_is_430": int(extra.get("updated_staged_event_count", 0) or 0) == EXPECTED_UPDATED_STAGED_EVENTS,
        },
    }
    report.update({k: v for k, v in extra.items() if k not in report})
    return report


def main() -> int:
    try:
        location_cache_payload = load_json(LOCATION_CACHE_PATH, {})
        promotion_report = load_json(PROMOTION_REPORT_PATH, {})
        dry_run = load_json(DRY_RUN_REPORT_PATH, {})
        staged_payload = load_json(STAGED_FEED_PATH, {})

        if not isinstance(location_cache_payload, dict):
            save_json(UPDATE_REPORT_PATH, build_failure_report("location_cache.json must be an object"))
            return 1
        if not isinstance(promotion_report, dict) or promotion_report.get("qa_pass") is not True:
            save_json(UPDATE_REPORT_PATH, build_failure_report("Phase 2E promotion report must exist and have qa_pass true"))
            return 1
        if dry_run.get("qa_pass") is not True:
            save_json(UPDATE_REPORT_PATH, build_failure_report("Dry-run report qa_pass must be true before staged-feed integration update"))
            return 1
        if int(dry_run.get("matched_staged_event_count") or 0) != EXPECTED_UPDATED_STAGED_EVENTS:
            save_json(
                UPDATE_REPORT_PATH,
                build_failure_report(
                    "Dry-run matched_staged_event_count must be 430 before staged-feed integration update",
                    dry_run_matched_staged_event_count=int(dry_run.get("matched_staged_event_count") or 0),
                ),
            )
            return 1
        if not isinstance(staged_payload, dict) or not isinstance(staged_payload.get("events"), list):
            save_json(UPDATE_REPORT_PATH, build_failure_report("nycif_staged_live_events.json must be an object with an events list"))
            return 1

        promoted_cache, promoted_source = extract_promoted_cache(location_cache_payload, promotion_report)
        if len(promoted_cache) != EXPECTED_PROMOTED_CACHE_KEYS:
            save_json(
                UPDATE_REPORT_PATH,
                build_failure_report(
                    f"Expected 25 promoted cache keys, found {len(promoted_cache)}",
                    promoted_cache_key_count=len(promoted_cache),
                    promoted_source=promoted_source,
                ),
            )
            return 1

        alias_to_cache_key: dict[str, str] = {}
        alias_collisions: dict[str, list[str]] = defaultdict(list)
        for cache_key, cache_row in promoted_cache.items():
            for alias in cache_aliases(cache_key, cache_row):
                existing = alias_to_cache_key.get(alias)
                if existing and existing != cache_key:
                    alias_collisions[alias].extend([existing, cache_key])
                else:
                    alias_to_cache_key[alias] = cache_key

        if alias_collisions:
            save_json(
                UPDATE_REPORT_PATH,
                build_failure_report(
                    "Promoted cache aliases are not unique",
                    promoted_cache_key_count=len(promoted_cache),
                    promoted_source=promoted_source,
                    conflict_count=len(alias_collisions),
                    alias_collisions={k: sorted(set(v)) for k, v in alias_collisions.items()},
                ),
            )
            return 1

        updated_rows: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        matched_keys: set[str] = set()
        update_counts_by_cache_key: Counter[str] = Counter()
        match_mode_counts: Counter[str] = Counter()

        for row in staged_payload["events"]:
            if not isinstance(row, dict):
                continue

            exact_matches = {alias_to_cache_key[alias] for alias in event_aliases(row) if alias in alias_to_cache_key}
            component_matches = {
                cache_key
                for cache_key, cache_row in promoted_cache.items()
                if component_location_match(cache_row, row)
            }
            matched_cache_keys = sorted(exact_matches | component_matches)
            if not matched_cache_keys:
                continue

            coord_pairs = {
                (round(float(promoted_cache[key]["lat"]), 6), round(float(promoted_cache[key]["lng"]), 6))
                for key in matched_cache_keys
                if valid_nyc_lat_lng(promoted_cache[key].get("lat"), promoted_cache[key].get("lng"))
            }
            if len(coord_pairs) != 1:
                conflicts.append({
                    "display_location": row.get("display_location") or row.get("location"),
                    "matched_cache_keys": matched_cache_keys,
                    "reason": "staged_event_matched_multiple_coordinate_sets_or_invalid_coordinates",
                    "source_event_id": row.get("source_event_id"),
                })
                continue

            cache_key = matched_cache_keys[0]
            cache_row = promoted_cache[cache_key]
            lat, lng = next(iter(coord_pairs))

            row["lat"] = lat
            row["lng"] = lng
            row["stable_identity_key"] = cache_key
            row["matched_promoted_cache_keys"] = matched_cache_keys
            row["group_key"] = cache_row.get("group_key") or cache_key.removeprefix("group:")
            row["gps_integration_phase"] = "gps_staged_feed_integration_update"
            row["gps_integration_source"] = promoted_source
            row["gps_integration_updated_at_utc"] = utc_now()
            row["location_source"] = "phase_2e_promoted_location_cache"
            row["phase_2e_promotion_applied_to_staged_feed"] = True
            row["public_map_modified"] = False
            row["phase_3a_run"] = False

            for key in matched_cache_keys:
                matched_keys.add(key)
                update_counts_by_cache_key[key] += 1
            match_mode_counts["exact_alias" if exact_matches else "borough_component"] += 1
            updated_rows.append({
                "display_location": row.get("display_location") or row.get("location"),
                "lat": row.get("lat"),
                "lng": row.get("lng"),
                "matched_promoted_cache_keys": matched_cache_keys,
                "source_event_id": row.get("source_event_id"),
                "stable_identity_key": cache_key,
            })

        unmatched_promoted_cache_keys = sorted(set(promoted_cache) - matched_keys)
        updated_staged_event_count = len(updated_rows)
        skipped_count = EXPECTED_UPDATED_STAGED_EVENTS - updated_staged_event_count if updated_staged_event_count < EXPECTED_UPDATED_STAGED_EVENTS else 0
        conflict_count = len(conflicts)

        qa_pass = (
            updated_staged_event_count == EXPECTED_UPDATED_STAGED_EVENTS
            and len(promoted_cache) == EXPECTED_PROMOTED_CACHE_KEYS
            and not unmatched_promoted_cache_keys
            and skipped_count == 0
            and conflict_count == 0
        )

        report = {
            "blocking_issues": [] if qa_pass else ["Staged feed GPS integration update did not meet one or more required counts"],
            "conflict_count": conflict_count,
            "conflicts": conflicts[:50],
            "dry_run_report": str(DRY_RUN_REPORT_PATH.relative_to(ROOT)),
            "generated_at_utc": utc_now(),
            "input_location_cache": str(LOCATION_CACHE_PATH.relative_to(ROOT)),
            "input_promotion_report": str(PROMOTION_REPORT_PATH.relative_to(ROOT)),
            "input_staged_feed": str(STAGED_FEED_PATH.relative_to(ROOT)),
            "location_cache_modified": False,
            "match_mode_counts": dict(sorted(match_mode_counts.items())),
            "next_required_step": "Run staged-feed GPS integration post-update QA, then decide whether to run a public-map dry-run validation gate. Do not publish to the public map until that gate passes.",
            "phase": "gps_staged_feed_integration_update",
            "phase_3a_run": False,
            "promoted_cache_key_count": len(promoted_cache),
            "promoted_source": promoted_source,
            "public_map_modified": False,
            "qa_pass": qa_pass,
            "skipped_count": skipped_count,
            "staged_feed_modified": qa_pass,
            "unmatched_promoted_cache_key_count": len(unmatched_promoted_cache_keys),
            "unmatched_promoted_cache_keys": unmatched_promoted_cache_keys,
            "update_counts_by_cache_key": dict(sorted(update_counts_by_cache_key.items())),
            "update_performed": qa_pass,
            "updated_staged_event_count": updated_staged_event_count,
            "updated_staged_event_sample": updated_rows[:25],
            "validated_conditions": {
                "conflict_count_is_0": conflict_count == 0,
                "location_cache_modified_false": True,
                "phase_3a_run_false": True,
                "promoted_cache_key_count_is_25": len(promoted_cache) == EXPECTED_PROMOTED_CACHE_KEYS,
                "public_map_modified_false": True,
                "qa_pass_true": qa_pass,
                "skipped_count_is_0": skipped_count == 0,
                "staged_feed_modified_true": qa_pass,
                "unmatched_promoted_cache_key_count_is_0": len(unmatched_promoted_cache_keys) == 0,
                "update_performed_true": qa_pass,
                "updated_staged_event_count_is_430": updated_staged_event_count == EXPECTED_UPDATED_STAGED_EVENTS,
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
            build_failure_report(
                "Unhandled staged-feed integration runtime exception",
                exception_type=type(exc).__name__,
                exception_message=str(exc),
                traceback=traceback.format_exc(),
            ),
        )
        raise


if __name__ == "__main__":
    sys.exit(main())
