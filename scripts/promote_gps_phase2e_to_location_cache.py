#!/usr/bin/env python3
"""Phase 2E — promote approved GPS rows into location_cache.json.

Explicit human authorization required before running. This script:
- reads approved rows from data/gps_manual_approval_queue.json
- writes master GPS entries into data/location_cache.json
- does NOT modify the staged feed or publish directly to the public map

Outputs:
- data/location_cache.json (updated)
- data/gps_phase2e_promotion_report.json
- data/gps_phase2e_promoted_rows.json
- data/gps_manual_approval_queue.json (promotion_allowed flags updated)
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APPROVAL_QUEUE_PATH = DATA_DIR / "gps_manual_approval_queue.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
PROMOTION_REPORT_PATH = DATA_DIR / "gps_phase2e_promotion_report.json"
PROMOTED_ROWS_PATH = DATA_DIR / "gps_phase2e_promoted_rows.json"
POST_QA_REPORT_PATH = DATA_DIR / "gps_phase2e_post_promotion_qa_report.json"


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
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


def coords_match(a_lat: Any, a_lng: Any, b_lat: Any, b_lng: Any, epsilon: float = 1e-5) -> bool:
    try:
        return abs(float(a_lat) - float(b_lat)) <= epsilon and abs(float(a_lng) - float(b_lng)) <= epsilon
    except Exception:
        return False


def cache_keys_for_row(row: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (cache_key, key_type) pairs for master location memory."""
    keys: list[tuple[str, str]] = []
    place_id = str(row.get("geocoder_place_id") or "").strip()
    borough = str(row.get("borough") or "").strip()
    location = str(row.get("display_location") or "").strip()

    if place_id.startswith("cemsid:"):
        keys.append((place_id, "cemsid"))
    elif place_id:
        keys.append((f"parks_facility:{place_id}", "parks_facility"))

    if borough and location:
        loc_key = f"location:{normalize_text_legacy(borough)}:{normalize_text_legacy(location)}"
        keys.append((loc_key, "location"))

    group_key = str(row.get("group_key") or "").strip()
    if group_key:
        keys.append((f"group_key:{group_key}", "group_key"))

    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for key, key_type in keys:
        if key not in seen:
            seen.add(key)
            unique.append((key, key_type))
    return unique


def cache_entry_from_row(row: dict[str, Any], cache_key: str, key_type: str, promoted_at: str) -> dict[str, Any]:
    place_id = str(row.get("geocoder_place_id") or "").strip()
    return {
        "lat": float(row["proposed_lat"]),
        "lng": float(row["proposed_lng"]),
        "display_location": row.get("display_location"),
        "borough": row.get("borough"),
        "confidence": row.get("geocoder_confidence") or "high",
        "source": "phase_2e_manual_approval_promotion",
        "geocoder_source": row.get("geocoder_source"),
        "confidence_reason": row.get("confidence_reason"),
        "key_type": key_type,
        "key_value": place_id or cache_key,
        "group_key": row.get("group_key"),
        "manual_reviewer": row.get("manual_reviewer"),
        "manual_reviewed_at_utc": row.get("manual_reviewed_at_utc"),
        "approval_decision_reason": row.get("approval_decision_reason"),
        "last_verified_at_utc": promoted_at,
        "phase": "phase_2e",
    }


def existing_coords(entry: Any) -> tuple[Any, Any]:
    if not isinstance(entry, dict):
        return None, None
    return entry.get("lat"), entry.get("lng")


