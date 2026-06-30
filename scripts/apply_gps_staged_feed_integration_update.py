from __future__ import annotations

import json
import re
import sys
import traceback
from collections import Counter
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


def normalize(value: Any) -> str:
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_tokens(value: Any) -> list[str]:
    return normalize(value).split()


def stable_key(borough: Any, location: Any) -> str:
    return f"group:{normalize(borough)}|{normalize(location)}"


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


def borough_of(row: dict[str, Any]) -> str:
    return normalize(row.get("borough") or row.get("event_borough"))


def event_location_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("display_location", "location", "event_location"):
        value = row.get(field)
        if value:
            parts.append(str(value))
    return " | ".join(parts)


def row_location(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "")


def site_name(location: Any) -> str:
    text = str(location or "")
    # Prefer the named place before the first facility delimiter.
    if ":" in text:
        text = text.split(":", 1)[0]
    return normalize(text)


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
            value_s = str(value)
            aliases.add(value_s)
            if not value_s.startswith("group:"):
                aliases.add(f"group:{value_s}")

    borough = row.get("borough") or row.get("event_borough")
    if borough:
        for field in ("display_location", "location", "event_location"):
            value = row.get(field)
            if value:
                aliases.add(stable_key(borough, value))
    return aliases


def cache_aliases(key: str, row: dict[str, Any]) -> set[str]:
    aliases = {key}
    for field in ("stable_identity_key", "group_key", "cache_key", "gps_cache_key", "key_value"):
        value = row.get(field)
        if value:
            value_s = str(value)
            aliases.add(value_s)
            if not value_s.startswith("group:"):
                aliases.add(f"group:{value_s}")

    borough = row.get("borough") or row.get("event_borough")
    location = row_location(row)
    if borough and location:
        aliases.add(stable_key(borough, location))
    return aliases


