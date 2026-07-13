#!/usr/bin/env python3
"""Build Phase 2 GPS review grouping artifacts.

This is a staging-only QA step. It does not geocode, does not modify
location_cache.json, and does not publish anything to the public map.

Purpose:
- Read data/gps_needs_review_events.json.
- Group repeated unresolved locations.
- Identify high-impact location groups worth geocoding first.
- Produce readable, compact grouping artifacts for QA.
- Produce a safe proposal queue for manual/API geocoding.

Outputs:
- data/gps_review_group_report.json
- data/gps_review_location_groups.json
- data/gps_review_geocoding_queue.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import build_group_key
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import build_group_key

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
GPS_REVIEW_PATH = DATA_DIR / "gps_needs_review_events.json"
GROUP_REPORT_PATH = DATA_DIR / "gps_review_group_report.json"
LOCATION_GROUPS_PATH = DATA_DIR / "gps_review_location_groups.json"
GEOCODING_QUEUE_PATH = DATA_DIR / "gps_review_geocoding_queue.json"
MAX_SAMPLE_EVENTS_PER_GROUP = 3


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


def date_key(value: Any) -> str:
    raw = str(value or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def borough(row: dict[str, Any]) -> str:
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def location(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("event_location") or "").strip()


def title(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("event_name") or "").strip()


def event_type(row: dict[str, Any]) -> str:
    return str(row.get("event_type") or "").strip()


def event_agency(row: dict[str, Any]) -> str:
    return str(row.get("event_agency") or "").strip()


def source_event_id(row: dict[str, Any]) -> str:
    return str(row.get("source_event_id") or row.get("event_id") or "").strip()


def cemsids(row: dict[str, Any]) -> list[str]:
    value = row.get("source_cemsid") or row.get("cemsid") or []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def likely_geocoder_query(row: dict[str, Any]) -> str:
    b = borough(row)
    loc = location(row)
    if not loc:
        return ""
    return f"{loc}, {b}, New York, NY" if b else f"{loc}, New York, NY"


def simplified_place_name(text: str) -> str:
    first = text.split(",")[0].strip()
    if ":" in first:
        first = first.split(":", 1)[0].strip()
    return first


def simplified_geocoder_query(row: dict[str, Any]) -> str:
    place = simplified_place_name(location(row))
    b = borough(row)
    if not place:
        return ""
    return f"{place}, {b}, New York, NY" if b else f"{place}, New York, NY"


def location_complexity(text: str) -> str:
    if not text:
        return "missing_location"
    comma_count = text.count(",")
    between_count = len(re.findall(r"\bbetween\b", text, flags=re.I))
    colon_count = text.count(":")
    if comma_count >= 2 or between_count >= 2:
        return "multi_segment_corridor"
    if " between " in text.lower():
        return "street_between_pair"
    if colon_count >= 1:
        return "park_or_facility_subsite"
    return "single_place_or_block"


def confidence_hint(example: dict[str, Any]) -> str:
    complexity = location_complexity(location(example))
    if complexity == "single_place_or_block":
        return "good_candidate"
    if complexity in {"street_between_pair", "park_or_facility_subsite"}:
        return "review_candidate"
    if complexity == "multi_segment_corridor":
        return "manual_review_first"
    return "insufficient_location"


def compact_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": title(row),
        "date": date_key(row.get("date") or row.get("start_date_time")),
        "start_date_time": row.get("start_date_time"),
        "borough": borough(row),
        "display_location": location(row),
        "source_event_id": source_event_id(row),
        "source_cemsid": cemsids(row),
        "event_type": event_type(row),
        "event_agency": event_agency(row),
    }


def build_group_record(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    example = rows[0]
    titles = Counter(title(row) for row in rows if title(row))
    event_types = Counter(event_type(row) for row in rows if event_type(row))
    agencies = Counter(event_agency(row) for row in rows if event_agency(row))
    dates = sorted({date_key(row.get("date") or row.get("start_date_time")) for row in rows if date_key(row.get("date") or row.get("start_date_time"))})
    source_ids = sorted({source_event_id(row) for row in rows if source_event_id(row)})
    cemsid_values = sorted({cid for row in rows for cid in cemsids(row)})
    complexity = location_complexity(location(example))
    hint = confidence_hint(example)
    return {
        "group_key": key,
        "event_count": len(rows),
        "unique_source_event_ids": len(source_ids),
        "borough": borough(example),
        "display_location": location(example),
        "location_complexity": complexity,
        "confidence_hint": hint,
        "geocoder_query": likely_geocoder_query(example),
        "simplified_geocoder_query": simplified_geocoder_query(example),
        "top_titles": titles.most_common(5),
        "event_types": event_types.most_common(5),
        "event_agencies": agencies.most_common(5),
        "first_date": dates[0] if dates else "",
        "last_date": dates[-1] if dates else "",
        "date_count": len(dates),
        "source_event_ids_sample": source_ids[:10],
        "source_cemsid_sample": cemsid_values[:10],
        "sample_events": [compact_event(row) for row in rows[:MAX_SAMPLE_EVENTS_PER_GROUP]],
        "sample_events_truncated": len(rows) > MAX_SAMPLE_EVENTS_PER_GROUP,
        "publish_status": "not_geocoded_not_public",
    }


def main() -> int:
    review_rows = rows_from_payload(load_json_file(GPS_REVIEW_PATH, {}))
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in review_rows:
        groups[build_group_key(row)].append(row)

    grouped_rows = [build_group_record(key, rows) for key, rows in groups.items()]
    grouped_rows.sort(key=lambda row: (row["event_count"], row["unique_source_event_ids"]), reverse=True)

    queue = []
    for row in grouped_rows:
        if row["confidence_hint"] in {"good_candidate", "review_candidate"}:
            queue.append({
                "group_key": row["group_key"],
                "priority_score": row["event_count"] + row["unique_source_event_ids"],
                "event_count": row["event_count"],
                "borough": row["borough"],
                "display_location": row["display_location"],
                "geocoder_query": row["geocoder_query"],
                "simplified_geocoder_query": row["simplified_geocoder_query"],
                "confidence_hint": row["confidence_hint"],
                "location_complexity": row["location_complexity"],
                "proposed_lat": None,
                "proposed_lng": None,
                "geocoder_source": None,
                "geocoder_confidence": None,
                "manual_review_status": "pending",
                "promotion_allowed": False,
            })
    queue.sort(key=lambda row: row["priority_score"], reverse=True)

    complexity_counts = Counter(row["location_complexity"] for row in grouped_rows)
    confidence_counts = Counter(row["confidence_hint"] for row in grouped_rows)
    borough_counts = Counter(row["borough"] for row in grouped_rows)
    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "generated_at_utc": generated_at,
        "phase": "phase_2_controlled_gps_review",
        "input_review_events": len(review_rows),
        "unique_location_groups": len(grouped_rows),
        "geocoding_queue_count": len(queue),
        "top_location_groups_sample": grouped_rows[:50],
        "complexity_counts": dict(complexity_counts),
        "confidence_counts": dict(confidence_counts),
        "borough_group_counts": dict(borough_counts),
        "public_map_modified": False,
        "location_cache_modified": False,
        "location_groups_readable_compact": True,
        "sample_events_per_group_limit": MAX_SAMPLE_EVENTS_PER_GROUP,
        "promotion_rule": "Only rows with proposed coordinates, named geocoder source, confidence score, and manual_review_status=approved may be promoted by a separate promotion script.",
    }

    save_json_file(GROUP_REPORT_PATH, report)
    save_json_file(LOCATION_GROUPS_PATH, {"generated_at_utc": generated_at, "groups": grouped_rows})
    save_json_file(GEOCODING_QUEUE_PATH, {"generated_at_utc": generated_at, "queue": queue})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