def main() -> int:
    queue_payload = load_json_file(APPROVAL_QUEUE_PATH, {})
    cache_payload = load_json_file(LOCATION_CACHE_PATH, {})
    queue = rows_from_payload(queue_payload, "approval_queue")

    if not isinstance(cache_payload, dict) or not isinstance(cache_payload.get("entries"), dict):
        print(json.dumps({"error": "location_cache.json missing entries dict"}, indent=2))
        return 1

    entries: dict[str, Any] = dict(cache_payload["entries"])
    before_count = len(entries)
    promoted_at = datetime.now(timezone.utc).isoformat()

    approved_rows = [row for row in queue if row.get("manual_review_status") == "approved"]
    promoted_rows: list[dict[str, Any]] = []
    cache_writes: list[dict[str, Any]] = []
    skipped_duplicates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    for row in approved_rows:
        if not valid_nyc_lat_lng(row.get("proposed_lat"), row.get("proposed_lng")):
            invalid_rows.append({"group_key": row.get("group_key"), "display_location": row.get("display_location")})
            continue
        if not row.get("manual_reviewer") or not row.get("approval_decision_reason"):
            invalid_rows.append({"group_key": row.get("group_key"), "reason": "missing_reviewer_metadata"})
            continue

        row_writes: list[dict[str, Any]] = []
        row_conflicts: list[dict[str, Any]] = []

        for cache_key, key_type in cache_keys_for_row(row):
            new_entry = cache_entry_from_row(row, cache_key, key_type, promoted_at)
            existing = entries.get(cache_key)
            if existing is None:
                entries[cache_key] = new_entry
                row_writes.append({"action": "add", "cache_key": cache_key, "key_type": key_type})
            else:
                ex_lat, ex_lng = existing_coords(existing)
                if coords_match(ex_lat, ex_lng, row.get("proposed_lat"), row.get("proposed_lng")):
                    skipped_duplicates.append(
                        {
                            "cache_key": cache_key,
                            "group_key": row.get("group_key"),
                            "display_location": row.get("display_location"),
                            "reason": "existing_cache_same_coordinates",
                        }
                    )
                else:
                    row_conflicts.append(
                        {
                            "cache_key": cache_key,
                            "group_key": row.get("group_key"),
                            "display_location": row.get("display_location"),
                            "existing_lat": ex_lat,
                            "existing_lng": ex_lng,
                            "proposed_lat": row.get("proposed_lat"),
                            "proposed_lng": row.get("proposed_lng"),
                        }
                    )

        if row_conflicts:
            conflicts.extend(row_conflicts)
            continue

        cache_writes.extend(row_writes)
        promoted_rows.append(
            {
                "group_key": row.get("group_key"),
                "display_location": row.get("display_location"),
                "borough": row.get("borough"),
                "proposed_lat": row.get("proposed_lat"),
                "proposed_lng": row.get("proposed_lng"),
                "geocoder_source": row.get("geocoder_source"),
                "cache_keys_written": [item["cache_key"] for item in row_writes],
                "cache_keys_skipped_duplicate": [
                    item["cache_key"]
                    for item in skipped_duplicates
                    if item.get("group_key") == row.get("group_key")
                ],
            }
        )

    after_count = len(entries)
    promoted_group_keys = {row.get("group_key") for row in promoted_rows}

    updated_queue: list[dict[str, Any]] = []
    for row in queue:
        out = dict(row)
        if row.get("group_key") in promoted_group_keys:
            out["promotion_allowed"] = True
            out["location_cache_modified"] = True
            out["phase_2e_promotion_performed"] = True
            out["phase_2e_promoted_at_utc"] = promoted_at
        updated_queue.append(out)

    cache_payload["entries"] = entries
    cache_payload["cache_entry_count"] = after_count
    cache_payload["last_phase_2e_promotion_at_utc"] = promoted_at
    cache_payload["last_phase_2e_promotion_row_count"] = len(promoted_rows)

    qa_pass = len(invalid_rows) == 0 and len(conflicts) == 0 and len(promoted_rows) == len(approved_rows)

    promotion_report = {
        "generated_at_utc": promoted_at,
        "phase": "phase_2e_location_cache_promotion",
        "qa_pass": qa_pass,
        "approved_input_count": len(approved_rows),
        "promoted_row_count": len(promoted_rows),
        "cache_keys_added_count": len(cache_writes),
        "duplicate_skip_count": len(skipped_duplicates),
        "conflict_count": len(conflicts),
        "invalid_row_count": len(invalid_rows),
        "location_cache_count_before": before_count,
        "location_cache_count_after": after_count,
        "location_cache_net_new_entries": after_count - before_count,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "promotion_performed": True,
        "source_artifact": "data/gps_manual_approval_queue.json",
        "conflicts_requiring_human_review": conflicts,
        "invalid_rows": invalid_rows,
        "promoted_group_keys": sorted(key for key in promoted_group_keys if key),
    }

    post_qa = {
        "generated_at_utc": promoted_at,
        "phase": "phase_2e_post_promotion_qa",
        "qa_pass": qa_pass,
        "promoted_row_count": len(promoted_rows),
        "location_cache_modified": True,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "next_required_step": "Re-run live sync / row disposition to consume new master GPS keys for future events at these locations.",
    }

    save_json_file(LOCATION_CACHE_PATH, cache_payload)
    save_json_file(APPROVAL_QUEUE_PATH, {"generated_at_utc": promoted_at, "approval_queue": updated_queue})
    save_json_file(PROMOTION_REPORT_PATH, promotion_report)
    save_json_file(PROMOTED_ROWS_PATH, {"generated_at_utc": promoted_at, "promoted_rows": promoted_rows})
    save_json_file(POST_QA_REPORT_PATH, post_qa)

    print(json.dumps(promotion_report, indent=2, ensure_ascii=False))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
