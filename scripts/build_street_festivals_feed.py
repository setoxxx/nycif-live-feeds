#!/usr/bin/env python3
"""Build a small street-festival / feast feed from committed snapshots (offline).

The staged permit snapshot is sports-heavy and often lacks the multi-day
Street Festival type. This builder harvests feast / festival / marquee civic
rows from the staged feed + calendar/parks supplemental snapshots so the
comprehensive What's-New/coverage fold-in and discovery projector can surface
them. Does NOT touch location_cache or GPS promotion artifacts.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "nycif_street_festivals_feed.json"

NYC = {"min_lat": 40.4774, "max_lat": 40.9176, "min_lng": -74.2591, "max_lng": -73.7004}
FESTIVAL_RE = re.compile(
    r"\bfeast\b|street festival|san gennaro|giglio|carnival|mardi gras|"
    r"summerstage|film festival|food festival|cultural festival",
    re.I,
)


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("events", "data", "rows", "records"):
            val = payload.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def valid_coord(lat, lng) -> bool:
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    if abs(lat_f) < 1e-9 and abs(lng_f) < 1e-9:
        return False
    return (
        NYC["min_lat"] <= lat_f <= NYC["max_lat"]
        and NYC["min_lng"] <= lng_f <= NYC["max_lng"]
    )


def title_of(row: dict) -> str:
    return str(
        row.get("title")
        or row.get("name")
        or row.get("event_name")
        or row.get("search_label")
        or ""
    ).strip()


def is_festival_row(row: dict) -> bool:
    etype = str(row.get("event_type") or row.get("type") or "").lower()
    if etype in {"street festival", "single block festival"}:
        return True
    blob = " ".join(
        str(v)
        for v in (
            title_of(row),
            row.get("event_type"),
            row.get("type"),
            row.get("category"),
            row.get("description"),
        )
        if v
    )
    return bool(FESTIVAL_RE.search(blob))


def main() -> int:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sources = [
        DATA / "nycif_staged_live_events.json",
        DATA / "supplemental_events_staging_feed.json",
        DATA / "nyc_citywide_events_calendar_snapshot.json",
        DATA / "nyc_parks_bigapps_events_snapshot.json",
    ]
    seen: set[str] = set()
    events: list[dict] = []
    for path in sources:
        for row in load_rows(path):
            if not is_festival_row(row):
                continue
            title = title_of(row) or "NYC festival"
            start = str(row.get("start_date_time") or row.get("start") or "")[:10]
            sid = str(
                row.get("source_event_id")
                or row.get("event_id")
                or row.get("id")
                or f"{title}:{start}"
            )
            if sid in seen:
                continue
            seen.add(sid)
            lat = row.get("lat") if row.get("lat") is not None else row.get("latitude")
            lng = row.get("lng") if row.get("lng") is not None else row.get("longitude")
            mapped = valid_coord(lat, lng)
            events.append(
                {
                    "id": f"festival:{sid}@{start or 'undated'}",
                    "title": title,
                    "event_type": row.get("event_type") or row.get("type") or "Street Festival",
                    "category": "arts",
                    "start_date_time": row.get("start_date_time") or row.get("start"),
                    "end_date_time": row.get("end_date_time") or row.get("end"),
                    "start_date": start or None,
                    "end_date": str(row.get("end_date_time") or row.get("end") or start or "")[:10]
                    or None,
                    "borough": row.get("borough") or row.get("event_borough"),
                    "location": row.get("display_location") or row.get("location") or row.get("address"),
                    "latitude": float(lat) if mapped else None,
                    "longitude": float(lng) if mapped else None,
                    "coordinate_status": "map_ready" if mapped else "list_only",
                    "source": {
                        "dataset": row.get("source_dataset") or path.stem,
                        "source_event_id": sid,
                    },
                }
            )

    OUT.write_text(json.dumps({"generated_at_utc": generated, "events": events}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(OUT.relative_to(ROOT)), "events": len(events)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
