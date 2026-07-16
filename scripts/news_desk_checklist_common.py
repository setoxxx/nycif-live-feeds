#!/usr/bin/env python3
"""Shared helpers for NYCIF News Desk assignment checklist (staging only)."""

from __future__ import annotations

import csv
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from civic_people_facing_common import parse_clock_time, resolve_coordinate_status, today_nyc
from schema_v1_common import borough_label, norm_text

import citywide_parade_census_common as census

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CENSUS_PATH = DATA_DIR / "citywide_parade_census_snapshot.json"
PHOTO_CALENDAR_PATH = DATA_DIR / "photographer_assignment_calendar_2mo.json"
MAJOR_RADAR_PATH = ROOT / "nycif_major_radar_map_events.json"
ALL_RADAR_PATH = ROOT / "nycif_all_radar_map_events.json"
DISCOVERY_MAJOR_PATH = DATA_DIR / "events_discovery_v02_major.json"
VIRAL_MATCHES_PATH = DATA_DIR / "photographer_viral_recurrence_matches.json"
ANCHOR_REGISTRY_PATH = census.ANCHOR_REGISTRY_PATH

FIELD_DESK_BASE = "https://setoxxx.github.io/nycif-field-desk/"

STORY_LANES = (
    "parade_march",
    "religious_procession_feast",
    "street_co_naming",
    "heritage_cultural_parade",
    "pop_up_street_activation",
    "fan_zone_major_civic",
    "returning_viral_candidate",
)

NEWS_DESK_STATUSES = frozenset({"unchecked", "assigned", "covered", "passed", "cancelled"})

POP_UP_RE = re.compile(
    r"street fair|merchandise fair|block party|open street|plaza programming|"
    r"fan zone|fan festival|activation|pop-?up|feast|festival|curlfest|greenmarket|"
    r"farmers market|street market|flea market",
    re.I,
)

HERITAGE_RE = re.compile(
    r"colombian|dominican|india day|african american|mexican day|panamanian|"
    r"hispanic day|pulaski|nigerian|korean parade|heritage parade|cultural parade",
    re.I,
)

FEAST_RE = re.compile(
    r"giglio|san gennaro|ferragosto|rath yatra|jagannath|religious procession|"
    r"icon procession|feast of|our lady",
    re.I,
)

EXCLUDE_TITLE_RE = re.compile(
    r"\b(rehearsal|practice session|closed|field day|shape up|yoga|zumba|"
    r"softball|baseball|soccer practice|learn to swim)\b",
    re.I,
)

CO_NAMING_RE = re.compile(r"co-?naming|c0-naming|street naming|naming ceremony", re.I)

LANE_PRIORITY = {
    "street_co_naming": 0,
    "religious_procession_feast": 1,
    "heritage_cultural_parade": 2,
    "fan_zone_major_civic": 3,
    "parade_march": 4,
    "pop_up_street_activation": 5,
    "returning_viral_candidate": 6,
}


