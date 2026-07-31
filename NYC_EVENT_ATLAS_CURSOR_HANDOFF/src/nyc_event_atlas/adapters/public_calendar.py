"""NYC public events calendar adapter.

Prefers an offline/local snapshot (e.g. nycif citywide calendar snapshot) because
nyc.gov robots.txt disallows automated HTML crawling of /main/events/.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from ..normalize import clean_text
from ..review_ingest import ensure_source, queue_normalized_candidates, save_snapshot
from .common import base_record, guess_borough, parse_clock, parse_iso_date

SOURCE_ID = "nyc_public_events_calendar"
ROOT = Path(__file__).resolve().parents[3]

BOROUGH_CODE = {
    "mn": "Manhattan",
    "bk": "Brooklyn",
    "qn": "Queens",
    "bx": "The Bronx",
    "si": "Staten Island",
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "The Bronx",
    "the bronx": "The Bronx",
    "staten island": "Staten Island",
    "citywide": "Citywide",
}

# Routine recurring programs that should not flood the Atlas review queue.
_SKIP_TITLE = (
    "lap swim",
    "pool hours",
    "outdoor pool",
    "pickleball",
    "soccer clinic",
    "basketball clinic",
    "yoga in the park",
    "storytime",
    "drop-in",
    "kids in motion",
    "kim:",
    "session 1:",
    "session 2:",
    "summer sports experience",
    "summer sport experience",
    "nyrr open run",
    "zumba",
    "cardio sculpt",
    "recreation center summer camp",
    "wheel fun rentals",
    "ongoing outdoor museum exhibit",
)

# Atlas editorial keep signals — prefer festivals/fairs/parades over routine rec.
_KEEP_SIGNALS = (
    "festival",
    "fest ",
    "fair",
    "parade",
    "feast",
    "carnival",
    "concert",
    "market",
    "block party",
    "street fair",
    "procession",
    "celebration",
    "holiday",
    "lighting",
    "menorah",
    "new year",
    "firework",
    "film festival",
    "cultural",
    "heritage",
    "jubilee",
)


def _iter_events(payload: Any):
    if isinstance(payload, list):
        for x in payload:
            if isinstance(x, dict):
                yield x
        return
    if isinstance(payload, dict):
        for key in ("items", "events", "results", "data", "rows"):
            val = payload.get(key)
            if isinstance(val, list):
                for x in val:
                    if isinstance(x, dict):
                        yield x
                return
        yield payload


def _borough_from_row(row: dict) -> str:
    boroughs = row.get("boroughs")
    if isinstance(boroughs, list) and boroughs:
        mapped = []
        for b in boroughs:
            label = BOROUGH_CODE.get(str(b).strip().lower())
            if label:
                mapped.append(label)
        uniq = sorted(set(mapped))
        if len(uniq) == 1:
            return uniq[0]
        if len(uniq) > 1:
            return "Citywide"
    for key in ("borough", "BOROUGH", "location_borough"):
        raw = row.get(key)
        if raw:
            label = BOROUGH_CODE.get(str(raw).strip().lower())
            if label:
                return label
            guessed = guess_borough(str(raw))
            if guessed != "Unknown":
                return guessed
    return guess_borough(
        row.get("title") or "",
        row.get("address") or "",
        row.get("short_description") or "",
    )


def map_calendar_row(
    row: dict,
    *,
    window_start: date,
    window_end: date,
    verified_on: str,
) -> dict | None:
    if row.get("canceled") is True:
        return None
    start = parse_iso_date(
        row.get("start_date_time")
        or row.get("start_date")
        or row.get("startdate")
        or row.get("date")
        or row.get("startDate")
        or row.get("start")
    )
    if start == "Unknown":
        return None
    try:
        d = date.fromisoformat(start)
    except ValueError:
        return None
    if d < window_start or d > window_end:
        return None

    name = clean_text(
        row.get("title") or row.get("name") or row.get("event_name") or row.get("EVENT_NAME")
    )
    if name == "Unknown":
        return None
    low = name.lower()
    if any(x in low for x in _SKIP_TITLE):
        return None
    cats = row.get("categories") or row.get("category") or []
    if isinstance(cats, list):
        cat_blob = " ".join(str(c) for c in cats).lower()
    else:
        cat_blob = str(cats).lower()
    # Prefer street/neighborhood festivals and explicit editorial signals.
    keep = any(x in low for x in _KEEP_SIGNALS) or any(
        x in cat_blob for x in ("street and neighborhood", "festival", "parade", "cultural", "holiday")
    )
    if not keep:
        return None

    loc = clean_text(
        row.get("address")
        or row.get("location")
        or row.get("venue")
        or row.get("park_name")
        or "Unknown"
    )
    borough = _borough_from_row(row)
    if borough == "Unknown":
        return None

    link = clean_text(
        row.get("permalink")
        or row.get("url")
        or row.get("link")
        or row.get("website")
        or "https://www.nyc.gov/main/events/"
    )
    end = parse_iso_date(
        row.get("end_date_time") or row.get("end_date") or row.get("enddate") or row.get("end")
    )
    cats = row.get("categories") or row.get("category") or []
    if isinstance(cats, list):
        cat_text = clean_text(cats[0]) if cats else "Citywide Calendar"
    else:
        cat_text = clean_text(cats) if cats else "Citywide Calendar"
    organizer = clean_text(
        row.get("agency_name") or row.get("organizer") or row.get("agency") or "NYC Public Events"
    )
    uid = row.get("source_event_id") or row.get("source_guid") or row.get("uid") or name
    return base_record(
        name=name,
        start_date=start,
        end_date=end if end != "Unknown" else start,
        start_time=parse_clock(row.get("time_part") or row.get("start_time") or row.get("starttime")),
        end_time=parse_clock(row.get("end_time") or row.get("endtime")),
        borough=borough,
        venue=loc,
        organizer=organizer,
        category="Community Program",
        subcategory=cat_text[:80] if cat_text != "Unknown" else "Citywide Calendar",
        status="Confirmed",
        confidence="High",
        primary_source=link,
        website=link,
        notes="Mapped from NYC public/citywide calendar snapshot. No inferred coords.",
        verified_on=verified_on,
        permit_id=f"pubcal:{uid}:{start}",
    )


def fetch_public_calendar(
    conn: sqlite3.Connection,
    *,
    window_start: date,
    window_end: date,
    offline_snapshot: Path | None = None,
) -> dict:
    ensure_source(
        conn,
        source_id=SOURCE_ID,
        name="NYC Upcoming Public Events / Citywide Calendar",
        base_url="https://www.nyc.gov",
        authority="official_government",
        confidence="High",
        method="offline_snapshot_or_api",
    )

    candidates = []
    if offline_snapshot:
        candidates.append(Path(offline_snapshot))
    candidates.extend(
        [
            ROOT / "data" / "nyc_citywide_events_calendar_snapshot.json",
            Path("/workspace/data/nyc_citywide_events_calendar_snapshot.json"),
            Path("data/nyc_citywide_events_calendar_snapshot.json"),
        ]
    )
    path = next((p for p in candidates if p and p.exists()), None)
    if path is None:
        return {
            "skipped": True,
            "reason": "No offline citywide calendar snapshot available; nyc.gov HTML is robots-disallowed.",
            "mapped_rows": 0,
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = list(_iter_events(payload))
    verified_on = date.today().isoformat()
    records = []
    for row in rows:
        mapped = map_calendar_row(
            row, window_start=window_start, window_end=window_end, verified_on=verified_on
        )
        if mapped:
            records.append(mapped)

    body = path.read_bytes()
    sha = hashlib.sha256(body).hexdigest()
    meta = {
        "url": str(path),
        "status": 200,
        "content_type": "application/json",
        "etag": None,
        "last_modified": None,
        "sha256": sha,
        "local_path": str(path),
        "robots_policy": "offline_snapshot",
    }
    snapshot_id = save_snapshot(
        conn,
        source_id=SOURCE_ID,
        meta=meta,
        params={"snapshot": str(path), "window_start": window_start.isoformat()},
        parser_version="public_calendar_snapshot_v2",
    )
    report = queue_normalized_candidates(
        conn, source_id=SOURCE_ID, snapshot_id=snapshot_id, records=records
    )
    report["mapped_rows"] = len(records)
    report["snapshot_path"] = str(path)
    report["fetched_rows"] = len(rows)
    return report
