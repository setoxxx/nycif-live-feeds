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
MAJOR_RADAR_PATH = ROOT / "nycif_major_radar_map_events.json"
PHOTOGRAPHER_CALENDAR_PATH = DATA_DIR / "photographer_assignment_calendar_2mo.json"
CITYWIDE_CALENDAR_PATH = DATA_DIR / "nyc_citywide_events_calendar_snapshot.json"
PARKS_BIGAPPS_PATH = DATA_DIR / "nyc_parks_bigapps_events_snapshot.json"
HISTORICAL_PERMITS_PATH = DATA_DIR / "nyc_permits_historical_snapshot.json"
SAPO_FOIL_PATH = DATA_DIR / "sapo_foil_operator_index.json"
ALL_RADAR_PATH = ROOT / "nycif_all_radar_map_events.json"

EDITORIAL_PRIORITY_RANK = {"highest": 0, "high": 1, "normal": 2, "low": 3}

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
    (
        "street_co_naming",
        re.compile(
            r"co-?naming|c0-naming|street naming|honorary street|naming ceremony|"
            r"street co-?naming|\bway naming\b",
            re.I,
        ),
    ),
    ("civic_dedication", re.compile(r"\bunveiling\b|dedication ceremony|ribbon cutting", re.I)),
]

# Auto-highest civic signals (local major-radar / desk behavior).
PRIORITY_HIGHEST_TITLE_RE = re.compile(
    r"co-?naming|c0-naming|street naming|honorary street|naming ceremony|"
    r"ol.?dirty bastard|\bodb\b|ticker.?tape|ball drop|thanksgiving day parade|"
    r"west indian|j.?ouvert|village halloween",
    re.I,
)
PRIORITY_HIGH_TITLE_RE = re.compile(
    r"street fair|merchandise fair|fan festival|curlfest|ferragosto|san gennaro|"
    r"veterans day parade|pride march|giglio",
    re.I,
)

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


def _title_day_key(name: str, day: str | None) -> tuple[str, str]:
    return norm_text(name), str(day or "")


def load_priority_reference(
    *,
    major_radar_path: Path | None = None,
    photographer_calendar_path: Path | None = None,
) -> dict[str, Any]:
    """Index local desk priority signals (major radar + photographer calendar)."""
    by_permit_id: dict[str, dict[str, Any]] = {}
    by_title_day: dict[tuple[str, str], dict[str, Any]] = {}

    def _upsert(
        *,
        permit_id: str | None,
        title: str,
        day: str | None,
        priority: str,
        reason: str,
        source: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "editorial_priority": priority,
            "priority_reason": reason,
            "priority_source": source,
            **(extra or {}),
        }
        if permit_id:
            existing = by_permit_id.get(permit_id)
            if existing is None or EDITORIAL_PRIORITY_RANK[priority] < EDITORIAL_PRIORITY_RANK.get(
                existing["editorial_priority"], 9
            ):
                by_permit_id[permit_id] = payload
        key = _title_day_key(title, day)
        existing = by_title_day.get(key)
        if existing is None or EDITORIAL_PRIORITY_RANK[priority] < EDITORIAL_PRIORITY_RANK.get(
            existing["editorial_priority"], 9
        ):
            by_title_day[key] = payload

    radar_path = major_radar_path or MAJOR_RADAR_PATH
    if radar_path.exists():
        radar_rows = json.loads(radar_path.read_text(encoding="utf-8"))
        if isinstance(radar_rows, list):
            for row in radar_rows:
                if not isinstance(row, dict):
                    continue
                day = str(row.get("date") or row.get("start_date_time") or "")[:10]
                if not in_census_window(parse_iso_day(day)):
                    continue
                title = str(row.get("title") or "")
                permit_id = str(row.get("id") or row.get("source_event_id") or "").strip() or None
                event_type = str(row.get("event_type") or "")
                priority = "normal"
                reason = None
                if event_type == "Street Co-Naming / Ceremony" or row.get("_manual_priority") == "NYPD":
                    priority = "highest"
                    reason = "major_radar_street_co_naming"
                elif row.get("field_default") or row.get("assignment_feed") == "major":
                    priority = "high"
                    reason = "major_radar_field_default"
                elif row.get("photo_pick"):
                    priority = "high"
                    reason = "major_radar_photo_pick"
                if priority != "normal":
                    _upsert(
                        permit_id=permit_id,
                        title=title,
                        day=day,
                        priority=priority,
                        reason=reason or "major_radar",
                        source="nycif_major_radar_map_events.json",
                    )

    cal_path = photographer_calendar_path or PHOTOGRAPHER_CALENDAR_PATH
    if cal_path.exists():
        cal_payload = json.loads(cal_path.read_text(encoding="utf-8"))
        cal_rows = cal_payload.get("events") if isinstance(cal_payload, dict) else cal_payload
        if isinstance(cal_rows, list):
            for row in cal_rows:
                if not isinstance(row, dict):
                    continue
                day = str(row.get("date") or row.get("start_date_time") or "")[:10]
                if not in_census_window(parse_iso_day(day)):
                    continue
                title = str(row.get("title") or "")
                source = row.get("source") if isinstance(row.get("source"), dict) else {}
                permit_id = str(source.get("source_event_id") or "").strip() or None
                score = int(row.get("assignment_score") or 0)
                priority = "normal"
                reason = None
                if row.get("money_day") and score >= 380:
                    priority = "highest"
                    reason = "photographer_money_day"
                elif row.get("money_day") or score >= 300:
                    priority = "high"
                    reason = "photographer_assignment_calendar"
                if priority != "normal":
                    _upsert(
                        permit_id=permit_id,
                        title=title,
                        day=day,
                        priority=priority,
                        reason=reason or "photographer_assignment_calendar",
                        source="photographer_assignment_calendar_2mo.json",
                        extra={"assignment_score": score} if score else None,
                    )

    return {"by_permit_id": by_permit_id, "by_title_day": by_title_day}