def extract_promoted_rows(location_cache_payload: Any, promotion_report: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    # Prefer the original stable Phase 2E approval/promotion report. The live location cache can be
    # rebuilt and may not preserve phase_2e_promotion_performed flags.
    promoted_rows = promotion_report.get("promoted_rows")
    if isinstance(promoted_rows, list):
        promoted: dict[str, dict[str, Any]] = {}
        for row in promoted_rows:
            if not isinstance(row, dict):
                continue
            key = row.get("stable_identity_key") or row.get("key_value") or stable_key(row.get("borough"), row.get("display_location"))
            promoted[str(key)] = dict(row)
        return promoted, "phase_2e_promotion_report_promoted_rows"

    entries = location_cache_payload.get("entries", location_cache_payload) if isinstance(location_cache_payload, dict) else {}
    flagged = {
        key: value
        for key, value in entries.items()
        if isinstance(value, dict) and value.get("phase_2e_promotion_performed") is True
    }
    if flagged:
        return flagged, "location_cache_phase_2e_flags"
    return {}, "none"


def promoted_match(cache_key: str, cache_row: dict[str, Any], event_row: dict[str, Any], alias_to_key: dict[str, str]) -> tuple[bool, str | None]:
    if cache_key in {alias_to_key[alias] for alias in event_aliases(event_row) if alias in alias_to_key}:
        return True, "exact_alias"

    if borough_of(cache_row) != borough_of(event_row):
        return False, None

    cache_location = row_location(cache_row)
    event_text = event_location_text(event_row)
    cache_norm = normalize(cache_location)
    event_norm = normalize(event_text)
    if not cache_norm or not event_norm:
        return False, None

    if cache_norm in event_norm or event_norm in cache_norm:
        return True, "full_location_component"

    cache_site = site_name(cache_location)
    if cache_site and len(cache_site.split()) >= 2 and cache_site in event_norm:
        return True, "site_component"

    # Last safe fallback: all promoted-location tokens are present in the staged location text.
    cache_token_list = norm_tokens(cache_location)
    event_token_set = set(norm_tokens(event_text))
    if cache_token_list and all(token in event_token_set for token in cache_token_list):
        return True, "token_component"

    return False, None


def failure_report(message: str, **extra: Any) -> dict[str, Any]:
    report = {
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
    }
    report.update(extra)
    report["validated_conditions"] = {
        "conflict_count_is_0": report["conflict_count"] == 0,
        "location_cache_modified_false": True,
        "phase_3a_run_false": True,
        "promoted_cache_key_count_is_25": report["promoted_cache_key_count"] == EXPECTED_PROMOTED_CACHE_KEYS,
        "public_map_modified_false": True,
        "qa_pass_true": False,
        "skipped_count_is_0": report["skipped_count"] == 0,
        "staged_feed_modified_true": False,
        "unmatched_promoted_cache_key_count_is_0": report["unmatched_promoted_cache_key_count"] == 0,
        "update_performed_true": False,
        "updated_staged_event_count_is_430": report["updated_staged_event_count"] == EXPECTED_UPDATED_STAGED_EVENTS,
    }
    return report


def main() -> int:
    try:
        location_cache = load_json(LOCATION_CACHE_PATH, {})
        promotion_report = load_json(PROMOTION_REPORT_PATH, {})
        dry_run = load_json(DRY_RUN_REPORT_PATH, {})
        staged_payload = load_json(STAGED_FEED_PATH, {})

        if not isinstance(promotion_report, dict) or promotion_report.get("qa_pass") is not True:
            save_json(UPDATE_REPORT_PATH, failure_report("Phase 2E promotion report must exist and have qa_pass true"))
            return 1
        if dry_run.get("qa_pass") is not True or int(dry_run.get("matched_staged_event_count") or 0) != EXPECTED_UPDATED_STAGED_EVENTS:
            save_json(UPDATE_REPORT_PATH, failure_report("Dry-run report must have qa_pass true and matched_staged_event_count 430"))
            return 1
        if not isinstance(staged_payload, dict) or not isinstance(staged_payload.get("events"), list):
            save_json(UPDATE_REPORT_PATH, failure_report("nycif_staged_live_events.json must be an object with an events list"))
            return 1

        promoted, promoted_source = extract_promoted_rows(location_cache, promotion_report)
        if len(promoted) != EXPECTED_PROMOTED_CACHE_KEYS:
            save_json(UPDATE_REPORT_PATH, failure_report(f"Expected 25 promoted cache keys, found {len(promoted)}", promoted_cache_key_count=len(promoted)))
            return 1

        alias_to_key: dict[str, str] = {}
        for key, row in promoted.items():
            for alias in cache_aliases(key, row):
                alias_to_key.setdefault(alias, key)

        updated_rows: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        matched_keys: set[str] = set()
        update_counts_by_key: Counter[str] = Counter()
        match_mode_counts: Counter[str] = Counter()

        for event_row in staged_payload["events"]:
            if not isinstance(event_row, dict):
                continue

            matched: dict[str, str] = {}
            for key, cache_row in promoted.items():
                is_match, mode = promoted_match(key, cache_row, event_row, alias_to_key)
                if is_match and mode:
                    matched[key] = mode

            if not matched:
                continue

            coord_pairs = set()
            for key in matched:
                cache_row = promoted[key]
                if valid_nyc_lat_lng(cache_row.get("lat"), cache_row.get("lng")):
                    coord_pairs.add((round(float(cache_row["lat"]), 6), round(float(cache_row["lng"]), 6)))

            if len(coord_pairs) != 1:
                conflicts.append({
                    "display_location": row_location(event_row),
                    "matched_promoted_cache_keys": sorted(matched),
                    "reason": "matched_promoted_keys_have_conflicting_or_invalid_coordinates",
                    "source_event_id": event_row.get("source_event_id"),
                })
                continue

            lat, lng = next(iter(coord_pairs))
            primary_key = sorted(matched)[0]
            primary_row = promoted[primary_key]
            event_row["lat"] = lat
            event_row["lng"] = lng
            event_row["stable_identity_key"] = primary_key
            event_row["matched_promoted_cache_keys"] = sorted(matched)
            event_row["group_key"] = primary_row.get("group_key") or primary_key.removeprefix("group:")
            event_row["gps_integration_phase"] = "gps_staged_feed_integration_update"
            event_row["gps_integration_source"] = promoted_source
            event_row["gps_integration_updated_at_utc"] = utc_now()
            event_row["location_source"] = "phase_2e_promoted_location_cache"
            event_row["phase_2e_promotion_applied_to_staged_feed"] = True
            event_row["public_map_modified"] = False
            event_row["phase_3a_run"] = False

            for key, mode in matched.items():
                matched_keys.add(key)
                update_counts_by_key[key] += 1
                match_mode_counts[mode] += 1
            updated_rows.append({
                "display_location": row_location(event_row),
                "lat": lat,
                "lng": lng,
                "matched_promoted_cache_keys": sorted(matched),
                "source_event_id": event_row.get("source_event_id"),
                "stable_identity_key": primary_key,
            })

        updated_count = len(updated_rows)
        unmatched = sorted(set(promoted) - matched_keys)
        skipped = max(EXPECTED_UPDATED_STAGED_EVENTS - updated_count, 0)
        conflict_count = len(conflicts)
        qa_pass = (
            updated_count == EXPECTED_UPDATED_STAGED_EVENTS
            and len(promoted) == EXPECTED_PROMOTED_CACHE_KEYS
            and not unmatched
            and skipped == 0
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
            "promoted_cache_key_count": len(promoted),
            "promoted_source": promoted_source,
            "public_map_modified": False,
            "qa_pass": qa_pass,
            "skipped_count": skipped,
            "staged_feed_modified": qa_pass,
            "unmatched_promoted_cache_key_count": len(unmatched),
            "unmatched_promoted_cache_keys": unmatched,
            "update_counts_by_cache_key": dict(sorted(update_counts_by_key.items())),
            "update_performed": qa_pass,
            "updated_staged_event_count": updated_count,
            "updated_staged_event_sample": updated_rows[:25],
            "validated_conditions": {
                "conflict_count_is_0": conflict_count == 0,
                "location_cache_modified_false": True,
                "phase_3a_run_false": True,
                "promoted_cache_key_count_is_25": len(promoted) == EXPECTED_PROMOTED_CACHE_KEYS,
                "public_map_modified_false": True,
                "qa_pass_true": qa_pass,
                "skipped_count_is_0": skipped == 0,
                "staged_feed_modified_true": qa_pass,
                "unmatched_promoted_cache_key_count_is_0": len(unmatched) == 0,
                "update_performed_true": qa_pass,
                "updated_staged_event_count_is_430": updated_count == EXPECTED_UPDATED_STAGED_EVENTS,
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
