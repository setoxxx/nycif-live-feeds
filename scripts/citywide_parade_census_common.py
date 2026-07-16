#!/usr/bin/env python3
"""Shared helpers for NYCIF citywide parade / procession / civic-event census."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from civic_people_facing_common import parse_clock_time
from schema_v1_common import borough_label, norm_text

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANCHOR_REGISTRY_PATH = DATA_DIR / "nycif_citywide_parade_anchor_registry.json"
PERMIT_SNAPSHOT_PATH = DATA_DIR / "raw_nyc_open_data_snapshot.json"

WINDOW_START = date(2026, 7, 16)
WINDOW_END = date(2026, 12, 31)

BOROUGH_QUEUES = (
    "Manhattan",
    "Brooklyn",
    "Queens",
    "Bronx",
    "Staten Island",
    "Multi-borough",
    "Metropolitan reference outside NYC",
)

CONFIDENCE_LEVELS = frozenset(
    {
        "confirmed",
        "permit_confirmed",
        "strongly_supported",
        "provisional",
        "historical_pattern_only",
        "rejected_cancelled",
    }
)

PERMIT_STATUSES = frozenset(
    {
        "not_yet_matched",
        "permit_matched",
        "permit_only",
        "anchor_only",
        "rejected_cancelled",
    }
)

# Title/location patterns for census inclusion (not only event_type == Parade).
EVENT_KIND_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("parade", re.compile(r"\bparade\b", re.I)),
    ("march", re.compile(r"\bmarch\b", re.I)),
    ("procession", re.compile(r"\bprocession\b|\bbaraat\b|\bgiglio\b", re.I)),
    ("motorcade", re.compile(r"\bmotorcade\b", re.I)),
    ("cavalcade", re.compile(r"\bcavalcade\b", re.I)),
    ("religious_procession", re.compile(r"religious procession|icon procession|rath yatra|jagannath", re.I)),
    ("funeral_procession", re.compile(r"funeral procession", re.I)),
    ("cultural_march", re.compile(r"cultural march|heritage parade|unity walk", re.I)),
    ("halloween_parade", re.compile(r"halloween parade", re.I)),
    ("holiday_parade", re.compile(r"holiday parade|tree.?lighting|santa parade|toy drive", re.I)),
    ("veterans_procession", re.compile(r"veterans day|veterans parade|veterans procession", re.I)),
    ("pet_parade", re.compile(r"pet parade|blessing of the animals", re.I)),
    ("bike_parade", re.compile(r"bike parade|critical mass", re.I)),
    ("boat_parade", re.compile(r"boat parade", re.I)),
    ("carnival", re.compile(r"\bcarnival\b|j.?ouvert|west indian", re.I)),
    ("ceremonial_race", re.compile(r"\bmarathon\b|\b5k\b|\b10k\b|turkey trot|cancer walk|walkathon", re.I)),
    ("ticker_tape_parade", re.compile(r"ticker.?tape", re.I)),
    ("marching_band_event", re.compile(r"marching band", re.I)),
    ("school_parade", re.compile(r"school parade|youth parade|back.?to.?school parade", re.I)),
    ("block_procession", re.compile(r"block procession|neighborhood parade", re.I)),
    ("political_march", re.compile(r"political march|demonstration march|election day", re.I)),
    ("pride_march", re.compile(r"\bpride\b", re.I)),
    ("lantern_procession", re.compile(r"lantern procession|mid.?autumn", re.I)),
    ("new_years_gathering", re.compile(r"new year|ball drop|times square celebration", re.I)),
    ("street_festival_procession", re.compile(r"ferragosto|san gennaro|powwow", re.I)),
    ("fan_festival", re.compile(r"curlfest|fan festival|fan zone", re.I)),
    ("balloon_inflation", re.compile(r"balloon inflation", re.I)),
]

CENSUS_INCLUDE_RE = re.compile(
    "|".join(f"(?:{p.pattern})" for _, p in EVENT_KIND_RULES),
    re.I,
)

EXCLUDE_LOCATION_RE = re.compile(r"\bparade ground\b", re.I)
EXCLUDE_TITLE_RE = re.compile(
    r"\b(rehearsal|practice session|closed|field day)\b",
    re.I,
)

OPEN_DATA_PARADE_TYPES = frozenset({"Parade", "Street Festival", "Street Event"})


def load_anchor_registry(path: Path | None = None) -> dict[str, Any]:
    payload = json.loads((path or ANCHOR_REGISTRY_PATH).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "anchors" not in payload:
        raise ValueError("anchor registry must be an object with anchors[]")
    return payload


def load_permit_rows(path: Path | None = None) -> list[dict[str, Any]]:
    payload = json.loads((path or PERMIT_SNAPSHOT_PATH).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("events") or []
        return [r for r in rows if isinstance(r, dict)]
    return []


def parse_iso_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def in_census_window(day: date | None) -> bool:
    return day is not None and WINDOW_START <= day <= WINDOW_END


def queue_borough(raw: str | None) -> str:
    label = borough_label(raw) if raw else None
    if label in BOROUGH_QUEUES[:5]:
        return label
    text = norm_text(str(raw or ""))
    if not text or text in {"citywide", "all boroughs", "all five boroughs", "nyc"}:
        return "Multi-borough"
    if "/" in str(raw or ""):
        return "Multi-borough"
    if "randall" in text:
        return "Manhattan"
    if label:
        return label
    return "Multi-borough"


def hhmm_from_datetime(value: Any) -> str | None:
    text = str(value or "").strip()
    if "T" not in text:
        return None
    clock = text.split("T", 1)[1][:12]
    parsed = parse_clock_time(clock.replace(".000", ""))
    if not parsed:
        return None
    hour, minute, _ = parsed
    return f"{hour:02d}:{minute:02d}"


def infer_event_kind(blob: str, event_type: str | None = None) -> str:
    if str(event_type or "").strip() == "Parade":
        return "parade"
    for kind, pattern in EVENT_KIND_RULES:
        if pattern.search(blob):
            return kind
    return "parade"


def permit_blob(row: dict[str, Any]) -> str:
    parts = [
        row.get("event_name"),
        row.get("event_type"),
        row.get("event_location"),
        row.get("street_closure_type"),
        row.get("event_agency"),
    ]
    return norm_text(" ".join(str(p) for p in parts if p))


def is_census_candidate(row: dict[str, Any]) -> tuple[bool, str]:
    day = parse_iso_day(row.get("start_date_time"))
    if not in_census_window(day):
        return False, "outside_window"
    blob = permit_blob(row)
    if EXCLUDE_LOCATION_RE.search(blob):
        return False, "parade_ground_excluded"
    title = norm_text(str(row.get("event_name") or ""))
    if EXCLUDE_TITLE_RE.search(title):
        return False, "rehearsal_or_closed_excluded"
    event_type = str(row.get("event_type") or "")
    if event_type == "Parade":
        return True, "event_type_parade"
    if event_type in OPEN_DATA_PARADE_TYPES and CENSUS_INCLUDE_RE.search(blob):
        return True, "typed_street_event_with_census_keyword"
    if CENSUS_INCLUDE_RE.search(blob):
        return True, "census_keyword_match"
    return False, "no_match"


def census_entry_from_permit(row: dict[str, Any], *, match_reason: str) -> dict[str, Any]:
    day = parse_iso_day(row.get("start_date_time"))
    blob = permit_blob(row)
    borough = queue_borough(row.get("event_borough"))
    return {
        "name": str(row.get("event_name") or "").strip(),
        "date": day.isoformat() if day else None,
        "start_time": hhmm_from_datetime(row.get("start_date_time")),
        "end_time": hhmm_from_datetime(row.get("end_date_time")),
        "borough": borough,
        "neighborhood": None,
        "route": str(row.get("event_location") or "").strip() or None,
        "event_kind": infer_event_kind(blob, row.get("event_type")),
        "permit_event_id": str(row.get("source_event_id") or "").strip() or None,
        "permit_status": "permit_only",
        "official_source": "nyc_open_data_tvpp-9vvx",
        "confidence": "permit_confirmed",
        "editorial_priority": "normal",
        "calendar_eligible": True,
        "map_eligible": False,
        "source_layer": "permit_extract",
        "match_reason": match_reason,
        "event_agency": row.get("event_agency"),
        "event_type": row.get("event_type"),
        "street_closure_type": row.get("street_closure_type"),
    }


def census_entry_from_anchor(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": anchor["name"],
        "date": anchor.get("date"),
        "start_time": anchor.get("start_time"),
        "end_time": anchor.get("end_time"),
        "borough": queue_borough(anchor.get("borough")),
        "neighborhood": anchor.get("neighborhood"),
        "route": anchor.get("route"),
        "event_kind": anchor.get("event_kind", "parade"),
        "permit_event_id": anchor.get("permit_event_id"),
        "permit_status": anchor.get("permit_status", "not_yet_matched"),
        "official_source": anchor.get("official_source"),
        "confidence": anchor.get("confidence", "provisional"),
        "editorial_priority": anchor.get("editorial_priority", "normal"),
        "calendar_eligible": bool(anchor.get("calendar_eligible", True)),
        "map_eligible": bool(anchor.get("map_eligible", False)),
        "source_layer": "editorial_anchor",
        "anchor_key": anchor.get("anchor_key"),
        "date_precision": anchor.get("date_precision"),
        "date_end": anchor.get("date_end"),
        "status_note": anchor.get("status_note"),
    }


def _alias_hit(anchor: dict[str, Any], permit_name: str) -> bool:
    blob = norm_text(permit_name)
    aliases = [anchor.get("name", "")] + list(anchor.get("match_aliases") or [])
    for alias in aliases:
        token = norm_text(str(alias))
        if not token:
            continue
        if token in blob or blob in token:
            return True
        # Loose token overlap for long official permit titles.
        words = [w for w in re.split(r"[^a-z0-9]+", token) if len(w) >= 4]
        if words and sum(1 for w in words if w in blob) >= min(2, len(words)):
            return True
    return False


def _strong_alias_match(anchor: dict[str, Any], permit_name: str) -> bool:
    blob = norm_text(permit_name)
    for alias in anchor.get("match_aliases") or []:
        token = norm_text(str(alias))
        if len(token) >= 8 and token in blob:
            return True
    return False


def _date_compatible(anchor: dict[str, Any], permit_day: date, *, strong_alias: bool) -> bool:
    anchor_day = parse_iso_day(anchor.get("date"))
    anchor_end = parse_iso_day(anchor.get("date_end"))
    precision = str(anchor.get("date_precision") or "exact")
    if precision in {"month_tba", "late_month", "early_month"}:
        if anchor_day and permit_day.year == anchor_day.year and permit_day.month == anchor_day.month:
            return True
        return False
    if precision == "window":
        if anchor_day and anchor_end:
            return anchor_day <= permit_day <= anchor_end
        if anchor_day:
            return abs((permit_day - anchor_day).days) <= 7
        return False
    if anchor_day:
        slop = 14 if strong_alias else 1
        return permit_day == anchor_day or abs((permit_day - anchor_day).days) <= slop
    return False


def match_anchor_to_permit(
    anchor: dict[str, Any], permit_rows: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for row in permit_rows:
        day = parse_iso_day(row.get("start_date_time"))
        if day is None:
            continue
        name = str(row.get("event_name") or "")
        if not _alias_hit(anchor, name):
            continue
        strong_alias = _strong_alias_match(anchor, name)
        if not _date_compatible(anchor, day, strong_alias=strong_alias):
            continue
        borough_ok = True
        anchor_borough = queue_borough(anchor.get("borough"))
        permit_borough = queue_borough(row.get("event_borough"))
        if anchor_borough not in {"Multi-borough", "Metropolitan reference outside NYC"}:
            borough_ok = anchor_borough == permit_borough or permit_borough == "Multi-borough"
        if not borough_ok:
            continue
        return row
    return None


def merge_anchor_with_permit(entry: dict[str, Any], permit_row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(entry)
    merged["permit_event_id"] = str(permit_row.get("source_event_id") or "").strip() or None
    merged["permit_status"] = "permit_matched"
    merged["official_source"] = merged.get("official_source") or "nyc_open_data_tvpp-9vvx"
    if merged.get("confidence") in {None, "provisional", "strongly_supported", "historical_pattern_only"}:
        merged["confidence"] = "permit_confirmed"
    day = parse_iso_day(permit_row.get("start_date_time"))
    if day:
        merged["date"] = day.isoformat()
    start_time = hhmm_from_datetime(permit_row.get("start_date_time"))
    end_time = hhmm_from_datetime(permit_row.get("end_date_time"))
    if start_time:
        merged["start_time"] = start_time
    if end_time:
        merged["end_time"] = end_time
    route = str(permit_row.get("event_location") or "").strip()
    if route:
        merged["route"] = route
    merged["permit_match_name"] = str(permit_row.get("event_name") or "").strip()
    return merged


def group_by_borough(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {b: [] for b in BOROUGH_QUEUES}
    for entry in entries:
        borough = entry.get("borough") or "Multi-borough"
        if borough not in grouped:
            borough = "Multi-borough"
        grouped[borough].append(entry)
    for bucket in grouped.values():
        bucket.sort(key=lambda e: (e.get("date") or "9999-99-99", e.get("name") or ""))
    return grouped