def load_json_list(path: Path, *keys: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    for key in keys or ("events", "entries", "rows", "matches"):
        val = payload.get(key)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    return []


def clean_headline(title: str) -> str:
    text = str(title or "").strip()
    text = re.sub(r"\bC0-Naming\b", "Co-Naming", text, flags=re.I)
    text = re.sub(r"\bC0 Naming\b", "Co-Naming", text, flags=re.I)
    if re.search(r"co-?naming|naming ceremony", text, re.I) and "ceremony" not in text.lower():
        text = f"{text} Ceremony"
    return text


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
    b = borough_label(borough) if borough else None
    if b in {"Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"}:
        params.append(f"borough={quote(b)}")
    return f"{FIELD_DESK_BASE}?{'&'.join(params)}"


def infer_story_lane(
    *,
    title: str,
    event_kind: str | None = None,
    category: str | None = None,
    event_type: str | None = None,
    viral: bool = False,
) -> str:
    if viral:
        return "returning_viral_candidate"
    if CO_NAMING_RE.search(title):
        return "street_co_naming"
    kind = str(event_kind or "")
    if kind in {"street_co_naming", "civic_dedication"}:
        return "street_co_naming"
    if str(event_type or "") == "Street Co-Naming / Ceremony":
        return "street_co_naming"
    if kind in {"religious_procession", "procession", "street_festival_procession"} or FEAST_RE.search(title):
        return "religious_procession_feast"
    if HERITAGE_RE.search(title) or kind == "cultural_march":
        return "heritage_cultural_parade"
    if kind in {
        "fan_festival",
        "balloon_inflation",
        "new_years_gathering",
        "ceremonial_race",
        "ticker_tape_parade",
        "carnival",
        "pride_march",
    }:
        return "fan_zone_major_civic"
    if POP_UP_RE.search(title):
        return "pop_up_street_activation"
    if kind in {"parade", "march", "halloween_parade", "holiday_parade", "veterans_procession"}:
        return "parade_march"
    if str(event_type or "") == "Parade" or re.search(r"\bparade\b|\bmarch\b", title, re.I):
        return "parade_march"
    return "parade_march"


def build_geocode_index() -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for path in (ALL_RADAR_PATH, MAJOR_RADAR_PATH):
        for row in load_json_list(path):
            pid = str(row.get("source_event_id") or "").strip()
            if not pid or not pid.isdigit():
                continue
            lat = row.get("latitude") or row.get("lat")
            lng = row.get("longitude") or row.get("lng")
            if pid not in index or (lat is not None and lng is not None):
                index[pid] = {
                    "latitude": lat,
                    "longitude": lng,
                    "display_location": row.get("display_location") or row.get("location"),
                }
    return index


def attach_coordinates(row: dict[str, Any], geocode_index: dict[str, dict[str, Any]]) -> dict[str, Any]:
    updated = dict(row)
    lat = updated.get("latitude")
    lng = updated.get("longitude")
    pid = str(updated.get("permit_event_id") or "").strip()
    if (lat is None or lng is None) and pid and pid in geocode_index:
        geo = geocode_index[pid]
        lat = geo.get("latitude")
        lng = geo.get("longitude")
        if not updated.get("route_or_location"):
            updated["route_or_location"] = geo.get("display_location")
    lat_f, lng_f, status, _ = resolve_coordinate_status(lat, lng)
    updated["latitude"] = lat_f
    updated["longitude"] = lng_f
    updated["coordinate_status"] = status
    return updated


def merge_key(row: dict[str, Any]) -> str:
    pid = str(row.get("permit_event_id") or "").strip()
    day = str(row.get("date") or "")
    if pid and day:
        return f"permit:{pid}@{day}"
    anchor = row.get("anchor_key")
    if anchor and day:
        return f"anchor:{anchor}@{day}"
    title = norm_text(str(row.get("story_headline") or ""))
    borough = norm_text(str(row.get("borough") or ""))
    return f"title:{title}@{day}@{borough}"


def _priority_rank(value: str | None) -> int:
    return census.EDITORIAL_PRIORITY_RANK.get(str(value or "normal"), 9)


def merge_rows(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, val in incoming.items():
        if val is None:
            continue
        if key == "why_story":
            tags = set(merged.get("why_story") or [])
            tags.update(incoming.get("why_story") or [])
            merged["why_story"] = sorted(tags)
            continue
        if key == "assignment_score":
            merged["assignment_score"] = max(
                int(merged.get("assignment_score") or 0),
                int(incoming.get("assignment_score") or 0),
            )
            continue
        if key == "editorial_priority":
            if _priority_rank(incoming.get("editorial_priority")) <= _priority_rank(
                merged.get("editorial_priority")
            ):
                merged["editorial_priority"] = incoming["editorial_priority"]
            continue
        if key in {"latitude", "longitude", "route_or_location", "neighborhood"} and merged.get(key):
            continue
        if key == "story_lane":
            cur = str(merged.get("story_lane") or "parade_march")
            new = str(val or "parade_march")
            if LANE_PRIORITY.get(new, 9) < LANE_PRIORITY.get(cur, 9):
                merged["story_lane"] = new
            continue
        merged[key] = val
    return merged


def base_row(
    *,
    headline: str,
    day: str | None,
    borough: str | None,
    lane: str,
    priority: str = "normal",
    confidence: str = "provisional",
    permit_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    route: str | None = None,
    neighborhood: str | None = None,
    assignment_score: int = 0,
    why_story: list[str] | None = None,
    source_layer: str,
    anchor_key: str | None = None,
    raw_title: str | None = None,
    latitude: Any = None,
    longitude: Any = None,
) -> dict[str, Any]:
    b = census.queue_borough(borough)
    clean = clean_headline(headline)
    row = {
        "checklist_id": None,
        "story_headline": clean,
        "story_lane": lane if lane in STORY_LANES else "parade_march",
        "date": day,
        "start_time": start_time,
        "end_time": end_time,
        "borough": b,
        "neighborhood": neighborhood,
        "route_or_location": route,
        "permit_event_id": permit_id,
        "editorial_priority": priority,
        "news_desk_status": "unchecked",
        "confidence": confidence,
        "assignment_score": assignment_score,
        "why_story": sorted(set(why_story or [])),
        "field_desk_link": field_desk_link(day, b),
        "latitude": latitude,
        "longitude": longitude,
        "coordinate_status": "list_only",
        "calendar_eligible": True,
        "map_eligible": False,
        "checked_by": None,
        "checked_at_utc": None,
        "notes": None,
        "source_layer": source_layer,
        "anchor_key": anchor_key,
        "raw_title": raw_title or headline,
    }
    pid = str(permit_id or "").strip()
    if pid and day:
        row["checklist_id"] = f"tvpp-9vvx:{pid}@{day}"
    elif anchor_key and day:
        row["checklist_id"] = f"anchor:{anchor_key}@{day}"
    else:
        row["checklist_id"] = merge_key(row)
    return row


def row_from_census_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    day = str(entry.get("date") or "")[:10] or None
    if day and not census.in_census_window(census.parse_iso_day(day)):
        return None
    title = entry.get("name") or "Untitled event"
    if EXCLUDE_TITLE_RE.search(str(title)):
        return None
    lane = infer_story_lane(
        title=str(title),
        event_kind=entry.get("event_kind"),
    )
    why = [str(entry.get("source_layer") or "parade_census")]
    if entry.get("priority_reason"):
        why.append(str(entry["priority_reason"]))
    if entry.get("event_kind"):
        why.append(str(entry["event_kind"]))
    return base_row(
        headline=str(title),
        day=day,
        borough=entry.get("borough"),
        lane=lane,
        priority=str(entry.get("editorial_priority") or "normal"),
        confidence=str(entry.get("confidence") or "provisional"),
        permit_id=entry.get("permit_event_id"),
        start_time=entry.get("start_time"),
        end_time=entry.get("end_time"),
        route=entry.get("route"),
        neighborhood=entry.get("neighborhood"),
        assignment_score=int(entry.get("assignment_score") or 0),
        why_story=why,
        source_layer=str(entry.get("source_layer") or "parade_census"),
        anchor_key=entry.get("anchor_key"),
        raw_title=str(entry.get("permit_match_name") or title),
    )


def row_from_photo_event(event: dict[str, Any]) -> dict[str, Any] | None:
    day = str(event.get("date") or "")[:10] or None
    if not day or not census.in_census_window(census.parse_iso_day(day)):
        return None
    title = str(event.get("title") or "")
    if EXCLUDE_TITLE_RE.search(title):
        return None
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    permit_id = str(source.get("source_event_id") or "").strip() or None
    lane = infer_story_lane(title=title, category=str(event.get("category") or ""))
    priority = "normal"
    score = int(event.get("assignment_score") or 0)
    if event.get("money_day") and score >= 380:
        priority = "highest"
    elif event.get("money_day") or score >= 300:
        priority = "high"
    return base_row(
        headline=title,
        day=day,
        borough=event.get("borough"),
        lane=lane,
        priority=priority,
        confidence="permit_confirmed" if permit_id else "strongly_supported",
        permit_id=permit_id,
        start_time=census.hhmm_from_datetime(event.get("start_date_time")),
        end_time=census.hhmm_from_datetime(event.get("end_date_time")),
        route=event.get("display_location"),
        assignment_score=score,
        why_story=["photographer_money_day"] if event.get("money_day") else ["photographer_assignment_calendar"],
        source_layer="photographer_assignment_calendar",
        raw_title=title,
        latitude=event.get("latitude"),
        longitude=event.get("longitude"),
    )


def row_from_radar_event(row: dict[str, Any]) -> dict[str, Any] | None:
    day = str(row.get("date") or row.get("start_date_time") or "")[:10]
    if not day or not census.in_census_window(census.parse_iso_day(day)):
        return None
    title = str(row.get("title") or "")
    if EXCLUDE_TITLE_RE.search(title):
        return None
    permit_id = str(row.get("source_event_id") or row.get("id") or "").strip()
    if not permit_id.isdigit():
        permit_id = ""
    permit_id = permit_id or None
    event_type = str(row.get("event_type") or "")
    lane = infer_story_lane(title=title, event_type=event_type)
    priority = "normal"
    if event_type == "Street Co-Naming / Ceremony" or row.get("_manual_priority") == "NYPD":
        priority = "highest"
        lane = "street_co_naming"
    elif row.get("field_default") or row.get("assignment_feed") == "major":
        priority = "high"
    elif row.get("photo_pick"):
        priority = "high"
    start_time = None
    if row.get("start_time"):
        clock = parse_clock_time(str(row.get("start_time")))
        if clock:
            start_time = f"{clock[0]:02d}:{clock[1]:02d}"
    return base_row(
        headline=title,
        day=day,
        borough=row.get("borough"),
        lane=lane,
        priority=priority,
        confidence="permit_confirmed" if permit_id else "strongly_supported",
        permit_id=permit_id,
        start_time=start_time,
        route=row.get("display_location") or row.get("location"),
        assignment_score=int(row.get("priority_score") or row.get("expected_crowd_score") or 0),
        why_story=["major_radar", event_type.lower().replace(" ", "_") if event_type else "radar"],
        source_layer="major_radar",
        raw_title=title,
        latitude=row.get("lat") or row.get("latitude"),
        longitude=row.get("lng") or row.get("longitude"),
    )


def row_from_discovery_major(event: dict[str, Any]) -> dict[str, Any] | None:
    day = str(event.get("start_date_time") or "")[:10]
    if not day or not census.in_census_window(census.parse_iso_day(day)):
        return None
    title = str(event.get("title") or "")
    if not POP_UP_RE.search(title) or EXCLUDE_TITLE_RE.search(title):
        return None
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    permit_id = str(source.get("source_event_id") or "").strip() or None
    return base_row(
        headline=title,
        day=day,
        borough=event.get("borough"),
        lane="pop_up_street_activation",
        priority="high" if event.get("significance") == "major" else "normal",
        confidence="permit_confirmed" if permit_id else "strongly_supported",
        permit_id=permit_id,
        start_time=census.hhmm_from_datetime(event.get("start_date_time")),
        end_time=census.hhmm_from_datetime(event.get("end_date_time")),
        route=event.get("location"),
        assignment_score=300 if event.get("significance") == "major" else 0,
        why_story=["discovery_major_pop_up"],
        source_layer="discovery_major",
        raw_title=title,
        latitude=event.get("latitude"),
        longitude=event.get("longitude"),
    )


def row_from_viral_match(match: dict[str, Any]) -> dict[str, Any] | None:
    day = str(match.get("current_date") or match.get("date") or "")[:10]
    if not day or not census.in_census_window(census.parse_iso_day(day)):
        return None
    title = str(match.get("current_title") or match.get("title") or "")
    if EXCLUDE_TITLE_RE.search(title):
        return None
    permit_id = str(match.get("current_source_event_id") or match.get("source_event_id") or "").strip() or None
    return base_row(
        headline=title,
        day=day,
        borough=match.get("borough"),
        lane="returning_viral_candidate",
        priority="high",
        confidence="strongly_supported",
        permit_id=permit_id,
        route=match.get("display_location") or match.get("location"),
        assignment_score=int(match.get("assignment_score") or 280),
        why_story=["viral_recurrence", str(match.get("label") or "returning_likely")],
        source_layer="viral_recurrence",
        raw_title=title,
    )


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda r: (
            _priority_rank(r.get("editorial_priority")),
            -int(r.get("assignment_score") or 0),
            r.get("date") or "9999-99-99",
            r.get("borough") or "",
            r.get("story_headline") or "",
        ),
    )


def group_by_borough(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {
        "Manhattan": [],
        "Brooklyn": [],
        "Queens": [],
        "Bronx": [],
        "Staten Island": [],
        "Multi-borough": [],
    }
    for row in rows:
        b = row.get("borough") or "Multi-borough"
        if b not in buckets:
            b = "Multi-borough"
        buckets[b].append(row)
    for key in buckets:
        buckets[key] = sort_rows(buckets[key])
    return buckets


def group_by_lane(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {lane: [] for lane in STORY_LANES}
    for row in rows:
        lane = row.get("story_lane") or "parade_march"
        if lane not in buckets:
            lane = "parade_march"
        buckets[lane].append(row)
    for key in buckets:
        buckets[key] = sort_rows(buckets[key])
    return buckets


def date_window_slices(
    rows: list[dict[str, Any]], *, today: date
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    today_s = today.isoformat()
    tomorrow_s = (today + timedelta(days=1)).isoformat()
    end_7 = (today + timedelta(days=7)).isoformat()
    end_14 = (today + timedelta(days=14)).isoformat()
    today_rows: list[dict[str, Any]] = []
    tomorrow_rows: list[dict[str, Any]] = []
    next_7: list[dict[str, Any]] = []
    next_14: list[dict[str, Any]] = []
    for row in rows:
        day = str(row.get("date") or "")
        if not day:
            continue
        if day == today_s:
            today_rows.append(row)
        if day == tomorrow_s:
            tomorrow_rows.append(row)
        if today_s <= day <= end_7:
            next_7.append(row)
        if today_s <= day <= end_14:
            next_14.append(row)
    return sort_rows(today_rows), sort_rows(tomorrow_rows), sort_rows(next_7), sort_rows(next_14)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "checklist_id",
        "story_headline",
        "story_lane",
        "date",
        "start_time",
        "end_time",
        "borough",
        "route_or_location",
        "editorial_priority",
        "news_desk_status",
        "confidence",
        "assignment_score",
        "permit_event_id",
        "field_desk_link",
        "coordinate_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fields})
