#!/usr/bin/env python3
"""Build today/tomorrow photographer Money-Day packs with borough clusters.

Read-only operator desk artifacts. Never invents HH:MM or lat/lng.
Never writes location_cache or Approved production feeds.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, today_nyc, utc_now  # noqa: E402
from pin_integrity import certify_nyc_pin  # noqa: E402

BOROUGH_KEYS = ("Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island")


def is_certified_map_ready(e: dict[str, Any]) -> bool:
    if e.get("coordinate_status") != "map_ready":
        return False
    lat_f, lng_f, ok, _reason = certify_nyc_pin(e.get("latitude"), e.get("longitude"), allow_swap_correct=True)
    if not ok:
        return False
    e["latitude"] = lat_f
    e["longitude"] = lng_f
    e["certified_pin"] = True
    return True


def normalize_borough(value: Any) -> str:
    raw = str(value or "").strip()
    low = raw.lower()
    if low in {"manhattan", "mn", "new york"}:
        return "Manhattan"
    if low in {"brooklyn", "bk", "bklyn"}:
        return "Brooklyn"
    if low in {"queens", "qn"}:
        return "Queens"
    if low in {"bronx", "bx", "the bronx"}:
        return "Bronx"
    if low in {"staten island", "si", "richmond"}:
        return "Staten Island"
    return "Unknown"


def field_desk_link(day: str, borough: str | None = None) -> str:
    base = (
        "https://setoxxx.github.io/nycif-field-desk/"
        f"?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date={day}&assignment=1"
    )
    if borough and borough != "Unknown":
        return base + f"&borough={borough.replace(' ', '%20')}"
    return base


def pack_event(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": e.get("id"),
        "title": e.get("title"),
        "date": e.get("date"),
        "start_date_time": e.get("start_date_time"),
        "end_date_time": e.get("end_date_time"),
        "borough": e.get("borough"),
        "display_location": e.get("display_location"),
        "coordinate_status": e.get("coordinate_status"),
        "source": e.get("source"),
        "lane": e.get("lane"),
        "assignment_score": e.get("assignment_score"),
        "why_selected": e.get("why_selected"),
        "map_link": e.get("map_link"),
        "field_desk_link": e.get("field_desk_link") or field_desk_link(str(e.get("date") or "")),
        "latitude": e.get("latitude") if e.get("coordinate_status") == "map_ready" else None,
        "longitude": e.get("longitude") if e.get("coordinate_status") == "map_ready" else None,
        "certified_pin": bool(e.get("certified_pin") and e.get("coordinate_status") == "map_ready"),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
    }


def build_pack(events: list[dict[str, Any]], *, day: date, reference_today: date, label: str) -> dict[str, Any]:
    day_s = day.isoformat()
    day_events = [e for e in events if e.get("date") == day_s]
    day_events.sort(key=lambda e: (-(e.get("assignment_score") or 0), e.get("title") or ""))
    # Pin clusters: NYC-certified map_ready only. Prefer demote over wrong pin.
    map_ready = []
    for e in day_events:
        if is_certified_map_ready(e):
            map_ready.append(e)
        elif e.get("coordinate_status") == "map_ready":
            e["coordinate_status"] = "list_only"
            e["latitude"] = None
            e["longitude"] = None
            e["map_link"] = None
            e["certified_pin"] = False
    clusters: dict[str, list[dict[str, Any]]] = {b: [] for b in BOROUGH_KEYS}
    clusters["Unknown"] = []
    for e in map_ready:
        clusters[normalize_borough(e.get("borough"))].append(pack_event(e))
    borough_clusters = []
    for b in [*BOROUGH_KEYS, "Unknown"]:
        items = clusters.get(b) or []
        if not items:
            continue
        borough_clusters.append(
            {
                "borough": b,
                "count": len(items),
                "field_desk_link": field_desk_link(day_s, b if b != "Unknown" else None),
                "events": items,
            }
        )
    go_shoot = [pack_event(e) for e in day_events[:25]]
    return {
        "schema_version": "photographer-money-day-pack-v1",
        "premium_label": "Photographer Money-Day Pack (premium/operator)",
        "pack_label": label,
        "generated_at_utc": utc_now(),
        "reference_today_nyc": reference_today.isoformat(),
        "pack_date": day_s,
        "total_events": len(day_events),
        "map_ready_count": len(map_ready),
        "list_only_count": sum(1 for e in day_events if e.get("coordinate_status") != "map_ready"),
        "borough_clusters": borough_clusters,
        "go_shoot": go_shoot,
        "money_day_ids": [e.get("id") for e in day_events if e.get("id")],
        "field_desk_link": field_desk_link(day_s),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": "Times/coords are source-native only. Never invented.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None)
    args = parser.parse_args()
    today = date.fromisoformat(args.reference_today) if args.reference_today else today_nyc()
    tomorrow = today + timedelta(days=1)

    cal = load_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", {})
    events = cal.get("events") or []
    if not events:
        print("No photographer calendar events; refusing pack build", file=sys.stderr)
        return 1

    today_pack = build_pack(events, day=today, reference_today=today, label="today")
    tomorrow_pack = build_pack(events, day=tomorrow, reference_today=today, label="tomorrow")

    report = {
        "schema_version": "photographer-money-day-pack-v1",
        "generated_at_utc": utc_now(),
        "reference_today_nyc": today.isoformat(),
        "qa_pass": True,
        "today": {
            "date": today_pack["pack_date"],
            "total_events": today_pack["total_events"],
            "map_ready_count": today_pack["map_ready_count"],
            "borough_cluster_count": len(today_pack["borough_clusters"]),
        },
        "tomorrow": {
            "date": tomorrow_pack["pack_date"],
            "total_events": tomorrow_pack["total_events"],
            "map_ready_count": tomorrow_pack["map_ready_count"],
            "borough_cluster_count": len(tomorrow_pack["borough_clusters"]),
            "top_go_shoot": [
                {
                    "title": e.get("title"),
                    "borough": e.get("borough"),
                    "score": e.get("assignment_score"),
                    "time": e.get("start_date_time"),
                }
                for e in (tomorrow_pack.get("go_shoot") or [])[:10]
            ],
        },
        "artifacts": {
            "today": "data/photographer_money_day_pack_today.json",
            "tomorrow": "data/photographer_money_day_pack_tomorrow.json",
            "calendar": "data/photographer_assignment_calendar_2mo.json",
        },
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "protected_files_untouched": True,
    }

    save_json(DATA_DIR / "photographer_money_day_pack_today.json", today_pack)
    save_json(DATA_DIR / "photographer_money_day_pack_tomorrow.json", tomorrow_pack)
    save_json(DATA_DIR / "photographer_money_day_pack_report.json", report)
    print(json.dumps({"qa_pass": report["qa_pass"], "today": report["today"], "tomorrow": report["tomorrow"]}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
