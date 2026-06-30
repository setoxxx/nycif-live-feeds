from __future__ import annotations

import json
import re
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz, utils
except Exception:  # pragma: no cover - reported by runtime QA below
    fuzz = None
    utils = None

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
PROMOTION_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_report.json"
DRY_RUN_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_dry_run_report.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
UPDATE_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_update_report.json"

EXPECTED_PROMOTED_CACHE_KEYS = 25
EXPECTED_UPDATED_STAGED_EVENTS = 430
FACILITY_TYPES = {"basketball", "softball", "soccer", "tennis", "handball", "track", "lawn", "lawns"}
RAPIDFUZZ_THRESHOLD = 92.0


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


def canonical_facility(value: Any) -> str:
    text = normalize(value)
    text = re.sub(r"\b(\d+)[a-z]\b", r"\1", text)
    return text


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


def row_location(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "")


def all_event_locations(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for field in ("display_location", "location", "event_location"):
        value = row.get(field)
        if value:
            text = str(value)
            key = normalize(text)
            if key and key not in seen:
                values.append(text)
                seen.add(key)
    return values


def unwrap_location_cache(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return payload["entries"]
    if isinstance(payload, dict):
        return payload
    return {}


def promoted_rows_from_report(promotion_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    promoted_rows = promotion_report.get("promoted_rows")
    promoted: dict[str, dict[str, Any]] = {}
    if isinstance(promoted_rows, list):
        for row in promoted_rows:
            if not isinstance(row, dict):
                continue
            key = row.get("stable_identity_key") or stable_key(row.get("borough"), row.get("display_location"))
            promoted[str(key)] = dict(row)
    return promoted


def location_components(location: Any) -> set[str]:
    text = str(location or "")
    components: set[str] = set()
    for part in re.split(r"\s*,\s*", text):
        part = part.strip()
        if not part:
            continue
        norm_full = canonical_facility(part)
        if ":" in part:
            site, facility = part.split(":", 1)
            site_norm = normalize(site)
            facility_norm = canonical_facility(facility)
            if site_norm and facility_norm:
                components.add(f"{site_norm} {facility_norm}")
            if facility_norm:
                components.add(facility_norm)
        if ":" in part or any(word in norm_full.split() for word in FACILITY_TYPES | {"field", "area"}):
            components.add(norm_full)
    return {component for component in components if component}


def facility_type(component: str) -> str | None:
    words = set(component.split())
    for kind in FACILITY_TYPES:
        if kind in words:
            return "lawn" if kind == "lawns" else kind
    return None


def facility_numbers(component: str) -> set[int]:
    words = component.split()
    numbers: set[int] = set()
    for idx, word in enumerate(words):
        if word not in FACILITY_TYPES:
            continue
        for next_word in words[idx + 1 : idx + 4]:
            if next_word.isdigit():
                numbers.add(int(next_word))
    return numbers


def guarded_fuzzy_component_match(promoted_component: str, event_component: str) -> tuple[bool, float]:
    if fuzz is None or utils is None:
        return False, 0.0
    promoted_kind = facility_type(promoted_component)
    event_kind = facility_type(event_component)
    if promoted_kind and event_kind and promoted_kind != event_kind:
        return False, 0.0
    if promoted_kind and not event_kind:
        return False, 0.0
    promoted_numbers = facility_numbers(promoted_component)
    event_numbers = facility_numbers(event_component)
    if promoted_numbers and event_numbers and not (promoted_numbers & event_numbers):
        return False, 0.0
    score = max(
        fuzz.token_sort_ratio(promoted_component, event_component, processor=utils.default_process),
        fuzz.WRatio(promoted_component, event_component, processor=utils.default_process),
    )
    return score >= RAPIDFUZZ_THRESHOLD, float(score)


def exact_or_fuzzy_facility_match(promoted_row: dict[str, Any], event_row: dict[str, Any]) -> tuple[bool, str | None, float]:
    if borough_of(promoted_row) != borough_of(event_row):
        return False, None, 0.0
    promoted_components = location_components(row_location(promoted_row))
    if not promoted_components:
        return False, None, 0.0
    event_components: set[str] = set()
    for location in all_event_locations(event_row):
        event_components.update(location_components(location))
    if not event_components:
        return False, None, 0.0
    if promoted_components & event_components:
        return True, "exact_facility", 100.0
    best_score = 0.0
    for promoted_component in promoted_components:
        for event_component in event_components:
            matched, score = guarded_fuzzy_component_match(promoted_component, event_component)
            best_score = max(best_score, score)
            if matched:
                return True, "rapidfuzz_facility", score
    return False, None, best_score


def cache_entry_matches_promoted(cache_row: dict[str, Any], promoted_row: dict[str, Any], promoted_key: str) -> bool:
    if borough_of(cache_row) != borough_of(promoted_row):
        return False
    cache_location = row_location(cache_row)
    promoted_location = row_location(promoted_row)
    cache_components = location_components(cache_location)
    promoted_components = location_components(promoted_location)
    if cache_components and promoted_components and (cache_components & promoted_components):
        return True
    if stable_key(cache_row.get("borough"), cache_location) == promoted_key:
        return True
    return False


def cemsids_for_promoted_rows(location_entries: dict[str, Any], promoted: dict[str, dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, list[dict[str, Any]]]]:
    key_to_cemsids: dict[str, set[str]] = {key: set() for key in promoted}
    key_to_entries: dict[str, list[dict[str, Any]]] = {key: [] for key in promoted}

    for entry_key, cache_row in location_entries.items():
        if not isinstance(cache_row, dict):
            continue
        key_type = str(cache_row.get("key_type") or "")
        key_value = str(cache_row.get("key_value") or entry_key)
        if key_type != "cemsid" and not key_value.startswith("cemsid:"):
            continue
        cemsid = key_value.split(":")[-1]
        if not cemsid:
            continue
        for promoted_key, promoted_row in promoted.items():
            if cache_entry_matches_promoted(cache_row, promoted_row, promoted_key):
                key_to_cemsids[promoted_key].add(cemsid)
                key_to_entries[promoted_key].append({
                    "cache_key": entry_key,
                    "cemsid": cemsid,
                    "display_location": cache_row.get("display_location"),
                    "lat": cache_row.get("lat"),
                    "lng": cache_row.get("lng"),
                })

    return key_to_cemsids, key_to_entries


def event_cemsids(event_row: dict[str, Any]) -> set[str]:
    raw = event_row.get("source_cemsid") or event_row.get("cemsid") or []
    if isinstance(raw, list):
        return {str(item) for item in raw if str(item)}
    if raw:
        return {str(raw)}
    return set()


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
        if fuzz is None or utils is None:
            save_json(UPDATE_REPORT_PATH, failure_report("RapidFuzz dependency is not installed; workflow must install rapidfuzz==3.*"))
            return 1

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

        promoted = promoted_rows_from_report(promotion_report)
        if len(promoted) != EXPECTED_PROMOTED_CACHE_KEYS:
            save_json(UPDATE_REPORT_PATH, failure_report(f"Expected 25 promoted rows, found {len(promoted)}", promoted_cache_key_count=len(promoted)))
            return 1

        location_entries = unwrap_location_cache(location_cache)
        key_to_cemsids, _ = cemsids_for_promoted_rows(location_entries, promoted)
        cemsid_to_keys: dict[str, set[str]] = defaultdict(set)
        for key, ids in key_to_cemsids.items():
            for cemsid in ids:
                cemsid_to_keys[cemsid].add(key)

        updated_rows: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        matched_keys: set[str] = set()
        update_counts_by_key: Counter[str] = Counter()
        match_mode_counts: Counter[str] = Counter()
        fuzzy_scores: list[float] = []

        for event_row in staged_payload["events"]:
            if not isinstance(event_row, dict):
                continue
            matched_by_key: dict[str, str] = {}
            matched_scores: dict[str, float] = {}

            for cemsid in event_cemsids(event_row):
                for key in cemsid_to_keys.get(cemsid, set()):
                    matched_by_key[key] = "source_cemsid"
                    matched_scores[key] = 100.0

            for key, promoted_row in promoted.items():
                matched, mode, score = exact_or_fuzzy_facility_match(promoted_row, event_row)
                if matched and mode:
                    matched_by_key.setdefault(key, mode)
                    matched_scores[key] = max(matched_scores.get(key, 0.0), score)
                    if mode == "rapidfuzz_facility":
                        fuzzy_scores.append(score)

            if not matched_by_key:
                continue

            coord_pairs = set()
            for key in matched_by_key:
                promoted_row = promoted[key]
                if valid_nyc_lat_lng(promoted_row.get("lat"), promoted_row.get("lng")):
                    coord_pairs.add((round(float(promoted_row["lat"]), 6), round(float(promoted_row["lng"]), 6)))
            if len(coord_pairs) != 1:
                conflicts.append({
                    "display_location": row_location(event_row),
                    "matched_promoted_cache_keys": sorted(matched_by_key),
                    "reason": "matched_promoted_keys_have_conflicting_or_invalid_coordinates",
                    "source_cemsid": sorted(event_cemsids(event_row)),
                    "source_event_id": event_row.get("source_event_id"),
                })
                continue

            lat, lng = next(iter(coord_pairs))
            primary_key = sorted(matched_by_key)[0]
            primary_row = promoted[primary_key]
            event_row["lat"] = lat
            event_row["lng"] = lng
            event_row["stable_identity_key"] = primary_key
            event_row["matched_promoted_cache_keys"] = sorted(matched_by_key)
            event_row["group_key"] = primary_row.get("group_key") or primary_key.removeprefix("group:")
            event_row["gps_integration_phase"] = "gps_staged_feed_integration_update"
            event_row["gps_integration_source"] = "source_cemsid_exact_or_rapidfuzz_facility"
            event_row["gps_integration_updated_at_utc"] = utc_now()
            event_row["location_source"] = "phase_2e_promoted_location_cache"
            event_row["phase_2e_promotion_applied_to_staged_feed"] = True
            event_row["public_map_modified"] = False
            event_row["phase_3a_run"] = False

            for key, mode in matched_by_key.items():
                matched_keys.add(key)
                update_counts_by_key[key] += 1
                match_mode_counts[mode] += 1
            updated_rows.append({
                "display_location": row_location(event_row),
                "lat": lat,
                "lng": lng,
                "matched_promoted_cache_keys": sorted(matched_by_key),
                "match_modes": dict(sorted(matched_by_key.items())),
                "match_scores": {key: round(score, 2) for key, score in sorted(matched_scores.items())},
                "source_cemsid": sorted(event_cemsids(event_row)),
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
            "promoted_source": "phase_2e_promotion_report_promoted_rows",
            "promoted_source_cemsid_counts": {key: len(ids) for key, ids in sorted(key_to_cemsids.items())},
            "promoted_source_cemsid_sample": {key: sorted(ids)[:10] for key, ids in sorted(key_to_cemsids.items())},
            "public_map_modified": False,
            "qa_pass": qa_pass,
            "rapidfuzz_enabled": True,
            "rapidfuzz_threshold": RAPIDFUZZ_THRESHOLD,
            "rapidfuzz_score_sample": [round(score, 2) for score in sorted(fuzzy_scores, reverse=True)[:25]],
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
