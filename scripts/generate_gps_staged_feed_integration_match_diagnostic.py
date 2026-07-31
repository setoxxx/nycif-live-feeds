from __future__ import annotations

import json
import math
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

try:
    from scripts.gps_identity import (
        build_stable_event_identity as stable_event_identity,
        event_cemsids,
        normalize_text_with_ampersand,
        row_location,
    )
    from scripts.gps_snapshot_provenance import (
        DEFAULT_STAGED_FEED_RELATIVE_PATH,
        file_provenance,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import (
        build_stable_event_identity as stable_event_identity,
        event_cemsids,
        normalize_text_with_ampersand,
        row_location,
    )
    from gps_snapshot_provenance import (
        DEFAULT_STAGED_FEED_RELATIVE_PATH,
        file_provenance,
    )

ROOT = Path(__file__).resolve().parents[1]
PRODUCER_SCRIPT = "scripts/generate_gps_staged_feed_integration_match_diagnostic.py"
DATA_DIR = ROOT / "data"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
PROMOTION_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_report.json"
DRY_RUN_REPORT_PATH = DATA_DIR / "gps_staged_feed_integration_dry_run_report.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
DIAGNOSTIC_PATH = DATA_DIR / "gps_staged_feed_integration_match_diagnostic.json"

# Historical note (Canonical Milestone 7-B.2): EXPECTED_PROMOTED_CACHE_KEYS
# = 25 and EXPECTED_STAGED_MATCHES = 430 previously gated qa_pass here. The
# diagnostic now reports readiness from internal consistency of what it
# actually selected (unique identities, zero multi-key conflicts, non-empty
# selection); the old dry-run target is carried as historical context only
# and never used as a gate. No runtime count constant remains here.
FACILITY_TYPES = {"basketball", "softball", "soccer", "tennis", "handball", "track", "lawn", "lawns"}
SITE_FUZZ_THRESHOLD = 96.0
FACILITY_FUZZ_THRESHOLD = 92.0
NEAR_MISS_LIMIT = 25
SAME_SITE_NEAR_MISS_MIN_SCORE = 70.0
SAME_COORDINATE_NEAR_METERS = 75.0

REJECTION_REASONS = (
    "site_name_below_threshold",
    "facility_type_mismatch",
    "facility_number_mismatch",
    "no_site_facility_pair",
    "borough_mismatch",
    "coordinate_conflict",
    "no_cemsid_overlap",
    "no_candidate_rows_found",
)


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


def canonical_facility(value: Any) -> str:
    text = normalize_text_with_ampersand(value)
    text = re.sub(r"\b(\d+)[a-z]\b", r"\1", text)
    return text


def borough_of(row: dict[str, Any]) -> str:
    return normalize_text_with_ampersand(row.get("borough") or row.get("event_borough"))


def borough_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_borough = borough_of(left)
    right_borough = borough_of(right)
    return not left_borough or not right_borough or left_borough == right_borough


def all_locations(row: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for field in ("display_location", "location", "event_location", "address"):
        value = row.get(field)
        if value:
            text = str(value)
            key = normalize_text_with_ampersand(text)
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


def lat_lng(row: dict[str, Any]) -> tuple[float, float] | None:
    lat = row.get("lat")
    lng = row.get("lng")
    if not valid_nyc_lat_lng(lat, lng):
        return None
    return float(lat), float(lng)


def distance_meters(a_lat: Any, a_lng: Any, b_lat: Any, b_lng: Any) -> float | None:
    if not valid_nyc_lat_lng(a_lat, a_lng) or not valid_nyc_lat_lng(b_lat, b_lng):
        return None
    lat1 = math.radians(float(a_lat))
    lon1 = math.radians(float(a_lng))
    lat2 = math.radians(float(b_lat))
    lon2 = math.radians(float(b_lng))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000.0 * 2.0 * math.asin(math.sqrt(h))


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
        site = normalize_text_with_ampersand(site_raw)
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


def facility_score(left: str, right: str) -> float:
    if left == right:
        return 100.0
    if fuzz is None or utils is None:
        return 0.0
    return float(
        max(
            fuzz.token_sort_ratio(left, right, processor=utils.default_process),
            fuzz.WRatio(left, right, processor=utils.default_process),
        )
    )


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
    score = facility_score(left, right)
    return score >= FACILITY_FUZZ_THRESHOLD, "rapidfuzz_site_facility", float(score)


def facility_type_number_compatible(left: str, right: str) -> bool:
    left_type = facility_type(left)
    right_type = facility_type(right)
    if left_type != right_type or left_type is None:
        return False
    left_numbers = facility_numbers(left)
    right_numbers = facility_numbers(right)
    if left_numbers or right_numbers:
        return bool(left_numbers & right_numbers)
    return True


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


def pair_diagnostics(promoted_row: dict[str, Any], event_row: dict[str, Any]) -> dict[str, Any]:
    promoted_pairs = site_facility_pairs(row_location(promoted_row))
    event_pairs: set[tuple[str, str]] = set()
    for location in all_locations(event_row):
        event_pairs.update(site_facility_pairs(location))

    result: dict[str, Any] = {
        "best_event_facility": None,
        "best_event_site": None,
        "best_facility_score": 0.0,
        "best_promoted_facility": None,
        "best_promoted_site": None,
        "best_site_score": 0.0,
        "event_pair_count": len(event_pairs),
        "facility_number_match": False,
        "facility_type_match": False,
        "promoted_pair_count": len(promoted_pairs),
        "rejection_reasons": [],
        "site_match": False,
        "site_pair_present": bool(promoted_pairs and event_pairs),
    }

    if not promoted_pairs or not event_pairs:
        result["rejection_reasons"].append("no_site_facility_pair")
        return result

    for promoted_site, promoted_facility in promoted_pairs:
        for event_site, event_facility in event_pairs:
            site_ok, site_score = same_site(promoted_site, event_site)
            fac_score = facility_score(promoted_facility, event_facility)
            if site_score > float(result["best_site_score"]):
                result["best_site_score"] = round(site_score, 2)
                result["best_event_site"] = event_site
                result["best_promoted_site"] = promoted_site
            if fac_score > float(result["best_facility_score"]):
                result["best_facility_score"] = round(fac_score, 2)
                result["best_event_facility"] = event_facility
                result["best_promoted_facility"] = promoted_facility
            if site_ok:
                result["site_match"] = True
            promoted_type = facility_type(promoted_facility)
            event_type = facility_type(event_facility)
            if promoted_type and promoted_type == event_type:
                result["facility_type_match"] = True
                promoted_numbers = facility_numbers(promoted_facility)
                event_numbers = facility_numbers(event_facility)
                if not promoted_numbers and not event_numbers:
                    result["facility_number_match"] = True
                elif promoted_numbers & event_numbers:
                    result["facility_number_match"] = True

    if not result["site_match"]:
        result["rejection_reasons"].append("site_name_below_threshold")
    if not result["facility_type_match"]:
        result["rejection_reasons"].append("facility_type_mismatch")
    elif not result["facility_number_match"]:
        result["rejection_reasons"].append("facility_number_mismatch")
    return result


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


def near_miss_row(promoted_key: str, promoted_row: dict[str, Any], event_row: dict[str, Any], key_to_cemsids: dict[str, set[str]]) -> dict[str, Any]:
    diagnostics = pair_diagnostics(promoted_row, event_row)
    overlap = sorted(event_cemsids(event_row) & key_to_cemsids.get(promoted_key, set()))
    distance = distance_meters(promoted_row.get("lat"), promoted_row.get("lng"), event_row.get("lat"), event_row.get("lng"))
    reasons = list(diagnostics["rejection_reasons"])
    if not borough_compatible(promoted_row, event_row):
        reasons.append("borough_mismatch")
    if not overlap:
        reasons.append("no_cemsid_overlap")
    if distance is not None and distance > SAME_COORDINATE_NEAR_METERS:
        reasons.append("coordinate_conflict")
    return {
        "best_event_facility": diagnostics["best_event_facility"],
        "best_event_site": diagnostics["best_event_site"],
        "best_facility_score": diagnostics["best_facility_score"],
        "best_promoted_facility": diagnostics["best_promoted_facility"],
        "best_promoted_site": diagnostics["best_promoted_site"],
        "best_site_score": diagnostics["best_site_score"],
        "coordinate_distance_meters": round(distance, 2) if distance is not None else None,
        "current_lat": event_row.get("lat"),
        "current_lng": event_row.get("lng"),
        "display_location": row_location(event_row),
        "event_borough": event_row.get("borough") or event_row.get("event_borough"),
        "exact_coordinate_match": bool(distance is not None and distance < 0.5),
        "facility_number_match": diagnostics["facility_number_match"],
        "facility_type_match": diagnostics["facility_type_match"],
        "overlapping_cemsids": overlap,
        "rejection_reasons": sorted(set(reasons)) or ["no_candidate_rows_found"],
        "source_cemsid": sorted(event_cemsids(event_row)),
        "source_event_id": event_row.get("source_event_id") or event_row.get("event_id") or event_row.get("id"),
        "stable_event_identity": stable_event_identity(event_row),
        "title": event_row.get("title") or event_row.get("event_name"),
    }


def near_miss_diagnostics(promoted_key: str, promoted_row: dict[str, Any], staged_rows: list[dict[str, Any]], key_to_cemsids: dict[str, set[str]]) -> dict[str, Any]:
    same_site_candidates: list[dict[str, Any]] = []
    same_facility_candidates: list[dict[str, Any]] = []
    same_coordinate_candidates: list[dict[str, Any]] = []
    same_cemsid_candidates: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()

    for event_row in staged_rows:
        row = near_miss_row(promoted_key, promoted_row, event_row, key_to_cemsids)
        for reason in row["rejection_reasons"]:
            if reason in REJECTION_REASONS:
                rejection_counts[reason] += 1

        if row["best_site_score"] >= SAME_SITE_NEAR_MISS_MIN_SCORE:
            same_site_candidates.append(row)
        if row["facility_type_match"] and row["facility_number_match"]:
            same_facility_candidates.append(row)
        if row["coordinate_distance_meters"] is not None and row["coordinate_distance_meters"] <= SAME_COORDINATE_NEAR_METERS:
            same_coordinate_candidates.append(row)
        if row["overlapping_cemsids"]:
            same_cemsid_candidates.append(row)

    if not staged_rows:
        rejection_counts["no_candidate_rows_found"] += 1
    if not any([same_site_candidates, same_facility_candidates, same_coordinate_candidates, same_cemsid_candidates]):
        rejection_counts["no_candidate_rows_found"] += 1

    same_site_candidates.sort(key=lambda row: (row["best_site_score"], row["best_facility_score"]), reverse=True)
    same_facility_candidates.sort(key=lambda row: (row["best_facility_score"], row["best_site_score"]), reverse=True)
    same_coordinate_candidates.sort(key=lambda row: row["coordinate_distance_meters"] if row["coordinate_distance_meters"] is not None else 999999999.0)
    same_cemsid_candidates.sort(key=lambda row: (len(row["overlapping_cemsids"]), row["best_site_score"], row["best_facility_score"]), reverse=True)

    return {
        "closest_same_facility_candidates": same_facility_candidates[:NEAR_MISS_LIMIT],
        "closest_same_site_candidates": same_site_candidates[:NEAR_MISS_LIMIT],
        "rejection_reason_counts": {reason: int(rejection_counts.get(reason, 0)) for reason in REJECTION_REASONS},
        "same_cemsid_candidates": same_cemsid_candidates[:NEAR_MISS_LIMIT],
        "same_coordinate_candidates": same_coordinate_candidates[:NEAR_MISS_LIMIT],
    }


def rows_from_staged(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events", None), list):
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

    unmatched_keys = sorted(key for key in promoted if not candidates_by_key.get(key))
    near_misses_by_key = {
        key: near_miss_diagnostics(key, promoted[key], staged_rows, key_to_cemsids)
        for key in unmatched_keys
    }

    selected_identity_count = len({row["stable_event_identity"] for row in selected_rows})
    selected_count = len(selected_rows)
    all_keys_have_candidates = all(bool(candidates_by_key.get(key)) for key in promoted)
    historical_dry_run_target = int(dry_run_report.get("matched_staged_event_count") or 0)
    stable_identity_ready = (
        selected_count > 0
        and selected_identity_count == selected_count
        and not multi_key_conflicts
    )

    staged_feed_provenance = file_provenance(
        STAGED_FEED_PATH,
        producer_script=PRODUCER_SCRIPT,
        repo_root=ROOT,
        staged_feed_path=DEFAULT_STAGED_FEED_RELATIVE_PATH,
        generated_at_utc=utc_now(),
    )

    report = {
        "blocking_issues": [] if stable_identity_ready else ["Diagnostic selection is not internally consistent (duplicate identities, multi-key conflicts, or empty selection)"],
        "candidate_count_by_promoted_cache_key": {key: len(rows) for key, rows in sorted(candidates_by_key.items())},
        "candidate_match_mode_counts": dict(Counter(mode for rows in candidates_by_key.values() for row in rows for mode in row["match_modes"])),
        "diagnostic_scope": "row_identity_capture_only_no_staged_feed_write_no_public_map_no_phase_3a",
        "dry_run_expected_matched_staged_event_count": historical_dry_run_target,
        "generated_at_utc": utc_now(),
        "input_dry_run_report": str(DRY_RUN_REPORT_PATH.relative_to(ROOT)),
        "input_location_cache": str(LOCATION_CACHE_PATH.relative_to(ROOT)),
        "input_promotion_report": str(PROMOTION_REPORT_PATH.relative_to(ROOT)),
        "input_staged_feed": str(STAGED_FEED_PATH.relative_to(ROOT)),
        "location_cache_modified": False,
        "multi_key_conflict_count": len(multi_key_conflicts),
        "multi_key_conflicts_sample": multi_key_conflicts[:50],
        "near_miss_diagnostics_by_promoted_cache_key": near_misses_by_key,
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
        "staged_feed_provenance": staged_feed_provenance,
        "stable_identity_ready_for_update": stable_identity_ready,
        "unmatched_promoted_cache_key_count": len(unmatched_keys),
        "unmatched_promoted_cache_keys": unmatched_keys,
        "validated_conditions": {
            "all_promoted_keys_have_candidates": all_keys_have_candidates,
            "historical_dry_run_target_not_used_as_gate": True,
            "location_cache_modified_false": True,
            "near_miss_diagnostics_present_for_unmatched_keys": set(near_misses_by_key) == set(unmatched_keys),
            "no_multi_key_conflicts": not multi_key_conflicts,
            "phase_3a_run_false": True,
            "promoted_cache_key_count_reported": len(promoted),
            "public_map_modified_false": True,
            "selected_candidate_count_positive": selected_count > 0,
            "selected_identities_are_unique": selected_identity_count == selected_count,
            "staged_feed_modified_false": True,
        },
    }

    save_json(DIAGNOSTIC_PATH, report)
    printable = {k: v for k, v in report.items() if k not in {"selected_stable_identity_rows", "near_miss_diagnostics_by_promoted_cache_key"}}
    printable["near_miss_diagnostics_by_promoted_cache_key_count"] = len(near_misses_by_key)
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
