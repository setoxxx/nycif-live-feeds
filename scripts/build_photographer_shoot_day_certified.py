#!/usr/bin/env python3
"""Build Shoot Day Certified pack — today/tomorrow map pins only (NYC certified).

Ranks crowd magnets (parade/festival/fair/activation/returning_likely) above
routine weekly greenmarkets. Never invents HH:MM or coordinates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, today_nyc, utc_now  # noqa: E402
from pin_integrity import certify_nyc_pin  # noqa: E402

GREENMARKET_RE = re.compile(r"greenmarket|farmers market|farmstand|green market", re.I)
CROWD_RE = re.compile(
    r"parade|festival|street fair|block party|carnival|fan zone|watch party|"
    r"activation|fireworks|march|rally|pride|merchandise fair|feast|open street|"
    r"plaza programming",
    re.I,
)
STATEN_ISLAND = "Staten Island"
BOROUGHS = ("Manhattan", "Brooklyn", "Queens", "Bronx", STATEN_ISLAND)
BOROUGH_NORMALIZE = {
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "Bronx",
    "staten island": STATEN_ISLAND,
    "si": STATEN_ISLAND,
}


def field_desk_link(day: str, borough: str | None = None) -> str:
    base = (
        "https://setoxxx.github.io/nycif-field-desk/"
        f"?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date={day}&assignment=1"
    )
    if borough:
        return base + f"&borough={borough.replace(' ', '%20')}"
    return base


def magnet_rank(row: dict[str, Any]) -> tuple[int, int, str]:
    title = str(row.get("title") or "")
    label = str(row.get("recurrence_label") or "")
    why = " ".join(str(x) for x in (row.get("why_selected") or []))
    score = int(row.get("assignment_score") or row.get("match_score") or 0)
    if label == "returning_likely" and CROWD_RE.search(title):
        tier = 0
    elif CROWD_RE.search(title) or CROWD_RE.search(why):
        tier = 1
    elif label == "returning_likely" and not GREENMARKET_RE.search(title):
        tier = 2
    elif GREENMARKET_RE.search(title):
        tier = 4  # secondary
    else:
        tier = 3
    return (tier, -score, title)


def normalize_borough(value: Any) -> str:
    return BOROUGH_NORMALIZE.get(str(value or "").strip().lower(), "Unknown")


def _viral_enrich(row: dict[str, Any], viral: dict[str, Any] | None) -> None:
    if not viral:
        return
    row["match_score"] = viral.get("match_score") or row.get("match_score")
    prior = viral.get("prior_year") if isinstance(viral.get("prior_year"), dict) else None
    row["prior_year_title"] = (prior or {}).get("title") or viral.get("prior_year_title")
    row["prior_year_date"] = (prior or {}).get("date") or viral.get("prior_year_date")


def certified_row(e: dict[str, Any], *, recurrence_label: str | None = None) -> dict[str, Any] | None:
    if e.get("coordinate_status") != "map_ready":
        return None
    lat_f, lng_f, ok, reason = certify_nyc_pin(
        e.get("latitude"), e.get("longitude"), allow_swap_correct=True
    )
    if not ok or lat_f is None or lng_f is None:
        return None
    src = e.get("source") if isinstance(e.get("source"), dict) else {}
    return {
        "id": e.get("id"),
        "event_id": src.get("source_event_id") or e.get("event_id"),
        "cemsid": e.get("cemsid"),
        "title": e.get("title"),
        "date": e.get("date"),
        "start_date_time": e.get("start_date_time"),
        "end_date_time": e.get("end_date_time"),
        "borough": e.get("borough"),
        "display_location": e.get("display_location"),
        "coordinate_status": "map_ready",
        "latitude": lat_f,
        "longitude": lng_f,
        "certified_pin": True,
        "pin_integrity_reason": reason,
        "source": src or e.get("source"),
        "assignment_score": e.get("assignment_score"),
        "match_score": e.get("match_score"),
        "why_selected": e.get("why_selected"),
        "recurrence_label": recurrence_label or e.get("recurrence_label"),
        "lane": e.get("lane"),
        "map_link": f"https://www.google.com/maps?q={lat_f},{lng_f}",
        "field_desk_link": e.get("field_desk_link") or field_desk_link(str(e.get("date") or "")),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
    }


def _needs_location_row(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": e.get("id"),
        "title": e.get("title"),
        "date": e.get("date"),
        "borough": e.get("borough"),
        "display_location": e.get("display_location"),
        "coordinate_status": "list_only",
        "certified_pin": False,
        "assignment_score": e.get("assignment_score"),
    }


def _borough_clusters(day_s: str, certified: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters = []
    for b in [*BOROUGHS, "Unknown"]:
        items = [c for c in certified if normalize_borough(c.get("borough")) == b]
        if not items:
            continue
        clusters.append(
            {
                "borough": b,
                "count": len(items),
                "field_desk_link": field_desk_link(day_s, b if b != "Unknown" else None),
                "events": items,
            }
        )
    return clusters


def build_day_section(
    day: date,
    money_events: list[dict[str, Any]],
    viral_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    day_s = day.isoformat()
    certified: list[dict[str, Any]] = []
    needs_location: list[dict[str, Any]] = []
    for e in money_events:
        if e.get("date") != day_s:
            continue
        viral = viral_by_id.get(str(e.get("id") or ""))
        label = (viral or {}).get("recurrence_label")
        row = certified_row(e, recurrence_label=label)
        if row:
            _viral_enrich(row, viral)
            certified.append(row)
        else:
            needs_location.append(_needs_location_row(e))
    certified.sort(key=magnet_rank)
    return {
        "date": day_s,
        "certified_pin_count": len(certified),
        "needs_location_count": len(needs_location),
        "borough_clusters": _borough_clusters(day_s, certified),
        "go_shoot_certified": certified,
        "needs_location": needs_location[:50],
        "field_desk_link": field_desk_link(day_s),
    }


def _index_viral_by_id(viral_matches: dict[str, Any]) -> dict[str, dict[str, Any]]:
    viral_by_id: dict[str, dict[str, Any]] = {}
    for m in viral_matches.get("matches") or []:
        if not isinstance(m, dict):
            continue
        cur = m.get("current")
        if not isinstance(cur, dict):
            continue
        cid = str(cur.get("id") or "")
        if not cid:
            continue
        prev = viral_by_id.get(cid)
        if prev is None or int(m.get("match_score") or 0) > int(prev.get("match_score") or 0):
            viral_by_id[cid] = m
    return viral_by_id


def _next7_summary(
    reference: date,
    events: list[dict[str, Any]],
    viral_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    next7 = []
    for i in range(7):
        sec = build_day_section(reference + timedelta(days=i), events, viral_by_id)
        next7.append(
            {
                "date": sec["date"],
                "certified_pin_count": sec["certified_pin_count"],
                "needs_location_count": sec["needs_location_count"],
                "top": [
                    {"title": e.get("title"), "borough": e.get("borough"), "tier_hint": magnet_rank(e)[0]}
                    for e in (sec.get("go_shoot_certified") or [])[:5]
                ],
            }
        )
    return next7


def _top_rows(section: dict[str, Any], n: int = 8) -> list[dict[str, Any]]:
    return [
        {
            "title": e.get("title"),
            "borough": e.get("borough"),
            "recurrence_label": e.get("recurrence_label"),
        }
        for e in (section.get("go_shoot_certified") or [])[:n]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None)
    args = parser.parse_args()
    reference = date.fromisoformat(args.reference_today) if args.reference_today else today_nyc()
    tomorrow = reference + timedelta(days=1)

    cal = load_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", {})
    events = cal.get("events") if isinstance(cal, dict) else []
    if not isinstance(events, list) or not events:
        raise SystemExit("Money-Day calendar missing — run calendar + pin gate first")

    viral_matches = load_json(DATA_DIR / "photographer_viral_recurrence_matches.json", {})
    viral_by_id = _index_viral_by_id(viral_matches if isinstance(viral_matches, dict) else {})

    today_sec = build_day_section(reference, events, viral_by_id)
    tom_sec = build_day_section(tomorrow, events, viral_by_id)
    next7 = _next7_summary(reference, events, viral_by_id)

    gate = load_json(DATA_DIR / "pin_integrity_gate_report.json", {})
    pack = {
        "schema_version": "photographer-shoot-day-certified-v1",
        "premium_label": "Shoot Day Certified Pack (premium/operator)",
        "generated_at_utc": utc_now(),
        "reference_today_nyc": reference.isoformat(),
        "pin_integrity_qa_pass": bool(gate.get("qa_pass")),
        "today": today_sec,
        "tomorrow": tom_sec,
        "next_7_summary": next7,
        "ranking_rules": [
            "returning_likely + crowd keywords first",
            "parade/festival/fair/activation next",
            "other non-greenmarket returning",
            "greenmarkets secondary",
            "only certified map_ready pins exposed for map clusters",
        ],
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    save_json(DATA_DIR / "photographer_shoot_day_certified_pack.json", pack)

    report = {
        "schema_version": "photographer-shoot-day-certified-v1",
        "generated_at_utc": pack["generated_at_utc"],
        "qa_pass": bool(gate.get("qa_pass")),
        "reference_today_nyc": reference.isoformat(),
        "today_certified_pins": today_sec["certified_pin_count"],
        "tomorrow_certified_pins": tom_sec["certified_pin_count"],
        "today_needs_location": today_sec["needs_location_count"],
        "tomorrow_needs_location": tom_sec["needs_location_count"],
        "pin_integrity_qa_pass": bool(gate.get("qa_pass")),
        "today_top": _top_rows(today_sec),
        "tomorrow_top": _top_rows(tom_sec),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "protected_files_untouched": True,
    }
    save_json(DATA_DIR / "photographer_shoot_day_certified_report.json", report)
    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "today_certified_pins": report["today_certified_pins"],
                "tomorrow_certified_pins": report["tomorrow_certified_pins"],
                "pin_integrity_qa_pass": report["pin_integrity_qa_pass"],
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
