#!/usr/bin/env python3
"""Build Howard's premium photographer assignment calendar (next ~2 months).

Read-only staging artifact for God View / Field Desk. Not a public-map publish.
Never invents HH:MM. Never writes location_cache or Approved production feeds.
"""

from __future__ import annotations

import argparse
import calendar as calmod
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, today_nyc, utc_now  # noqa: E402
from schema_v1_common import DEFAULT_TIMEZONE, extract_events  # noqa: E402

NY_TZ = ZoneInfo(DEFAULT_TIMEZONE)

# Deterministic assignment-grade keyword scoring (mirrors major-feed intent).
KEYWORD_RULES: list[tuple[int, str, str]] = [
    (220, r"world cup|fifa|fan zone", "keyword_world_cup_fan_zone"),
    (200, r"\bpride\b", "keyword_pride"),
    (200, r"\bparade\b|\bmarch\b|\brally\b|\bvigil\b|\bceremony\b", "keyword_civic_gathering"),
    (180, r"street fair|festival|merchandise fair|feast|block party", "keyword_street_fair_festival"),
    (170, r"marathon|criterium|\b5k\b|\b10k\b|half marathon|tour|race", "keyword_spectator_race"),
    (160, r"street closure|open street|plaza|activation", "keyword_street_activation"),
    (140, r"farmers market|greenmarket|street market|flea market", "keyword_market"),
    (130, r"concert|performance|fireworks|carnival", "keyword_spectacle"),
    (120, r"protest|demonstration", "keyword_civic_action"),
]

EXCLUDE_ROUTINES = re.compile(
    r"sport - youth|sport - adult|softball practice|baseball practice|"
    r"basketball practice|soccer practice|learn to swim|shape up|"
    r"fitness class|chair yoga|tai chi|esl class|computer class",
    re.I,
)

MIN_MAJOR_SCORE = 160
MIN_REVIEW_SCORE = 180


