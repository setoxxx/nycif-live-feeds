#!/usr/bin/env python3
"""Build NYCIF News Desk assignment checklist (Jul 16–Dec 31, 2026).

Merges parade census, photographer money-day desk, major radar, discovery major,
and viral recurrence into a daily-refreshed editorial checklist.
Staging only — never promotes to public map or location_cache.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, safety_fields, save_json, today_nyc, utc_now  # noqa: E402
import citywide_parade_census_common as census  # noqa: E402
import news_desk_checklist_common as nd  # noqa: E402

CHECKLIST_PATH = DATA_DIR / "news_desk_assignment_checklist.json"
REPORT_PATH = DATA_DIR / "news_desk_assignment_checklist_report.json"
CSV_PATH = DATA_DIR / "news_desk_assignment_checklist.csv"


def upsert(store: dict[str, dict[str, Any]], row: dict[str, Any] | None) -> None:
    if not row:
        return
    key = nd.merge_key(row)
    if key in store:
        store[key] = nd.merge_rows(store[key], row)
    else:
        store[key] = row


def build_checklist(
    *,
    reference_today: date | None = None,
    census_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    today = reference_today or today_nyc()
    geocode_index = nd.build_geocode_index()
    merged: dict[str, dict[str, Any]] = {}

    census_payload = load_json(census_path or nd.CENSUS_PATH, {})
    census_entries = list(census_payload.get("entries") or [])
    priority_events = list(census_payload.get("priority_events") or [])
    seen_ids = {id(e) for e in census_entries}
    for event in priority_events:
        if id(event) not in seen_ids:
            census_entries.append(event)

    for entry in census_entries:
        upsert(merged, nd.row_from_census_entry(entry))

    photo_payload = load_json(nd.PHOTO_CALENDAR_PATH, {})
    for event in photo_payload.get("events") or []:
        if not isinstance(event, dict):
            continue
        if not event.get("money_day"):
            continue
        upsert(merged, nd.row_from_photo_event(event))

    for row in nd.load_json_list(nd.MAJOR_RADAR_PATH):
        upsert(merged, nd.row_from_radar_event(row))

    for event in nd.load_json_list(nd.DISCOVERY_MAJOR_PATH, "events"):
        upsert(merged, nd.row_from_discovery_major(event))

    for match in nd.load_json_list(nd.VIRAL_MATCHES_PATH, "matches"):
        upsert(merged, nd.row_from_viral_match(match))

    all_rows = [nd.attach_coordinates(row, geocode_index) for row in merged.values()]
    all_rows = nd.sort_rows(all_rows)

    today_rows, tomorrow_rows, next_7, next_14 = nd.date_window_slices(all_rows, today=today)
    priority_unchecked = [
        r
        for r in all_rows
        if r.get("news_desk_status") == "unchecked"
        and str(r.get("editorial_priority") or "normal") in {"highest", "high"}
    ]

    anchor_watchlist = [
        nd.attach_coordinates(nd.row_from_census_entry(entry), geocode_index)
        for entry in census_entries
        if entry.get("anchor_key")
        and entry.get("permit_status") in {"not_yet_matched", "anchor_only"}
    ]
    anchor_watchlist = [r for r in anchor_watchlist if r]

    permit_only = [
        r
        for r in all_rows
        if r.get("source_layer") == "permit_extract" or "permit_only" in (r.get("why_story") or [])
    ]

    by_borough = nd.group_by_borough(all_rows)
    by_story_lane = nd.group_by_lane(all_rows)

    map_eligible_count = sum(1 for r in all_rows if r.get("map_eligible"))
    map_ready_count = sum(1 for r in all_rows if r.get("coordinate_status") == "map_ready")
    duplicate_ids = len(all_rows) - len({r.get("checklist_id") for r in all_rows})

    odb = next(
        (
            r
            for r in all_rows
            if r.get("anchor_key") == "odb-street-co-naming"
            or r.get("permit_event_id") == "945819"
        ),
        None,
    )

    qa_pass = (
        odb is not None
        and odb.get("editorial_priority") == "highest"
        and odb.get("story_lane") == "street_co_naming"
        and map_eligible_count == 0
        and duplicate_ids == 0
        and len(all_rows) > 0
        and all(r.get("field_desk_link") for r in all_rows)
        and all(r.get("story_lane") in nd.STORY_LANES for r in all_rows)
        and all(r.get("news_desk_status") in nd.NEWS_DESK_STATUSES for r in all_rows)
    )

    checklist = {
        "schema_version": "news-desk-assignment-checklist-v1",
        "window_start": census.WINDOW_START.isoformat(),
        "window_end": census.WINDOW_END.isoformat(),
        "generated_at_utc": utc_now(),
        "today_nyc": today.isoformat(),
        "today": today_rows,
        "tomorrow": tomorrow_rows,
        "next_7_days": next_7,
        "next_14_days": next_14,
        "priority_unchecked": priority_unchecked,
        "by_borough": by_borough,
        "by_story_lane": by_story_lane,
        "anchor_watchlist": nd.sort_rows(anchor_watchlist),
        "permit_only_discoveries": nd.sort_rows(permit_only),
        "all_rows": all_rows,
        "counts": {
            "total": len(all_rows),
            "today_count": len(today_rows),
            "tomorrow_count": len(tomorrow_rows),
            "next_7_days_count": len(next_7),
            "next_14_days_count": len(next_14),
            "priority_unchecked_count": len(priority_unchecked),
            "anchor_watchlist_count": len(anchor_watchlist),
            "map_ready_count": map_ready_count,
            "list_only_count": len(all_rows) - map_ready_count,
            "borough_counts": {b: len(rows) for b, rows in by_borough.items() if rows},
            "story_lane_counts": {lane: len(rows) for lane, rows in by_story_lane.items() if rows},
            "editorial_priority_counts": dict(Counter(r.get("editorial_priority") for r in all_rows)),
        },
        "field_desk_base": nd.FIELD_DESK_BASE,
        "assignment_mode_link": nd.field_desk_link(today.isoformat()),
        "notes": (
            "News Desk assignment checklist for parades, feasts, co-namings, pop-ups, and "
            "signature civic stories. Staging/editorial only — map_eligible remains false."
        ),
        **safety_fields(),
    }

    report = {
        "schema_version": "news-desk-assignment-checklist-report-v1",
        "generated_at_utc": checklist["generated_at_utc"],
        "qa_pass": qa_pass,
        "today_nyc": today.isoformat(),
        "total_rows": len(all_rows),
        "today_count": len(today_rows),
        "priority_unchecked_count": len(priority_unchecked),
        "map_eligible_count": map_eligible_count,
        "map_ready_count": map_ready_count,
        "duplicate_checklist_ids": duplicate_ids,
        "odb_present": odb is not None,
        "odb_editorial_priority": odb.get("editorial_priority") if odb else None,
        "odb_story_lane": odb.get("story_lane") if odb else None,
        "checks": {
            "odb_highest_street_co_naming": bool(
                odb and odb.get("editorial_priority") == "highest" and odb.get("story_lane") == "street_co_naming"
            ),
            "all_map_eligible_false": map_eligible_count == 0,
            "no_duplicate_checklist_ids": duplicate_ids == 0,
            "all_rows_have_field_desk_link": all(r.get("field_desk_link") for r in all_rows),
        },
        "snapshot_path": "data/news_desk_assignment_checklist.json",
        "csv_path": "data/news_desk_assignment_checklist.csv",
        "census_path": "data/citywide_parade_census_snapshot.json",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    return checklist, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None, help="YYYY-MM-DD for date windows")
    parser.add_argument("--census-path", default=str(nd.CENSUS_PATH))
    args = parser.parse_args()

    ref_today = date.fromisoformat(args.reference_today) if args.reference_today else None
    checklist, report = build_checklist(
        reference_today=ref_today,
        census_path=Path(args.census_path),
    )
    save_json(CHECKLIST_PATH, checklist)
    save_json(REPORT_PATH, report)
    nd.write_csv(CSV_PATH, checklist["all_rows"])

    print(
        f"news desk checklist qa_pass={report['qa_pass']} "
        f"total={report['total_rows']} priority_unchecked={report['priority_unchecked_count']} "
        f"today={report['today_count']} map_ready={report['map_ready_count']}"
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
