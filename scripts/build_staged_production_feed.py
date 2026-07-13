#!/usr/bin/env python3
"""Build a staged production-shaped feed from the test enriched feed.

This script creates staged outputs only. It does not overwrite production feeds.

Inputs:
- data/nycif_live_test_enriched_events.json

Outputs:
- data/nycif_staged_live_events.json
- data/staged_live_manifest.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TEST_FEED_PATH = DATA_DIR / "nycif_live_test_enriched_events.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
STAGED_MANIFEST_PATH = DATA_DIR / "staged_live_manifest.json"


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


def rows_from_test_feed(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def valid_lat_lng(row: dict[str, Any]) -> bool:
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def date_key(row: dict[str, Any]) -> str:
    for key in ("start_date_time", "start", "date"):
        raw = str(row.get(key) or "")
        match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
        if match:
            return match.group(0)
    return ""


def street_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in (
            "title",
            "event_name",
            "event_type",
            "street_closure_type",
            "location",
            "display_location",
            "major_reason",
            "source_file",
        )
    )


def is_one_day_street_event(row: dict[str, Any]) -> bool:
    text = normalize_text_legacy(street_text(row))
    return bool(
        re.search(
            r"\b(block party|street activity|street event|street fair|street closure|sidewalk closure|plaza event|festival)\b",
            text,
        )
    )


def one_day_street_key(row: dict[str, Any]) -> str:
    try:
        lat = f"{float(row.get('lat')):.5f}"
        lng = f"{float(row.get('lng')):.5f}"
    except Exception:
        lat = ""
        lng = ""
    return "|".join(
        [
            normalize_text_legacy(row.get("title") or row.get("event_name")),
            normalize_text_legacy(row.get("borough") or row.get("event_borough")),
            normalize_text_legacy(row.get("display_location") or row.get("location") or row.get("address")),
            lat,
            lng,
        ]
    )


def priority_score(row: dict[str, Any]) -> int:
    score = 0
    for key in ("expected_crowd_score", "priority_score", "priority"):
        try:
            score += int(row.get(key) or 0)
        except Exception:
            pass
    if row.get("field_default"):
        score += 100
    if row.get("photo_pick") or row.get("photoPick"):
        score += 50
    if row.get("match_type") == "event_id":
        score += 25
    return score


def choose_street_keeper(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    # For one-day street-style events, keep the earliest source date. If dates tie, keep the stronger row.
    da = date_key(a)
    db = date_key(b)
    if da and db and da != db:
        return a if da < db else b
    return b if priority_score(b) > priority_score(a) else a


def reject_sample(row: dict[str, Any], reason: str, kept: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "reason": reason,
        "title": row.get("title") or row.get("event_name"),
        "date": date_key(row),
        "borough": row.get("borough") or row.get("event_borough"),
        "display_location": row.get("display_location") or row.get("location"),
        "source_event_id": row.get("source_event_id") or row.get("event_id"),
        "source_cemsid": row.get("source_cemsid") or [],
        "kept_date": date_key(kept) if kept else None,
        "kept_source_event_id": (kept or {}).get("source_event_id") if kept else None,
    }


def apply_one_day_street_dedupe(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    keyed: dict[str, dict[str, Any]] = {}
    passthrough: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in rows:
        if not is_one_day_street_event(row):
            passthrough.append(row)
            continue
        key = one_day_street_key(row)
        if not key.strip("|"):
            passthrough.append(row)
            continue
        if key not in keyed:
            keyed[key] = row
            continue
        existing = keyed[key]
        kept = choose_street_keeper(existing, row)
        removed = row if kept is existing else existing
        keyed[key] = kept
        rejected.append(reject_sample(removed, "one_day_street_duplicate_suppressed", kept))

    return [*passthrough, *keyed.values()], rejected


def staged_event(row: dict[str, Any]) -> dict[str, Any]:
    # Keep production app-friendly fields while retaining source keys for QA traceability.
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "category": row.get("category") or "general",
        "borough": row.get("borough"),
        "location": row.get("location"),
        "display_location": row.get("display_location") or row.get("location"),
        "lat": float(row.get("lat")),
        "lng": float(row.get("lng")),
        "date": row.get("date"),
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "display_time": row.get("display_time"),
        "event_agency": row.get("event_agency"),
        "event_type": row.get("event_type"),
        "street_closure_type": row.get("street_closure_type"),
        "community_board": row.get("community_board") or [],
        "police_precinct": row.get("police_precinct") or [],
        "source_dataset": row.get("source_dataset") or "tvpp-9vvx",
        "source_event_id": row.get("source_event_id"),
        "source_cemsid": row.get("source_cemsid") or [],
        "match_type": row.get("match_type"),
        "location_source": row.get("location_source"),
        "needs_review": False,
        "production_ready": True,
        "staged_feed": True,
    }


def main() -> int:
    source_payload = load_json_file(TEST_FEED_PATH, {})
    rows = rows_from_test_feed(source_payload)
    eligible_rows = [row for row in rows if row.get("needs_review") is False and valid_lat_lng(row)]
    staged_source_rows, one_day_street_rejected_rows = apply_one_day_street_dedupe(eligible_rows)
    staged_rows = [staged_event(row) for row in staged_source_rows]
    skipped_rows = [row for row in rows if not (row.get("needs_review") is False and valid_lat_lng(row))]
    staged_rows.sort(key=lambda row: (row.get("date") or "9999-99-99", row.get("start_date_time") or "", row.get("borough") or "", row.get("title") or ""))

    generated_at = datetime.now(timezone.utc).isoformat()
    match_counts: dict[str, int] = {}
    borough_counts: dict[str, int] = {}
    category_counts: dict[str, int] = {}
    for row in staged_rows:
        match_type = str(row.get("match_type") or "unknown")
        borough = str(row.get("borough") or "Unknown")
        category = str(row.get("category") or "general")
        match_counts[match_type] = match_counts.get(match_type, 0) + 1
        borough_counts[borough] = borough_counts.get(borough, 0) + 1
        category_counts[category] = category_counts.get(category, 0) + 1

    feed = {
        "generated_at_utc": generated_at,
        "source": "nycif_live_test_enriched_events.json",
        "production_feed": False,
        "staged_feed": True,
        "production_ready": True,
        "events": staged_rows,
    }
    manifest = {
        "generated_at_utc": generated_at,
        "source": "nycif_live_test_enriched_events.json",
        "production_feed": False,
        "staged_feed": True,
        "production_ready": True,
        "test_feed_rows_loaded": len(rows),
        "eligible_rows_before_one_day_street_dedupe": len(eligible_rows),
        "staged_feed_events": len(staged_rows),
        "skipped_needs_review_or_bad_gps": len(skipped_rows),
        "one_day_street_duplicates_suppressed": len(one_day_street_rejected_rows),
        "duplicate_policy": {
            "one_day_street_events": "dedupe by title + borough + location + coordinate; keep earliest source date; recurring sports and park events are not deduped by this rule",
            "production_feeds_modified": False,
        },
        "match_counts": match_counts,
        "borough_counts": borough_counts,
        "category_counts": category_counts,
        "sample_one_day_street_rejected_rows": one_day_street_rejected_rows[:25],
        "sample_skipped_rows": [
            {
                "title": row.get("title"),
                "borough": row.get("borough"),
                "display_time": row.get("display_time"),
                "display_location": row.get("display_location") or row.get("location"),
                "source_event_id": row.get("source_event_id"),
                "source_cemsid": row.get("source_cemsid") or [],
            }
            for row in skipped_rows[:20]
        ],
    }

    save_json_file(STAGED_FEED_PATH, feed)
    save_json_file(STAGED_MANIFEST_PATH, manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
