from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz, utils
except Exception:  # pragma: no cover - dependency is checked at runtime
    fuzz = None
    utils = None

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
PROMOTION_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_report.json"
DRY_RUN_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_dry_run_report.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
DIAGNOSTIC_PATH = DATA_DIR / "gps_staged_feed_integration_match_diagnostic.json"

EXPECTED_PROMOTED_CACHE_KEYS = 25
EXPECTED_STAGED_MATCHES = 430
FACILITY_TYPES = {"basketball", "softball", "soccer", "tennis", "handball", "track", "lawn", "lawns"}
SITE_FUZZ_THRESHOLD = 96.0
FACILITY_FUZZ_THRESHOLD = 92.0


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


def borough_of(row: dict[str, Any]) -> str:
    return normalize(row.get("borough") or row.get("event_borough"))


def borough_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_borough = borough_of(left)
    right_borough = borough_of(right)
    return not left_borough or not right_borough or left_borough == right_borough


def row_location(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "")


def all_locations(row: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for field in ("display_location", "location", "event_location", "address"):
        value = row.get(field)
        if value:
            text = str(value)
            key = normalize(text)
            if key and key not in seen:
                out.append(text)
                seen.add(key)
    return out


def valid_nyc_lat_lng(lat: Any, lng: Any) -> bool:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except Exception:
        return False
    return 40.0 <= lat_f <= 41.0 and -75.0 <= lng_f <= -73.0


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


def split_site_facility(part: str) -> tuple[str, str] | None:
    part = str(part or "").strip()
    if not part:
        return None
    if ":" in part:
        site_raw, facility_raw = part.split(":", 1)
        site = normalize(site_raw)
        facility = canonical_facility(facility_raw)
        if site and facility_type(facility):
            return site, facility
    text = canonical_facility(part)
    words = text.split()
    facility_idx: int | None = None
    for idx, word in enumerate(words):
        if word in FACILITY_TYPES:
            facility_idx = idx
            break
    if facility_idx is None:
        return None
    site = " ".join(words[:facility_idx]).strip()
    facility = " ".join(words[facility_idx:]).strip()
    if site and facility and facility_type(facility):
        return site, facility
    return None


def site_facility_pairs(location: Any) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for part in re.split(r"\s*,\s*", str(location or "")):
        parsed = split_site_facility(part)
        if parsed:
            pairs.add(parsed)
    return pairs


def same_site(left: str, right: str) -> tuple[bool, float]:
    if left == right:
        return True, 100.0
    if fuzz is None or utils is None:
        return False, 0.0
    score = float(fuzz.token_sort_ratio(left, right, processor=utils.default_process))
    return score >= SITE_FUZZ_THRESHOLD, score


def same_facility(left: str, right: str) -> tuple[bool, str, float]:
    if left == right:
        return True, "exact_site_facility", 100.0
    if fuzz is None or utils is None:
        return False, "", 0.0
    left_type = facility_type(left)
    right_type = facility_type(right)
    if left_type and right_type and left_type != right_type:
        return False, "", 0.0
    if left_type and not right_type:
        return False, "", 0.0
    left_numbers = facility_numbers(left)
    right_numbers = facility_numbers(right)
    if left_numbers and right_numbers and not (left_numbers & right_numbers):
        return False, "", 0.0
    score = max(
        fuzz.token_sort_ratio(left, right, processor=utils.default_process),
        fuzz.WRatio(left, right, processor=utils.default_process),
    )
    return float(score) >= FACILITY_FUZZ_THRESHOLD, "rapidfuzz_site_facility", float(score)


def promoted_rows_from_report(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    promoted: dict[str, dict[str, Any]] = {}
    rows = payload.get("promoted_rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return promoted
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("stable_identity_key") or "")
        if key:
            promoted[key] = row
    return promoted


def unwrap_location_cache(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("entries"), dict):
        return payload["entries"]
    if isinstance(payload, dict):
        return payload
    return {}


def event_cemsids(row: dict[str, Any]) -> set[str]:
    raw = row.get("source_cemsid") or row.get("cemsid") or []
    if isinstance(raw, list):
        return {str(item) for item in raw if str(item)}
    if raw:
        return {str(raw)}
    return set()


def stable_event_identity(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("source_event_id") or row.get("event_id") or row.get("id") or ""),
            normalize(row_location(row)),
            ",".join(sorted(event_cemsids(row))),
            str(row.get("date") or ""),
            str(row.get("start_date_time") or ""),
        ]
    )