def infer_editorial_priority(entry: dict[str, Any]) -> tuple[str, str | None]:
    name = str(entry.get("name") or "")
    blob = norm_text(f"{name} {entry.get('event_kind') or ''}")
    if entry.get("event_kind") == "street_co_naming" or PRIORITY_HIGHEST_TITLE_RE.search(name):
        return "highest", "title_street_co_naming_or_signature_civic"
    if PRIORITY_HIGH_TITLE_RE.search(name):
        return "high", "title_high_value_civic"
    if entry.get("editorial_priority") in {"highest", "high"}:
        return str(entry["editorial_priority"]), "anchor_editorial_priority"
    return str(entry.get("editorial_priority") or "normal"), None


def apply_editorial_priority(
    entry: dict[str, Any], priority_ref: dict[str, Any] | None
) -> dict[str, Any]:
    updated = dict(entry)
    base_priority, base_reason = infer_editorial_priority(updated)
    updated["editorial_priority"] = base_priority
    if base_reason:
        updated["priority_reason"] = base_reason

    ref = priority_ref or {}
    permit_id = str(updated.get("permit_event_id") or "").strip()
    day = str(updated.get("date") or "")
    title = str(updated.get("name") or "")
    overlay = None
    if permit_id:
        overlay = (ref.get("by_permit_id") or {}).get(permit_id)
    if overlay is None:
        overlay = (ref.get("by_title_day") or {}).get(_title_day_key(title, day))

    if overlay:
        new_priority = overlay["editorial_priority"]
        current = str(updated.get("editorial_priority") or "normal")
        if EDITORIAL_PRIORITY_RANK[new_priority] <= EDITORIAL_PRIORITY_RANK.get(current, 9):
            updated["editorial_priority"] = new_priority
            updated["priority_reason"] = overlay.get("priority_reason")
            updated["priority_source"] = overlay.get("priority_source")
            if overlay.get("assignment_score") is not None:
                updated["assignment_score"] = overlay["assignment_score"]
    return updated