def event_day(row: dict[str, Any]) -> str | None:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    direct = str(nycif.get("event_date") or "").strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", direct):
        return direct
    start = str(row.get("start_date_time") or row.get("start") or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", start):
        return start[:10]
    return None


def scoring_text(row: dict[str, Any]) -> str:
    parts = [
        row.get("title"),
        row.get("category"),
        row.get("location"),
        row.get("event_type"),
        row.get("type"),
        ((row.get("nycif") or {}) if isinstance(row.get("nycif"), dict) else {}).get("event_type"),
        " ".join(str(x) for x in (row.get("categories") or []) if x),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def _base_assignment_score(row: dict[str, Any], text: str) -> tuple[int, list[str]]:
    rules: list[str] = []
    score = 0
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    if row.get("significance") == "major" or nycif.get("is_major"):
        score += 200
        rules.append("significance_major")
    carried = nycif.get("major_score")
    if isinstance(carried, (int, float)) and carried:
        bonus = int(carried)
        score = max(score, bonus)
        rules.append(f"carried_major_score:{bonus}")
    if nycif.get("photo_pick") or nycif.get("field_default") or nycif.get("assignment_feed"):
        score += 80
        rules.append("assignment_or_photo_flag")
    for points, pattern, rule in KEYWORD_RULES:
        if re.search(pattern, text):
            score += points
            rules.append(rule)
    return score, rules


def _should_exclude(
    row: dict[str, Any],
    *,
    lane: str,
    text: str,
    score: int,
    rules: list[str],
) -> tuple[bool, list[str]]:
    extra: list[str] = []
    if EXCLUDE_ROUTINES.search(text) and score < 220 and "significance_major" not in rules:
        return True, ["routine_activity_excluded"]
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    coord = nycif.get("coordinate_status") or (
        "map_ready" if row.get("latitude") is not None else "list_only"
    )
    loc = str(row.get("location") or row.get("display_location") or "")
    thin_list = (
        lane != "approved_major"
        and coord == "list_only"
        and (loc.upper().startswith("ZIP ") or len(loc.strip()) < 4)
        and score < 220
    )
    if thin_list:
        return True, ["list_only_thin_location_excluded"]
    return False, extra


def score_row(row: dict[str, Any], *, lane: str) -> tuple[int, list[str], bool]:
    text = scoring_text(row)
    score, rules = _base_assignment_score(row, text)
    excluded, excl_rules = _should_exclude(row, lane=lane, text=text, score=score, rules=rules)
    if excl_rules:
        rules = [*rules, *excl_rules]
    return score, rules, excluded


def load_major_events() -> list[dict[str, Any]]:
    for path in (
        DATA_DIR / "schema-v1-discovery" / "major" / "events.json",
        DATA_DIR / "events_discovery_v02_major.json",
        DATA_DIR / "events_schema_v1_major.json",
    ):
        if path.exists():
            return extract_events(load_json(path, {}))
    return []


def load_review_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Civic dated review events (OAC etc.)
    civic = load_json(DATA_DIR / "events_schema_v1_civic_review.json", {})
    rows.extend(extract_events(civic))
    # Existing supplemental review if present
    supp = DATA_DIR / "events_schema_v1_supplemental_review.json"
    if supp.exists():
        rows.extend(extract_events(load_json(supp, {})))
    return rows


def window_bounds(today: date) -> tuple[date, date, date, date]:
    """Return (today, end_2mo, month1_start, month2_start)."""
    month1_start = date(today.year, today.month, 1)
    if today.month == 12:
        month2_start = date(today.year + 1, 1, 1)
        end = date(today.year + 1, 2, 1) - timedelta(days=1)
    else:
        month2_start = date(today.year, today.month + 1, 1)
        if today.month == 11:
            end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 2, 1) - timedelta(days=1)
    return today, end, month1_start, month2_start


def map_link(lat: Any, lng: Any) -> str | None:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None
    return f"https://www.google.com/maps?q={lat_f},{lng_f}"


def normalize_assignment(
    row: dict[str, Any],
    *,
    lane: str,
    score: int,
    rules: list[str],
) -> dict[str, Any] | None:
    day = event_day(row)
    if not day:
        return None
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    coord = nycif.get("coordinate_status")
    if not coord:
        coord = "map_ready" if row.get("latitude") is not None else "list_only"
    start = row.get("start_date_time")
    end = row.get("end_date_time")
    # Preserve source times only; do not invent clock fields.
    return {
        "id": row.get("id"),
        "title": row.get("title") or "Untitled event",
        "date": day,
        "start_date_time": start,
        "end_date_time": end,
        "timezone": row.get("timezone") or DEFAULT_TIMEZONE,
        "borough": row.get("borough"),
        "display_location": row.get("location") or row.get("display_location"),
        "coordinate_status": coord,
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "map_link": map_link(row.get("latitude"), row.get("longitude")) if coord == "map_ready" else None,
        "category": row.get("category"),
        "lane": lane,
        "source": {
            "dataset": source.get("dataset"),
            "source_event_id": source.get("source_event_id"),
        },
        "assignment_score": score,
        "why_selected": rules[:6],
        "photo_pick": bool(nycif.get("photo_pick")),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "premium_label": "Photographer Assignment Calendar (premium/operator)",
    }


def month_grid(year: int, month: int, by_day: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    weeks = calmod.monthcalendar(year, month)
    days_out = []
    for week in weeks:
        week_out = []
        for day in week:
            if day == 0:
                week_out.append(None)
                continue
            key = f"{year:04d}-{month:02d}-{day:02d}"
            events = by_day.get(key, [])
            top = sorted(events, key=lambda e: (-(e.get("assignment_score") or 0), e.get("title") or ""))[:5]
            week_out.append(
                {
                    "date": key,
                    "count": len(events),
                    "map_ready_count": sum(1 for e in events if e.get("coordinate_status") == "map_ready"),
                    "top_events": [
                        {
                            "id": e.get("id"),
                            "title": e.get("title"),
                            "borough": e.get("borough"),
                            "lane": e.get("lane"),
                            "assignment_score": e.get("assignment_score"),
                            "why_selected": e.get("why_selected"),
                            "coordinate_status": e.get("coordinate_status"),
                            "start_date_time": e.get("start_date_time"),
                            "display_location": e.get("display_location"),
                            "map_link": e.get("map_link"),
                            "source": e.get("source"),
                        }
                        for e in top
                    ],
                }
            )
        days_out.append(week_out)
    return {
        "year": year,
        "month": month,
        "label": date(year, month, 1).strftime("%B %Y"),
        "weeks": days_out,
    }


def _in_window(day: str | None, today: date, end: date) -> bool:
    if not day:
        return False
    d = date.fromisoformat(day)
    return today <= d <= end


def collect_assignments(
    rows: list[dict[str, Any]],
    *,
    lane: str,
    min_score: int,
    today: date,
    end: date,
    seen_ids: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        day = event_day(row)
        if not _in_window(day, today, end):
            continue
        score, rules, excluded = score_row(row, lane=lane)
        if excluded or score < min_score:
            continue
        rid = str(row.get("id") or "")
        if rid and rid in seen_ids:
            continue
        item = normalize_assignment(row, lane=lane, score=score, rules=rules)
        if not item or str(item["id"]) in seen_ids:
            continue
        seen_ids.add(str(item["id"]))
        out.append(item)
    return out


def build_calendar_payload(
    selected: list[dict[str, Any]],
    *,
    today: date,
    end: date,
    m1: date,
    m2: date,
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = sorted(
        selected,
        key=lambda e: (e["date"], -(e.get("assignment_score") or 0), e.get("title") or ""),
    )
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in selected:
        by_day[e["date"]].append(e)
    months = [
        month_grid(m1.year, m1.month, by_day),
        month_grid(m2.year, m2.month, by_day),
    ]
    go_shoot = selected[:20]
    payload = {
        "schema_version": "photographer-assignment-calendar-v1",
        "generated_at_utc": utc_now(),
        "premium_label": "Photographer Assignment Calendar (premium/operator)",
        "timezone": DEFAULT_TIMEZONE,
        "reference_today_nyc": today.isoformat(),
        "window_start": today.isoformat(),
        "window_end": end.isoformat(),
        "total_events": len(selected),
        "days_with_coverage": sum(1 for v in by_day.values() if v),
        "coordinate_status_counts": dict(Counter(e.get("coordinate_status") for e in selected)),
        "lane_counts": dict(Counter(e.get("lane") for e in selected)),
        "months": months,
        "go_shoot_these": go_shoot,
        "events": selected,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "selection_rules_documentation": [
            "Primary: Approved/Major permits with score >= 160 (significance/major_score/keywords).",
            "Secondary: Review/civic high-signal with score >= 180 and location not ZIP-only fluff.",
            "Routine sports/classes suppressed unless overwhelmingly major.",
            "Never invent HH:MM; start/end are source-native or null.",
        ],
    }
    report = {
        "schema_version": "photographer-assignment-calendar-v1",
        "generated_at_utc": payload["generated_at_utc"],
        "qa_pass": len(selected) > 0 and all(e.get("date") for e in selected),
        "reference_today_nyc": today.isoformat(),
        "window_end": end.isoformat(),
        "total_events": len(selected),
        "days_with_coverage": payload["days_with_coverage"],
        "month_counts": [
            {
                "label": m["label"],
                "event_count": sum((d or {}).get("count", 0) for week in m["weeks"] for d in week if d),
                "days_with_events": sum(1 for week in m["weeks"] for d in week if d and d.get("count")),
            }
            for m in months
        ],
        "coordinate_status_counts": payload["coordinate_status_counts"],
        "lane_counts": payload["lane_counts"],
        "go_shoot_sample": [
            {"date": e["date"], "title": e["title"], "score": e["assignment_score"], "borough": e["borough"]}
            for e in go_shoot[:10]
        ],
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "protected_files_untouched": True,
    }
    return payload, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None)
    args = parser.parse_args()
    today = date.fromisoformat(args.reference_today) if args.reference_today else today_nyc()
    _, end, m1, m2 = window_bounds(today)

    seen_ids: set[str] = set()
    selected = collect_assignments(
        load_major_events(),
        lane="approved_major",
        min_score=MIN_MAJOR_SCORE,
        today=today,
        end=end,
        seen_ids=seen_ids,
    )
    selected.extend(
        collect_assignments(
            load_review_candidates(),
            lane="review_high_signal",
            min_score=MIN_REVIEW_SCORE,
            today=today,
            end=end,
            seen_ids=seen_ids,
        )
    )
    payload, report = build_calendar_payload(selected, today=today, end=end, m1=m1, m2=m2)
    save_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", payload)
    save_json(DATA_DIR / "photographer_assignment_calendar_report.json", report)
    print(
        json.dumps(
            {
                "total_events": report["total_events"],
                "days_with_coverage": report["days_with_coverage"],
                "month_counts": report["month_counts"],
                "qa_pass": report["qa_pass"],
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
