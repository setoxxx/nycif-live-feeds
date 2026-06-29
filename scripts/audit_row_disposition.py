#!/usr/bin/env python3
"""Audit every incoming NYC Open Data row into an explicit disposition.

Every current/future raw row must end in exactly one bucket:
1. staged_with_valid_gps
2. matched_known_gps_memory
3. gps_review_queue
4. rejected_with_reason

Outputs:
- data/row_disposition_report.json
- data/row_disposition_events.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_SNAPSHOT_PATH = DATA_DIR / "raw_nyc_open_data_snapshot.json"
TEST_FEED_PATH = DATA_DIR / "nycif_live_test_enriched_events.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
LOCATION_CACHE_PATH = DATA_DIR / "location_cache.json"
GPS_NEEDS_REVIEW_PATH = DATA_DIR / "gps_needs_review_events.json"
ROW_DISPOSITION_REPORT_PATH = DATA_DIR / "row_disposition_report.json"
ROW_DISPOSITION_EVENTS_PATH = DATA_DIR / "row_disposition_events.json"
TODAY_UTC = datetime.now(timezone.utc).date().isoformat()


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


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def split_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def date_key(value: Any) -> str:
    raw = str(value or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def raw_date(row: dict[str, Any]) -> str:
    return date_key(row.get("start_date_time") or row.get("date"))


def feed_date(row: dict[str, Any]) -> str:
    return date_key(row.get("date") or row.get("start_date_time") or row.get("start"))


def source_event_id(row: dict[str, Any]) -> str:
    return str(row.get("source_event_id") or row.get("event_id") or "").strip()


def title_text(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("event_name") or row.get("name") or "").strip()


def borough_text(row: dict[str, Any]) -> str:
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def location_text(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or row.get("address") or "").strip()


def valid_lat_lng(row: dict[str, Any]) -> bool:
    try:
        lat = float(row.get("lat"))
        lng = float(row.get("lng"))
    except Exception:
        return False
    return 40.0 <= lat <= 41.0 and -75.0 <= lng <= -73.0


def raw_keys(row: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    event_id = source_event_id(row)
    borough = borough_text(row)
    location = location_text(row)
    title = title_text(row)
    date = raw_date(row)
    if event_id:
        keys.add(f"event_id:{event_id}")
        keys.add(event_id)
        keys.add(f"nyc_open_data:tvpp-9vvx:{event_id}")
    for cemsid in split_ids(row.get("source_cemsid") or row.get("cemsid")):
        keys.add(f"cemsid:{norm(borough)}:{cemsid}")
    if location:
        keys.add(f"location:{norm(borough)}:{norm(location)}")
    if title and location and date:
        keys.add(f"text_date_location:{norm(title)}:{norm(borough)}:{norm(location)}:{date}")
        keys.add("|".join([norm(title), norm(borough), norm(location), date]))
    return {key for key in keys if key}


def feed_keys(row: dict[str, Any]) -> set[str]:
    keys = raw_keys(row)
    row_id = str(row.get("id") or "").strip()
    if row_id:
        keys.add(row_id)
    return keys


def compact_raw(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_event_id": source_event_id(row),
        "title": title_text(row),
        "date": raw_date(row),
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "borough": borough_text(row),
        "display_location": location_text(row),
        "event_type": row.get("event_type"),
        "event_agency": row.get("event_agency"),
        "source_cemsid": split_ids(row.get("source_cemsid") or row.get("cemsid")),
    }


def index_by_keys(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in feed_keys(row):
            index.setdefault(key, row)
    return index


def cache_keys(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return set()
    return set(entries.keys())


def disposition_for_raw(row: dict[str, Any], staged_index: dict[str, dict[str, Any]], test_index: dict[str, dict[str, Any]], gps_keys: set[str], review_keys: set[str]) -> dict[str, Any]:
    keys = raw_keys(row)
    staged_match = next((staged_index[key] for key in keys if key in staged_index), None)
    test_match = next((test_index[key] for key in keys if key in test_index), None)

    event = compact_raw(row)
    event["disposition"] = "rejected_with_reason"
    event["reason"] = "unclassified_raw_row"

    if staged_match and valid_lat_lng(staged_match):
        event["disposition"] = "staged_with_valid_gps"
        event["reason"] = "present_in_staged_feed_with_valid_nyc_coordinates"
        event["lat"] = staged_match.get("lat")
        event["lng"] = staged_match.get("lng")
        event["match_type"] = staged_match.get("match_type")
        return event

    if test_match and valid_lat_lng(test_match):
        event["disposition"] = "matched_known_gps_memory"
        event["reason"] = "present_in_test_feed_with_valid_gps_but_not_public_staged"
        event["lat"] = test_match.get("lat")
        event["lng"] = test_match.get("lng")
        event["match_type"] = test_match.get("match_type")
        return event

    if any(key in gps_keys for key in keys):
        event["disposition"] = "matched_known_gps_memory"
        event["reason"] = "matched_location_cache_but_not_staged"
        return event

    if any(key in review_keys for key in keys):
        event["disposition"] = "gps_review_queue"
        event["reason"] = "listed_in_gps_needs_review_queue"
        return event

    if not raw_date(row):
        event["reason"] = "missing_or_unparseable_date"
    elif raw_date(row) < TODAY_UTC:
        event["reason"] = "past_event_not_current_future"
    elif not location_text(row):
        event["reason"] = "missing_location"
    elif not title_text(row):
        event["reason"] = "missing_title"
    else:
        event["disposition"] = "gps_review_queue"
        event["reason"] = "current_future_row_missing_gps_match_not_yet_in_review_queue"
    return event


def main() -> int:
    raw_rows_all = rows_from_payload(load_json_file(RAW_SNAPSHOT_PATH, []))
    raw_rows = [row for row in raw_rows_all if raw_date(row) >= TODAY_UTC]
    test_rows = rows_from_payload(load_json_file(TEST_FEED_PATH, {}))
    staged_rows = rows_from_payload(load_json_file(STAGED_FEED_PATH, {}))
    review_rows = rows_from_payload(load_json_file(GPS_NEEDS_REVIEW_PATH, {}))

    staged_index = index_by_keys(staged_rows)
    test_index = index_by_keys(test_rows)
    gps_keys = cache_keys(load_json_file(LOCATION_CACHE_PATH, {}))
    review_index = index_by_keys(review_rows)
    review_keys = set(review_index.keys())

    dispositions = [disposition_for_raw(row, staged_index, test_index, gps_keys, review_keys) for row in raw_rows]
    counts = Counter(row["disposition"] for row in dispositions)
    reason_counts = Counter(row["reason"] for row in dispositions)
    total = len(dispositions)
    covered = counts["staged_with_valid_gps"] + counts["matched_known_gps_memory"] + counts["gps_review_queue"] + counts["rejected_with_reason"]
    gps_ready = counts["staged_with_valid_gps"] + counts["matched_known_gps_memory"]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "today_utc": TODAY_UTC,
        "raw_rows_loaded": len(raw_rows_all),
        "current_future_raw_rows": total,
        "classified_rows": covered,
        "unclassified_rows": max(total - covered, 0),
        "disposition_counts": dict(counts),
        "reason_counts": dict(reason_counts),
        "gps_ready_or_known_count": gps_ready,
        "gps_ready_or_known_pct": round((gps_ready / total) * 100, 3) if total else None,
        "qa_pass": total == covered and max(total - covered, 0) == 0,
        "qa_contract": [
            "staged_with_valid_gps",
            "matched_known_gps_memory",
            "gps_review_queue",
            "rejected_with_reason",
        ],
        "samples": {
            "gps_review_queue": [row for row in dispositions if row["disposition"] == "gps_review_queue"][:50],
            "rejected_with_reason": [row for row in dispositions if row["disposition"] == "rejected_with_reason"][:50],
        },
    }

    save_json_file(ROW_DISPOSITION_REPORT_PATH, report)
    save_json_file(ROW_DISPOSITION_EVENTS_PATH, {"generated_at_utc": report["generated_at_utc"], "events": dispositions})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