def census_entry_from_permit(
    row: dict[str, Any],
    *,
    match_reason: str,
    priority_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    day = parse_iso_day(row.get("start_date_time"))
    blob = permit_blob(row)
    borough = queue_borough(row.get("event_borough"))
    entry = {
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
    return apply_editorial_priority(entry, priority_ref)


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


def merge_anchor_with_permit(
    entry: dict[str, Any],
    permit_row: dict[str, Any],
    *,
    priority_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    return apply_editorial_priority(merged, priority_ref)


def _sort_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda e: (
            EDITORIAL_PRIORITY_RANK.get(str(e.get("editorial_priority") or "normal"), 9),
            e.get("date") or "9999-99-99",
            e.get("name") or "",
        ),
    )


def group_by_borough(entries: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {b: [] for b in BOROUGH_QUEUES}
    for entry in entries:
        borough = entry.get("borough") or "Multi-borough"
        if borough not in grouped:
            borough = "Multi-borough"
        grouped[borough].append(entry)
    for bucket in grouped.values():
        bucket[:] = _sort_entries(bucket)
    return grouped


def priority_queue(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cross-borough priority lane for desk/calendar consumers."""
    flagged = [
        e
        for e in entries
        if str(e.get("editorial_priority") or "normal") in {"highest", "high"}
    ]
    return _sort_entries(flagged)


def load_calendar_rows(path: Path | None = None) -> list[dict[str, Any]]:
    payload = json.loads((path or CITYWIDE_CALENDAR_PATH).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    rows = payload.get("events") or payload.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def load_parks_rows(path: Path | None = None) -> list[dict[str, Any]]:
    payload = json.loads((path or PARKS_BIGAPPS_PATH).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    rows = payload.get("events") or payload.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def load_historical_rows(path: Path | None = None) -> list[dict[str, Any]]:
    if not (path or HISTORICAL_PERMITS_PATH).exists():
        return []
    payload = json.loads((path or HISTORICAL_PERMITS_PATH).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    rows = payload.get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def load_foil_operators(path: Path | None = None) -> dict[str, dict[str, Any]]:
    foil_path = path or SAPO_FOIL_PATH
    if not foil_path.exists():
        return {}
    payload = json.loads(foil_path.read_text(encoding="utf-8"))
    operators = payload.get("operators") or []
    index: dict[str, dict[str, Any]] = {}
    for row in operators:
        if not isinstance(row, dict):
            continue
        for key in ("event_id", "permit_event_id", "source_event_id"):
            pid = str(row.get(key) or "").strip()
            if pid:
                index[pid] = row
    return index


def calendar_borough(row: dict[str, Any]) -> str:
    boroughs = row.get("boroughs")
    if isinstance(boroughs, list) and boroughs:
        if len(boroughs) > 1:
            return "Multi-borough"
        return queue_borough(boroughs[0])
    return queue_borough(row.get("borough") or row.get("address"))


def calendar_blob(row: dict[str, Any]) -> str:
    parts = [
        row.get("title"),
        row.get("short_description"),
        row.get("address"),
        row.get("categories"),
    ]
    return norm_text(" ".join(str(p) for p in parts if p))


def is_calendar_candidate(row: dict[str, Any]) -> tuple[bool, str]:
    if row.get("canceled"):
        return False, "canceled"
    day = parse_iso_day(row.get("start_date_time"))
    if not in_census_window(day):
        return False, "outside_window"
    blob = calendar_blob(row)
    if EXCLUDE_LOCATION_RE.search(blob):
        return False, "parade_ground_excluded"
    if EXCLUDE_TITLE_RE.search(norm_text(str(row.get("title") or ""))):
        return False, "rehearsal_or_closed_excluded"
    if CENSUS_INCLUDE_RE.search(blob):
        return True, "calendar_census_keyword"
    return False, "no_match"


def is_parks_candidate(row: dict[str, Any]) -> tuple[bool, str]:
    day = parse_iso_day(row.get("start_date_time") or row.get("start_date"))
    if not in_census_window(day):
        return False, "outside_window"
    blob = norm_text(
        " ".join(
            str(p)
            for p in (
                row.get("title"),
                row.get("description"),
                row.get("location"),
                row.get("display_location"),
                row.get("categories"),
            )
            if p
        )
    )
    if EXCLUDE_LOCATION_RE.search(blob):
        return False, "parade_ground_excluded"
    if EXCLUDE_TITLE_RE.search(norm_text(str(row.get("title") or ""))):
        return False, "rehearsal_or_closed_excluded"
    if CENSUS_INCLUDE_RE.search(blob):
        return True, "parks_census_keyword"
    return False, "no_match"


def entry_dedupe_key(entry: dict[str, Any]) -> str:
    pid = str(entry.get("permit_event_id") or "").strip()
    day = str(entry.get("date") or "")
    if pid and day:
        return f"permit:{pid}@{day}"
    anchor = entry.get("anchor_key")
    if anchor and day:
        return f"anchor:{anchor}@{day}"
    return f"title:{norm_text(str(entry.get('name') or ''))}@{day}@{norm_text(str(entry.get('borough') or ''))}"


def census_entry_from_calendar(
    row: dict[str, Any],
    *,
    match_reason: str,
    priority_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    day = parse_iso_day(row.get("start_date_time"))
    blob = calendar_blob(row)
    entry = {
        "name": str(row.get("title") or "").strip(),
        "date": day.isoformat() if day else None,
        "start_time": hhmm_from_datetime(row.get("start_date_time")),
        "end_time": hhmm_from_datetime(row.get("end_date_time")),
        "borough": calendar_borough(row),
        "neighborhood": None,
        "route": str(row.get("address") or "").strip() or None,
        "event_kind": infer_event_kind(blob),
        "permit_event_id": None,
        "permit_status": "not_yet_matched",
        "official_source": "nyc_citywide_events_calendar",
        "confidence": "provisional",
        "editorial_priority": "normal",
        "calendar_eligible": True,
        "map_eligible": False,
        "source_layer": "citywide_calendar",
        "match_reason": match_reason,
        "source_event_id": str(row.get("source_event_id") or "").strip() or None,
        "permalink": row.get("permalink"),
    }
    return apply_editorial_priority(entry, priority_ref)


def census_entry_from_parks(
    row: dict[str, Any],
    *,
    match_reason: str,
    priority_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    day = parse_iso_day(row.get("start_date_time") or row.get("start_date"))
    blob = norm_text(
        " ".join(
            str(p)
            for p in (row.get("title"), row.get("description"), row.get("location"))
            if p
        )
    )
    entry = {
        "name": str(row.get("title") or "").strip(),
        "date": day.isoformat() if day else None,
        "start_time": hhmm_from_datetime(row.get("start_date_time")),
        "end_time": hhmm_from_datetime(row.get("end_date_time")),
        "borough": queue_borough(row.get("borough")),
        "neighborhood": None,
        "route": str(row.get("display_location") or row.get("location") or "").strip() or None,
        "event_kind": infer_event_kind(blob),
        "permit_event_id": None,
        "permit_status": "not_yet_matched",
        "official_source": "nyc_parks_bigapps",
        "confidence": "provisional",
        "editorial_priority": "normal",
        "calendar_eligible": True,
        "map_eligible": False,
        "source_layer": "parks_bigapps",
        "match_reason": match_reason,
        "source_event_id": str(row.get("source_event_id") or "").strip() or None,
        "latitude": row.get("lat"),
        "longitude": row.get("lng"),
    }
    return apply_editorial_priority(entry, priority_ref)


def merge_supplemental_entries(
    existing: list[dict[str, Any]], supplemental: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Merge supplemental rows without duplicating permit/anchor matches."""
    seen = {entry_dedupe_key(e) for e in existing}
    added = 0
    merged = list(existing)
    for entry in supplemental:
        key = entry_dedupe_key(entry)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
        added += 1
    return merged, added


def apply_historical_tba_inference(
    entries: list[dict[str, Any]],
    historical_rows: list[dict[str, Any]],
    *,
    anchor_registry: dict[str, Any] | None = None,
) -> int:
    """Use prior-year permits to annotate unmatched anchors — never add standalone rows."""
    if not historical_rows:
        return 0
    alias_by_key: dict[str, list[str]] = {}
    if anchor_registry:
        for anchor in anchor_registry.get("anchors") or []:
            key = anchor.get("anchor_key")
            if key:
                alias_by_key[str(key)] = list(anchor.get("match_aliases") or [])
    updated = 0
    for entry in entries:
        if not entry.get("anchor_key"):
            continue
        if entry.get("permit_status") not in {"not_yet_matched", "anchor_only"}:
            continue
        anchor_name = str(entry.get("name") or "")
        anchor_ctx = {
            "name": anchor_name,
            "match_aliases": alias_by_key.get(str(entry.get("anchor_key")), []),
        }
        for hist in historical_rows:
            hist_name = str(hist.get("event_name") or "")
            if not _alias_hit(anchor_ctx, hist_name):
                continue
            hist_day = parse_iso_day(hist.get("start_date_time"))
            if hist_day is None:
                continue
            note = (
                f"Historical pattern: prior-year permit on {hist_day.month}/{hist_day.day} "
                f"(event_id {hist.get('event_id') or hist.get('source_event_id') or 'unknown'})"
            )
            entry["status_note"] = note
            if entry.get("confidence") in {None, "provisional"}:
                entry["confidence"] = "historical_pattern_only"
            entry["historical_reference_event_id"] = str(
                hist.get("event_id") or hist.get("source_event_id") or ""
            ).strip() or None
            updated += 1
            break
    return updated


def apply_foil_operator_joins(
    entries: list[dict[str, Any]], foil_index: dict[str, dict[str, Any]]
) -> int:
    if not foil_index:
        return 0
    joins = 0
    for entry in entries:
        pid = str(entry.get("permit_event_id") or "").strip()
        if not pid or pid not in foil_index:
            continue
        foil = foil_index[pid]
        org = foil.get("applicant_org") or foil.get("operator_org")
        if org:
            entry["foil_applicant_org"] = org
            joins += 1
    return joins


def anchor_watchlist(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Unmatched editorial anchors awaiting permit/organizer confirmation."""
    rows = [
        e
        for e in entries
        if e.get("anchor_key")
        and e.get("permit_status") in {"not_yet_matched", "anchor_only"}
    ]
    return _sort_entries(rows)
