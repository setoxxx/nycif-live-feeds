#!/usr/bin/env python3
"""Build Milestone 9 coverage-gap review findings (Phases A, B, C).

Produces evidence-only classification artifacts for human review.
Does NOT approve, promote, modify location_cache, staged feeds, or public map.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.build_gps_geocoding_filled_proposals import (
        simplified_place,
        valid_nyc_lat_lng,
    )
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        overlap_key,
        repo_relative,
        row_coords,
        safety_fields,
        save_json_file,
        title_key,
        utc_now_iso,
        write_csv,
    )
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover
    from build_gps_geocoding_filled_proposals import simplified_place, valid_nyc_lat_lng
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        overlap_key,
        repo_relative,
        row_coords,
        safety_fields,
        save_json_file,
        title_key,
        utc_now_iso,
        write_csv,
    )
    from gps_identity import normalize_text_legacy

UNFILLED_QUEUE = DATA_DIR / "gps_review_geocoding_unfilled_review_queue.json"
FACILITY_REF = DATA_DIR / "nyc_parks_facility_reference.json"
PARKS_SNAPSHOT = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
LOCATION_CACHE = DATA_DIR / "location_cache.json"

GPS_FINDINGS = DATA_DIR / "gps_unfilled_review_findings.json"
CALENDAR_QUEUE = DATA_DIR / "supplemental_calendar_only_review_queue.json"
CALENDAR_FINDINGS = DATA_DIR / "supplemental_calendar_only_review_findings.json"
CALENDAR_PRIORITY_CSV = DATA_DIR / "supplemental_calendar_only_priority_review.csv"
PARKS_QUEUE = DATA_DIR / "supplemental_parks_only_review_queue.json"
PARKS_FINDINGS = DATA_DIR / "supplemental_parks_only_review_findings.json"

PRIORITY_CSV_FIELDS = [
    "priority_rank",
    "overlap_key",
    "title",
    "start_date_time",
    "boroughs",
    "categories",
    "parks_title_date_match",
    "proposed_lat",
    "proposed_lng",
    "classification",
    "review_notes",
    "manual_review_status",
    "promotion_allowed",
]


def rows_from_payload(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get(key), list):
        return [row for row in payload[key] if isinstance(row, dict)]
    return []


def parent_place(display: str) -> str:
    text = str(display or "").split(":")[0].strip()
    return simplified_place(text)


def build_facility_index() -> dict[str, dict[str, Any]]:
    payload = load_json_file(FACILITY_REF, {})
    facilities = payload.get("facilities", []) if isinstance(payload, dict) else []
    index: dict[str, dict[str, Any]] = {}
    for row in facilities:
        if not isinstance(row, dict):
            continue
        lat, lng = row.get("lat"), row.get("lng")
        if not valid_nyc_lat_lng(lat, lng):
            continue
        borough = normalize_text_legacy(row.get("borough"))
        for field in ("facility_name", "display_location", "location_text"):
            key = simplified_place(str(row.get(field) or ""))
            if key:
                index[f"{borough}|{key}"] = row
    return index


def build_parks_location_index() -> dict[str, dict[str, Any]]:
    payload = load_json_file(PARKS_SNAPSHOT, {})
    events = payload.get("events", payload) if isinstance(payload, dict) else payload
    if not isinstance(events, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for row in events:
        if not isinstance(row, dict):
            continue
        lat, lng = row_coords(row)
        if lat is None:
            continue
        for field in ("location", "display_location"):
            key = simplified_place(str(row.get(field) or ""))
            if key:
                index[key] = row
    return index


def research_unfilled_row(
    row: dict[str, Any],
    facility_index: dict[str, dict[str, Any]],
    parks_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    display = str(row.get("display_location") or "")
    borough = normalize_text_legacy(row.get("borough"))
    complexity = row.get("location_complexity") or "unknown"
    parent = parent_place(display)
    facility_hit = facility_index.get(f"{borough}|{parent}")
    parks_hit = parks_index.get(parent) or parks_index.get(simplified_place(display))

    if facility_hit:
        classification = "official_parks_facility_reference_match"
        notes = (
            f"Matched parent place '{parent}' in nyc_parks_facility_reference.json "
            f"({facility_hit.get('facility_name')}). Coordinates available for manual_gps_reference.json after human confirmation."
        )
        proposed_lat = facility_hit.get("lat")
        proposed_lng = facility_hit.get("lng")
        source = "nyc_parks_facility_reference.json"
    elif parks_hit:
        lat, lng = row_coords(parks_hit)
        classification = "official_parks_events_snapshot_match"
        notes = (
            f"Matched parent place '{parent}' in nyc_parks_bigapps_events_snapshot.json. "
            "Requires human confirmation before manual_gps_reference.json."
        )
        proposed_lat, proposed_lng = lat, lng
        source = "nyc_parks_bigapps_events_snapshot.json"
    elif complexity == "street_between_pair":
        classification = "needs_human_field_verification"
        notes = (
            "Open street segment between two cross streets. No official reference match. "
            "Requires field-verified midpoint before manual_gps_reference.json."
        )
        proposed_lat, proposed_lng = None, None
        source = None
    else:
        classification = "needs_human_field_verification"
        notes = (
            "Park or facility subsite with no official Parks reference match. "
            "Verify parent park pin manually before adding to manual_gps_reference.json."
        )
        proposed_lat, proposed_lng = None, None
        source = None

    item = {
        "group_key": row.get("group_key"),
        "display_location": display,
        "borough": row.get("borough"),
        "event_count": row.get("event_count"),
        "priority_score": row.get("priority_score"),
        "location_complexity": complexity,
        "classification": classification,
        "research_notes": notes,
        "proposed_lat": proposed_lat,
        "proposed_lng": proposed_lng,
        "proposed_source": source,
        "ready_for_manual_reference": bool(
            proposed_lat is not None
            and proposed_lng is not None
            and classification.startswith("official_")
        ),
    }
    item.update(safety_fields())
    return item


def classify_calendar_row(row: dict[str, Any]) -> tuple[str, str]:
    title = str(row.get("title") or "")
    has_parks = bool(row.get("parks_title_date_match"))
    lat, lng = row_coords(row)
    categories = row.get("categories") or []

    if has_parks and lat is not None:
        return (
            "likely_valid_parks_overlap",
            "Title+date overlap with Parks BigApps; proposed coordinates present for manual spot-check.",
        )
    if has_parks and lat is None:
        return (
            "needs_more_research",
            "Parks title+date overlap but Parks row lacks coordinates in snapshot.",
        )
    if any("Street and Neighborhood" in str(category) for category in categories):
        return (
            "needs_more_research",
            "No Parks match; street/neighborhood event may need address geocoding review.",
        )
    if any("Parks & Recreation" in str(category) for category in categories):
        return (
            "needs_more_research",
            "Parks category calendar event without Parks title+date match; verify permit alias or manual geocoding.",
        )
    return (
        "needs_more_research",
        "No Parks title+date match; calendar address text only.",
    )


def recurring_title_key(title: str) -> str:
    base = title_key(title)
    base = re.sub(r"\d{4}[-/]\d{2}[-/]\d{2}", "", base)
    base = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]?\d{0,4}\b", "", base)
    return normalize_text_legacy(base)


def build_phase_a_findings() -> dict[str, Any]:
    unfilled = rows_from_payload(load_json_file(UNFILLED_QUEUE, {}), "review_queue")
    facility_index = build_facility_index()
    parks_index = build_parks_location_index()
    researched = [
        research_unfilled_row(row, facility_index, parks_index) for row in unfilled
    ]
    classification_counts = Counter(row.get("classification") for row in researched)
    ready = [row for row in researched if row.get("ready_for_manual_reference")]
    return {
        "generated_at_utc": utc_now_iso(),
        "phase": "phase_a_gps_unfilled_review_findings",
        "input_count": len(unfilled),
        "classification_counts": dict(classification_counts),
        "ready_for_manual_reference_count": len(ready),
        "needs_human_field_verification_count": classification_counts.get(
            "needs_human_field_verification", 0
        ),
        "street_between_pair_count": sum(
            1 for row in researched if row.get("location_complexity") == "street_between_pair"
        ),
        "park_or_facility_subsite_count": sum(
            1 for row in researched if row.get("location_complexity") == "park_or_facility_subsite"
        ),
        "ready_for_manual_reference": ready,
        "needs_human_field_verification": [
            row for row in researched if row.get("classification") == "needs_human_field_verification"
        ],
        "all_rows": researched,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": (
            "Human confirms ready_for_manual_reference rows before copying into manual_gps_reference.json. "
            "Street segments require field-verified midpoints."
        ),
    }


def build_phase_b_findings() -> dict[str, Any]:
    queue = rows_from_payload(load_json_file(CALENDAR_QUEUE, {}), "review_queue")
    classified_rows: list[dict[str, Any]] = []
    title_occurrences: Counter[str] = Counter()
    for row in queue:
        title_occurrences[recurring_title_key(str(row.get("title") or ""))] += 1

    for row in queue:
        classification, notes = classify_calendar_row(row)
        item = dict(row)
        item["classification"] = classification
        item["review_notes"] = notes
        item["recurrence_count"] = title_occurrences[
            recurring_title_key(str(row.get("title") or ""))
        ]
        item["promotion_allowed"] = False
        item["manual_review_status"] = "pending"
        classified_rows.append(item)

    classification_counts = Counter(row.get("classification") for row in classified_rows)
    recurring_program_instances = [
        row
        for row in classified_rows
        if row.get("recurrence_count", 0) >= 5
    ]

    priority_rows: list[dict[str, Any]] = []
    for rank, row in enumerate(
        sorted(
            classified_rows,
            key=lambda item: (
                0 if item.get("classification") == "likely_valid_parks_overlap" else 1,
                -int(item.get("recurrence_count") or 0),
                item.get("review_rank") or 0,
            ),
        )[:100],
        start=1,
    ):
        priority_rows.append(
            {
                "priority_rank": rank,
                "overlap_key": row.get("overlap_key"),
                "title": row.get("title"),
                "start_date_time": row.get("start_date_time"),
                "boroughs": ", ".join(str(value) for value in (row.get("boroughs") or [])),
                "categories": ", ".join(str(value) for value in (row.get("categories") or [])),
                "parks_title_date_match": row.get("parks_title_date_match"),
                "proposed_lat": row.get("proposed_lat"),
                "proposed_lng": row.get("proposed_lng"),
                "classification": row.get("classification"),
                "review_notes": row.get("review_notes"),
                "manual_review_status": "pending",
                "promotion_allowed": False,
            }
        )

    write_csv(CALENDAR_PRIORITY_CSV, priority_rows, PRIORITY_CSV_FIELDS)

    spot_check_samples = []
    by_borough: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in classified_rows:
        if row.get("classification") != "likely_valid_parks_overlap":
            continue
        borough_label = ", ".join(str(value) for value in (row.get("boroughs") or [])) or "unknown"
        by_borough[borough_label].append(row)
    for borough_rows in by_borough.values():
        spot_check_samples.extend(borough_rows[:4])
    spot_check_samples = spot_check_samples[:24]

    return {
        "generated_at_utc": utc_now_iso(),
        "phase": "phase_b_calendar_only_review_findings",
        "input_count": len(queue),
        "classification_counts": dict(classification_counts),
        "likely_valid_parks_overlap_count": classification_counts.get("likely_valid_parks_overlap", 0),
        "needs_more_research_count": classification_counts.get("needs_more_research", 0),
        "recurring_program_instance_count": len(recurring_program_instances),
        "spot_check_sample_count": len(spot_check_samples),
        "spot_check_samples": [
            {
                "overlap_key": row.get("overlap_key"),
                "title": row.get("title"),
                "start_date_time": row.get("start_date_time"),
                "proposed_lat": row.get("proposed_lat"),
                "proposed_lng": row.get("proposed_lng"),
                "classification": row.get("classification"),
            }
            for row in spot_check_samples
        ],
        "priority_review_csv": repo_relative(CALENDAR_PRIORITY_CSV),
        "priority_review_count": len(priority_rows),
        "approved_for_supplemental_staging": [],
        "rejected_false_match": [],
        "needs_more_research": [
            row
            for row in classified_rows
            if row.get("classification") == "needs_more_research"
        ][:200],
        "likely_valid_parks_overlap": [
            row
            for row in classified_rows
            if row.get("classification") == "likely_valid_parks_overlap"
        ][:200],
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": (
            "Human spot-checks likely_valid_parks_overlap rows using priority CSV. "
            "Move approved rows into approved_for_supplemental_staging in a separate reviewed commit."
        ),
    }


def build_phase_c_findings() -> dict[str, Any]:
    queue = rows_from_payload(load_json_file(PARKS_QUEUE, {}), "review_queue")
    title_occurrences: Counter[str] = Counter()
    for row in queue:
        title_occurrences[recurring_title_key(str(row.get("title") or ""))] += 1

    classified: list[dict[str, Any]] = []
    for row in queue:
        recurrence = title_occurrences[recurring_title_key(str(row.get("title") or ""))]
        lat, lng = row_coords(row)
        if lat is None:
            bucket = "missing_coordinates"
            notes = "Parks BigApps row lacks valid NYC coordinates."
        elif row.get("calendar_title_date_match"):
            bucket = "already_represented_via_calendar"
            notes = "Also overlaps citywide calendar by title+date; coordinate with Phase B review."
        elif recurrence >= 5:
            bucket = "recurring_program_instances"
            notes = f"Recurring program title appears {recurrence} times in Parks-only queue."
        else:
            bucket = "high_value_unique_events"
            notes = "Distinct Parks-native event candidate for supplemental ingestion review."

        item = dict(row)
        item["classification"] = bucket
        item["review_notes"] = notes
        item["recurrence_count"] = recurrence
        item["promotion_allowed"] = False
        item["manual_review_status"] = "pending"
        classified.append(item)

    classification_counts = Counter(row.get("classification") for row in classified)
    missing_coords = [row for row in classified if row.get("classification") == "missing_coordinates"]
    recommended = [
        {
            "overlap_key": row.get("overlap_key"),
            "title": row.get("title"),
            "start_date_time": row.get("start_date_time"),
            "location": row.get("location"),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
        }
        for row in classified
        if row.get("classification") == "high_value_unique_events"
    ][:100]

    return {
        "generated_at_utc": utc_now_iso(),
        "phase": "phase_c_parks_only_review_findings",
        "input_count": len(queue),
        "classification_counts": dict(classification_counts),
        "high_value_unique_events_count": classification_counts.get("high_value_unique_events", 0),
        "recurring_program_instances_count": classification_counts.get("recurring_program_instances", 0),
        "already_represented_via_calendar_count": classification_counts.get(
            "already_represented_via_calendar", 0
        ),
        "missing_coordinates_count": classification_counts.get("missing_coordinates", 0),
        "missing_coordinates_rows": missing_coords,
        "recommended_supplemental_ingestion_candidates": recommended,
        "samples": {
            "high_value_unique_events": [
                row for row in classified if row.get("classification") == "high_value_unique_events"
            ][:10],
            "recurring_program_instances": [
                row for row in classified if row.get("classification") == "recurring_program_instances"
            ][:10],
        },
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "next_required_step": (
            "Review high_value_unique_events for supplemental ingestion. "
            "Skip recurring_program_instances for map pin density unless explicitly desired."
        ),
    }


def main() -> int:
    phase_a = build_phase_a_findings()
    phase_b = build_phase_b_findings()
    phase_c = build_phase_c_findings()

    save_json_file(GPS_FINDINGS, phase_a)
    save_json_file(CALENDAR_FINDINGS, phase_b)
    save_json_file(PARKS_FINDINGS, phase_c)

    summary = {
        "generated_at_utc": utc_now_iso(),
        "phase_a": {
            "unfilled_count": phase_a["input_count"],
            "ready_for_manual_reference_count": phase_a["ready_for_manual_reference_count"],
            "needs_human_field_verification_count": phase_a["needs_human_field_verification_count"],
        },
        "phase_b": {
            "calendar_only_count": phase_b["input_count"],
            "likely_valid_parks_overlap_count": phase_b["likely_valid_parks_overlap_count"],
            "needs_more_research_count": phase_b["needs_more_research_count"],
            "priority_review_csv": phase_b["priority_review_csv"],
        },
        "phase_c": {
            "parks_only_count": phase_c["input_count"],
            "classification_counts": phase_c["classification_counts"],
            "missing_coordinates_count": phase_c["missing_coordinates_count"],
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