def cache_entry_matches_promoted(cache_row: dict[str, Any], promoted_row: dict[str, Any]) -> bool:
    if not borough_compatible(cache_row, promoted_row):
        return False
    cache_pairs = site_facility_pairs(row_location(cache_row))
    promoted_pairs = site_facility_pairs(row_location(promoted_row))
    for promoted_site, promoted_facility in promoted_pairs:
        for cache_site, cache_facility in cache_pairs:
            site_ok, _site_score = same_site(promoted_site, cache_site)
            if not site_ok:
                continue
            facility_ok, _mode, _score = same_facility(promoted_facility, cache_facility)
            if facility_ok:
                return True
    return False


def cemsids_for_promoted_rows(location_entries: dict[str, Any], promoted: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    key_to_cemsids: dict[str, set[str]] = {key: set() for key in promoted}
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
            if cache_entry_matches_promoted(cache_row, promoted_row):
                key_to_cemsids[promoted_key].add(cemsid)
    return key_to_cemsids


def row_match(promoted_key: str, promoted_row: dict[str, Any], event_row: dict[str, Any], key_to_cemsids: dict[str, set[str]]) -> dict[str, Any] | None:
    if not borough_compatible(promoted_row, event_row):
        return None
    modes: dict[str, float] = {}
    cemsid_overlap = event_cemsids(event_row) & key_to_cemsids.get(promoted_key, set())
    if cemsid_overlap:
        modes["source_cemsid"] = 100.0

    promoted_pairs = site_facility_pairs(row_location(promoted_row))
    event_pairs: set[tuple[str, str]] = set()
    for location in all_locations(event_row):
        event_pairs.update(site_facility_pairs(location))

    for promoted_site, promoted_facility in promoted_pairs:
        for event_site, event_facility in event_pairs:
            site_ok, site_score = same_site(promoted_site, event_site)
            if not site_ok:
                continue
            facility_ok, mode, facility_score = same_facility(promoted_facility, event_facility)
            if facility_ok and mode:
                score = min(site_score, facility_score)
                modes[mode] = max(modes.get(mode, 0.0), score)

    if not modes:
        return None
    if not valid_nyc_lat_lng(promoted_row.get("lat"), promoted_row.get("lng")):
        return None
    return {
        "current_lat": event_row.get("lat"),
        "current_lng": event_row.get("lng"),
        "display_location": row_location(event_row),
        "event_borough": event_row.get("borough") or event_row.get("event_borough"),
        "match_modes": dict(sorted(modes.items())),
        "promoted_cache_key": promoted_key,
        "promoted_display_location": promoted_row.get("display_location"),
        "promoted_lat": promoted_row.get("lat"),
        "promoted_lng": promoted_row.get("lng"),
        "source_cemsid": sorted(event_cemsids(event_row)),
        "source_event_id": event_row.get("source_event_id") or event_row.get("event_id") or event_row.get("id"),
        "stable_event_identity": stable_event_identity(event_row),
        "title": event_row.get("title") or event_row.get("event_name"),
    }


def rows_from_staged(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def main() -> int:
    if fuzz is None or utils is None:
        report = {
            "blocking_issues": ["RapidFuzz dependency is not installed"],
            "generated_at_utc": utc_now(),
            "location_cache_modified": False,
            "phase": "gps_staged_feed_integration_match_diagnostic",
            "phase_3a_run": False,
            "public_map_modified": False,
            "qa_pass": False,
            "staged_feed_modified": False,
        }
        save_json(DIAGNOSTIC_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    location_cache = load_json(LOCATION_CACHE_PATH, {})
    promotion_report = load_json(PROMOTION_REPORT_PATH, {})
    dry_run_report = load_json(DRY_RUN_REPORT_PATH, {})
    staged_payload = load_json(STAGED_FEED_PATH, {})

    promoted = promoted_rows_from_report(promotion_report)
    staged_rows = rows_from_staged(staged_payload)
    key_to_cemsids = cemsids_for_promoted_rows(unwrap_location_cache(location_cache), promoted)

    candidates_by_key: dict[str, list[dict[str, Any]]] = {key: [] for key in promoted}
    event_to_promoted_keys: dict[str, set[str]] = defaultdict(set)

    for promoted_key, promoted_row in promoted.items():
        seen_identities: set[str] = set()
        for event_row in staged_rows:
            match = row_match(promoted_key, promoted_row, event_row, key_to_cemsids)
            if match is None:
                continue
            identity = match["stable_event_identity"]
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            candidates_by_key[promoted_key].append(match)
            event_to_promoted_keys[identity].add(promoted_key)

    multi_key_conflicts: list[dict[str, Any]] = []
    for identity, keys in event_to_promoted_keys.items():
        if len(keys) <= 1:
            continue
        coords = {
            (
                round(float(promoted[key]["lat"]), 6),
                round(float(promoted[key]["lng"]), 6),
            )
            for key in keys
            if valid_nyc_lat_lng(promoted[key].get("lat"), promoted[key].get("lng"))
        }
        if len(coords) > 1:
            multi_key_conflicts.append({
                "matched_promoted_cache_keys": sorted(keys),
                "reason": "candidate_event_matches_multiple_promoted_coordinate_sets",
                "stable_event_identity": identity,
            })

    conflict_identities = {item["stable_event_identity"] for item in multi_key_conflicts}
    selected_rows: list[dict[str, Any]] = []
    for promoted_key in sorted(candidates_by_key):
        for row in candidates_by_key[promoted_key]:
            if row["stable_event_identity"] in conflict_identities:
                continue
            selected_rows.append(row)

    selected_identity_count = len({row["stable_event_identity"] for row in selected_rows})
    selected_count = len(selected_rows)
    all_keys_have_candidates = all(bool(candidates_by_key.get(key)) for key in promoted)
    expected_count = int(dry_run_report.get("matched_staged_event_count") or EXPECTED_STAGED_MATCHES)
    stable_identity_ready = (
        selected_count == expected_count
        and selected_identity_count == expected_count
        and len(promoted) == EXPECTED_PROMOTED_CACHE_KEYS
        and all_keys_have_candidates
        and not multi_key_conflicts
    )

    report = {
        "blocking_issues": [] if stable_identity_ready else ["Diagnostic candidate identities do not yet equal the dry-run 430-row contract"],
        "candidate_count_by_promoted_cache_key": {key: len(rows) for key, rows in sorted(candidates_by_key.items())},
        "candidate_match_mode_counts": dict(Counter(mode for rows in candidates_by_key.values() for row in rows for mode in row["match_modes"])),
        "diagnostic_scope": "row_identity_capture_only_no_staged_feed_write_no_public_map_no_phase_3a",
        "dry_run_expected_matched_staged_event_count": expected_count,
        "generated_at_utc": utc_now(),
        "input_dry_run_report": str(DRY_RUN_REPORT_PATH.relative_to(ROOT)),
        "input_location_cache": str(LOCATION_CACHE_PATH.relative_to(ROOT)),
        "input_promotion_report": str(PROMOTION_REPORT_PATH.relative_to(ROOT)),
        "input_staged_feed": str(STAGED_FEED_PATH.relative_to(ROOT)),
        "location_cache_modified": False,
        "multi_key_conflict_count": len(multi_key_conflicts),
        "multi_key_conflicts_sample": multi_key_conflicts[:50],
        "phase": "gps_staged_feed_integration_match_diagnostic",
        "phase_3a_run": False,
        "promoted_cache_key_count": len(promoted),
        "promoted_source_cemsid_counts": {key: len(ids) for key, ids in sorted(key_to_cemsids.items())},
        "public_map_modified": False,
        "qa_pass": stable_identity_ready,
        "selected_candidate_count": selected_count,
        "selected_stable_event_identity_count": selected_identity_count,
        "selected_stable_identity_rows": selected_rows,
        "staged_event_count": len(staged_rows),
        "staged_feed_modified": False,
        "stable_identity_ready_for_update": stable_identity_ready,
        "unmatched_promoted_cache_key_count": sum(1 for key in promoted if not candidates_by_key.get(key)),
        "unmatched_promoted_cache_keys": sorted(key for key in promoted if not candidates_by_key.get(key)),
        "validated_conditions": {
            "all_promoted_keys_have_candidates": all_keys_have_candidates,
            "candidate_count_matches_dry_run_430": selected_count == expected_count,
            "location_cache_modified_false": True,
            "no_multi_key_conflicts": not multi_key_conflicts,
            "phase_3a_run_false": True,
            "promoted_cache_key_count_is_25": len(promoted) == EXPECTED_PROMOTED_CACHE_KEYS,
            "public_map_modified_false": True,
            "selected_identities_are_unique": selected_identity_count == selected_count,
            "staged_feed_modified_false": True,
        },
    }

    save_json(DIAGNOSTIC_PATH, report)
    print(json.dumps({k: v for k, v in report.items() if k != "selected_stable_identity_rows"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
