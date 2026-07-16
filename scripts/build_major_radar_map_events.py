#!/usr/bin/env python3
"""Rebuild nycif_major_radar_map_events.json from current desk priority rules.

Sources (in priority order):
  - Existing NYPD / field intel hard-writes (_hard_written rows preserved)
  - Parade census priority_events
  - Photographer assignment calendar (money_day)
  - Anchor registry highest/high entries

Does not modify protected feeds or location_cache.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, utc_now  # noqa: E402
import citywide_parade_census_common as census  # noqa: E402

MAJOR_RADAR_PATH = ROOT / "nycif_major_radar_map_events.json"
ALL_RADAR_PATH = ROOT / "nycif_all_radar_map_events.json"
CENSUS_PATH = DATA_DIR / "citywide_parade_census_snapshot.json"
PHOTO_CALENDAR_PATH = DATA_DIR / "photographer_assignment_calendar_2mo.json"
ANCHOR_REGISTRY_PATH = DATA_DIR / "nycif_citywide_parade_anchor_registry.json"
REPORT_PATH = DATA_DIR / "major_radar_rebuild_report.json"

FIELD_DESK_BASE = "https://setoxxx.github.io/nycif-field-desk/"


def field_desk_link(day: str | None, borough: str | None = None) -> str:
    params = [
        "v=civic-people-facing-v01",
        "resetFilters=1",
        "feeds=main",
        "mode=all",
        "assignment=1",
    ]
    if day:
        params.append(f"date={day}")
    b = census.queue_borough(borough)
    if b in {"Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"}:
        params.append(f"borough={quote(b)}")
    return f"{FIELD_DESK_BASE}?{'&'.join(params)}"


def load_existing_hard_writes(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict) and r.get("_hard_written")]


def build_geocode_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in (ALL_RADAR_PATH, MAJOR_RADAR_PATH):
        if not path.exists():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("source_event_id") or row.get("id") or "").strip()
            if pid.isdigit():
                index[pid] = row
            elif str(row.get("id") or "").startswith("nypd-"):
                index[str(row["id"])] = row
    return index


def infer_event_type(entry: dict[str, Any]) -> str:
    kind = str(entry.get("event_kind") or "")
    name = str(entry.get("name") or entry.get("title") or "")
    if kind == "street_co_naming" or re.search(r"co-?naming|naming ceremony", name, re.I):
        return "Street Co-Naming / Ceremony"
    if kind in {"fan_festival", "carnival"} or re.search(r"street fair|merchandise fair", name, re.I):
        return "Street Fair"
    if kind == "parade" or re.search(r"\bparade\b", name, re.I):
        return "Parade"
    return "Special Event"


def radar_row_from_entry(
    entry: dict[str, Any],
    *,
    geocode_index: dict[str, dict[str, Any]],
    source_tag: str,
) -> dict[str, Any] | None:
    day = str(entry.get("date") or "")[:10]
    if not day or not census.in_census_window(census.parse_iso_day(day)):
        return None
    title = str(entry.get("name") or entry.get("title") or "").strip()
    if not title:
        return None
    permit_id = str(entry.get("permit_event_id") or entry.get("source_event_id") or "").strip()
    priority = str(entry.get("editorial_priority") or "normal")
    if priority not in {"highest", "high"}:
        return None

    geo = geocode_index.get(permit_id) if permit_id.isdigit() else None
    lat = entry.get("latitude") or entry.get("lat") or (geo or {}).get("lat")
    lng = entry.get("longitude") or entry.get("lng") or (geo or {}).get("lng")
    location = (
        entry.get("route")
        or entry.get("display_location")
        or entry.get("location")
        or (geo or {}).get("display_location")
        or (geo or {}).get("location")
    )
    borough = census.queue_borough(entry.get("borough"))
    event_type = infer_event_type(entry)
    score = int(entry.get("assignment_score") or entry.get("priority_score") or 0)
    if priority == "highest":
        score = max(score, 400)
    elif priority == "high":
        score = max(score, 300)

    row = {
        "id": permit_id if permit_id.isdigit() else f"{source_tag}-{entry.get('anchor_key') or census.entry_dedupe_key(entry)}",
        "title": title,
        "date": day,
        "end_date": day,
        "start_time": entry.get("start_time") or "",
        "end_time": entry.get("end_time") or "",
        "start_date_time": day,
        "end_date_time": day,
        "borough": borough,
        "location": location or "",
        "display_location": location or "",
        "lat": lat,
        "lng": lng,
        "event_type": event_type,
        "photo_pick": priority in {"highest", "high"},
        "field_default": priority in {"highest", "high"},
        "assignment_feed": "major",
        "priority_score": score,
        "field_desk_link": field_desk_link(day, borough),
        "source_file": source_tag,
        "major_reason": f"{source_tag}:{priority}",
    }
    if permit_id.isdigit():
        row["source_event_id"] = permit_id
    if event_type == "Street Co-Naming / Ceremony":
        row["_manual_priority"] = "NYPD"
    return row


def merge_key(row: dict[str, Any]) -> str:
    pid = str(row.get("source_event_id") or "").strip()
    day = str(row.get("date") or "")[:10]
    if pid.isdigit() and day:
        return f"permit:{pid}@{day}"
    return f"id:{row.get('id')}@{day}"


def build_major_radar(
    *,
    census_path: Path | None = None,
    photo_path: Path | None = None,
    anchor_path: Path | None = None,
    existing_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    geocode_index = build_geocode_index()
    hard_writes = load_existing_hard_writes(existing_path or MAJOR_RADAR_PATH)
    hard_keys = {merge_key(r) for r in hard_writes}

    merged: dict[str, dict[str, Any]] = {}
    for row in hard_writes:
        merged[merge_key(row)] = row

    census_payload = load_json(census_path or CENSUS_PATH, {})
    for entry in census_payload.get("priority_events") or []:
        row = radar_row_from_entry(entry, geocode_index=geocode_index, source_tag="parade_census")
        if not row:
            continue
        key = merge_key(row)
        if key in hard_keys:
            continue
        merged[key] = row

    photo_payload = load_json(photo_path or PHOTO_CALENDAR_PATH, {})
    for event in photo_payload.get("events") or []:
        if not isinstance(event, dict) or not event.get("money_day"):
            continue
        score = int(event.get("assignment_score") or 0)
        if score < 300:
            continue
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        entry = {
            "name": event.get("title"),
            "date": event.get("date"),
            "borough": event.get("borough"),
            "permit_event_id": source.get("source_event_id"),
            "editorial_priority": "highest" if score >= 380 else "high",
            "assignment_score": score,
            "route": event.get("display_location"),
            "latitude": event.get("latitude"),
            "longitude": event.get("longitude"),
        }
        row = radar_row_from_entry(entry, geocode_index=geocode_index, source_tag="photographer_money_day")
        if not row:
            continue
        key = merge_key(row)
        if key in hard_keys:
            continue
        existing = merged.get(key)
        if existing and int(existing.get("priority_score") or 0) >= int(row.get("priority_score") or 0):
            continue
        merged[key] = row

    registry = census.load_anchor_registry(anchor_path or ANCHOR_REGISTRY_PATH)
    for anchor in registry.get("anchors") or []:
        if str(anchor.get("editorial_priority") or "normal") not in {"highest", "high"}:
            continue
        entry = census.census_entry_from_anchor(anchor)
        row = radar_row_from_entry(entry, geocode_index=geocode_index, source_tag="editorial_anchor")
        if not row:
            continue
        key = merge_key(row)
        if key in hard_keys:
            continue
        existing = merged.get(key)
        if existing and str(existing.get("major_reason", "")).startswith("parade_census"):
            continue
        merged[key] = row

    rows = sorted(
        merged.values(),
        key=lambda r: (
            census.EDITORIAL_PRIORITY_RANK.get(
                "highest" if r.get("_manual_priority") == "NYPD" else "high" if r.get("field_default") else "normal",
                9,
            ),
            -int(r.get("priority_score") or 0),
            r.get("date") or "",
            r.get("title") or "",
        ),
    )

    report = {
        "schema_version": "major-radar-rebuild-report-v1",
        "generated_at_utc": utc_now(),
        "qa_pass": len(rows) > 0 and len(hard_writes) > 0,
        "total_rows": len(rows),
        "hard_written_preserved": len(hard_writes),
        "generated_rows": len(rows) - len(hard_writes),
        "output_path": "nycif_major_radar_map_events.json",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    return rows, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census-path", default=str(CENSUS_PATH))
    parser.add_argument("--photo-path", default=str(PHOTO_CALENDAR_PATH))
    parser.add_argument("--anchor-path", default=str(ANCHOR_REGISTRY_PATH))
    parser.add_argument("--existing-path", default=str(MAJOR_RADAR_PATH))
    args = parser.parse_args()

    rows, report = build_major_radar(
        census_path=Path(args.census_path),
        photo_path=Path(args.photo_path),
        anchor_path=Path(args.anchor_path),
        existing_path=Path(args.existing_path),
    )
    save_json(MAJOR_RADAR_PATH, rows)
    save_json(REPORT_PATH, report)
    print(
        f"major radar rebuild total={report['total_rows']} "
        f"hard_writes={report['hard_written_preserved']} generated={report['generated_rows']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
