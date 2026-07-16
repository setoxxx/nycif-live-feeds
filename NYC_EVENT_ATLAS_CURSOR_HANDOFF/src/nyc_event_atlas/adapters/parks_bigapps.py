"""NYC Parks BigApps events JSON adapter."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

from ..http_client import AtlasHttpClient
from ..normalize import clean_text
from ..review_ingest import ensure_source, queue_normalized_candidates, save_snapshot
from .common import base_record, parse_clock, parse_iso_date, valid_nyc_pair

SOURCE_ID = "nyc_parks_bigapps"
EVENTS_URL = "https://www.nycgovparks.org/xml/events_300_rss.json"
ROOT = Path(__file__).resolve().parents[3]


def _coords(value) -> tuple[str, str]:
    if not value:
        return "Unknown", "Unknown"
    if isinstance(value, dict):
        return valid_nyc_pair(value.get("lat") or value.get("latitude"), value.get("lng") or value.get("longitude") or value.get("lon"))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        # Parks sometimes [lat, lng] or [lng, lat]; prefer values in NYC lat range first.
        a, b = value[0], value[1]
        try:
            fa, fb = float(a), float(b)
        except (TypeError, ValueError):
            return "Unknown", "Unknown"
        if 40.4 <= fa <= 41.0 and -74.3 <= fb <= -73.6:
            return valid_nyc_pair(fa, fb)
        if 40.4 <= fb <= 41.0 and -74.3 <= fa <= -73.6:
            return valid_nyc_pair(fb, fa)
    return "Unknown", "Unknown"


def map_parks_row(row: dict, *, window_start: date, window_end: date, verified_on: str) -> dict | None:
    start = parse_iso_date(row.get("startdate"))
    if start == "Unknown":
        return None
    try:
        d = date.fromisoformat(start)
    except ValueError:
        return None
    if d < window_start or d > window_end:
        return None
    end = parse_iso_date(row.get("enddate"))
    title = clean_text(row.get("title"))
    # Skip routine sports clinics unless named festival/parade/concert keywords.
    low = title.lower()
    if any(x in low for x in ("pickleball", "soccer clinic", "basketball clinic", "practice")):
        if not any(x in low for x in ("festival", "parade", "concert", "movie", "market", "feast")):
            return None
    parks = clean_text(row.get("parknames") or row.get("location"))
    cats = row.get("categories") or []
    if isinstance(cats, str):
        cats = [cats]
    subcategory = clean_text(cats[0]) if cats else "Parks Program"
    lat, lng = _coords(row.get("coordinates"))
    link = clean_text(row.get("link") or EVENTS_URL)
    borough = "Unknown"
    if lat != "Unknown":
        from .common import borough_from_coords

        borough = borough_from_coords(lat, lng)
    return base_record(
        name=title,
        start_date=start,
        end_date=end if end != "Unknown" else start,
        start_time=parse_clock(row.get("starttime")),
        end_time=parse_clock(row.get("endtime")),
        borough=borough,
        venue=parks,
        organizer="NYC Parks",
        category="Parks Program",
        subcategory=subcategory,
        status="Confirmed",
        confidence="High",
        primary_source=link,
        website=link,
        notes=f"Parks BigApps guid={row.get('guid')}; parkids={row.get('parkids')}",
        lat=lat,
        lng=lng,
        verified_on=verified_on,
        permit_id=f"parks:{row.get('guid')}" if row.get("guid") else "Unknown",
    )


def fetch_parks_bigapps(
    conn: sqlite3.Connection,
    *,
    window_start: date,
    window_end: date,
    offline_snapshot: Path | None = None,
) -> dict:
    ensure_source(
        conn,
        source_id=SOURCE_ID,
        name="NYC Parks BigApps Events",
        base_url="https://www.nycgovparks.org",
        authority="official_government",
        confidence="High",
        method="bigapps_json",
    )
    verified_on = date.today().isoformat()
    if offline_snapshot and offline_snapshot.exists():
        payload = json.loads(offline_snapshot.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("events") or payload.get("items") or []
        body = offline_snapshot.read_bytes()
        import hashlib

        sha = hashlib.sha256(body).hexdigest()
        meta = {
            "url": str(offline_snapshot),
            "status": 200,
            "content_type": "application/json",
            "etag": None,
            "last_modified": None,
            "sha256": sha,
            "local_path": str(offline_snapshot),
            "robots_policy": "offline_snapshot",
        }
    else:
        client = AtlasHttpClient(cache_dir=str(ROOT / "data" / "raw"), robots_policy="official_feed")
        response, meta = client.get(EVENTS_URL, ext_hint=".json")
        rows = response.json()
        if not isinstance(rows, list):
            rows = rows.get("events") or rows.get("items") or []

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        mapped = map_parks_row(row, window_start=window_start, window_end=window_end, verified_on=verified_on)
        if mapped and mapped.get("BOROUGH") != "Unknown":
            records.append(mapped)
        elif mapped:
            # Keep with Unknown borough only if park name embeds borough; else skip invalid.
            # Try park location text again via notes.
            from .common import guess_borough

            b = guess_borough(mapped["EVENT_NAME"], mapped["VENUE"], mapped["RESEARCH_NOTES"])
            if b != "Unknown":
                mapped["BOROUGH"] = b
                records.append(mapped)

    snapshot_id = save_snapshot(
        conn,
        source_id=SOURCE_ID,
        meta=meta,
        params={"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        parser_version="parks_bigapps_v1",
    )
    report = queue_normalized_candidates(
        conn, source_id=SOURCE_ID, snapshot_id=snapshot_id, records=records
    )
    report["fetched_rows"] = len(rows)
    report["mapped_rows"] = len(records)
    return report
