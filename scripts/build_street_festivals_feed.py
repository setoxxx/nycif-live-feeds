#!/usr/bin/env python3
"""Ingest NYC street festivals / feasts / parades that the staged pipeline drops.

The staged feed is dominated by ballfield permits and drops the multi-day
Street Festival / feast / parade permits (e.g. the Williamsburg Giglio Feast
of Our Lady of Mount Carmel, a 12-day Street Festival). Those live in the
NYC Permitted Events dataset (tvpp-9vvx / SAPO) as single rows WITH real
start/end dates but WITHOUT coordinates.

This script:
  1. pulls the marquee event types from the live SODA API,
  2. geocodes each street-segment location via NYC GeoSearch (public API),
  3. certifies the result is inside the NYC metro box (no ocean pins),
  4. writes data/nycif_street_festivals_feed.json + a report.

It touches no protected artifacts (no location_cache.json, no GPS/approval
files). Geocode results are cached in data/geosearch_cache.json so reruns are
cheap and kind to the geocoder. Coordinates are never invented — a row that
cannot be geocoded to a valid NYC point is emitted list_only (no pin).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_FEED = ROOT / "data" / "nycif_street_festivals_feed.json"
OUT_REPORT = ROOT / "data" / "nycif_street_festivals_report.json"
CACHE_PATH = ROOT / "data" / "geosearch_cache.json"

SODA = "https://data.cityofnewyork.us/resource/tvpp-9vvx.json"
GEOSEARCH = "https://geosearch.planninglabs.nyc/v2/search"

# Marquee, crowd-drawing, photographable permit types the public map should
# carry. Ballfield/sport permits (which already dominate the staged feed) and
# the very high-volume, low-signal "Special Event" / "Farmers Market" buckets
# are intentionally excluded so this stays a curated, geocodable set.
EVENT_TYPES = [
    "Street Festival",
    "Single Block Festival",
    "Parade",
    "Block Party",
    "Religious Event",
    "Concert",
    "Health Fair",
    "Athletic Race/Tour",
]

# Marquee title keywords. NYC files the crowd-drawing, News-Desk-worthy events
# (FIFA House, FIFA World Cup, Thai SELECT Cultural Festival, San Gennaro, the
# Giglio feast) under low-signal permit *types* like "Production Event",
# "Plaza Partner Event" and "Street Event" — so an event_type filter alone drops
# them. We also match on the event NAME so those surface regardless of type.
# These map to the frontend medal engine's MARQUEE_RE so the News Desk agrees.
MARQUEE_LIKE = [
    "FIFA", "WORLD CUP", "FEAST", "FESTIVAL", "PARADE", "CARNIVAL",
    "GIGLIO", "SAN GENNARO", "FAN FEST", "FAN ZONE", "MARATHON",
    "CULTURAL", "PROCESSION",
]
WINDOW_DAYS = 90

NYC = dict(min_lat=40.4774, max_lat=40.9176, min_lng=-74.2591, max_lng=-73.7004)
BOROUGH_NAMES = {
    "manhattan": "Manhattan", "brooklyn": "Brooklyn", "queens": "Queens",
    "bronx": "Bronx", "staten island": "Staten Island",
}


def _get(url: str, tries: int = 3):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - network best effort
            last = exc
            time.sleep(0.5 * (attempt + 1))
    print(f"  request failed: {url} -> {last}", file=sys.stderr)
    return None


def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def in_nyc(lat: float, lng: float) -> bool:
    return (NYC["min_lat"] <= lat <= NYC["max_lat"]
            and NYC["min_lng"] <= lng <= NYC["max_lng"])


def primary_street(location: str) -> str:
    """Reduce a segment description to a geocodable house address.

    "HAVEMEYER STREET between METROPOLITAN AVENUE and NORTH 9 STREET"
        -> "1 Havemeyer Street"
    """
    text = str(location or "").strip()
    if not text:
        return ""
    # Cut at the first segment/range keyword.
    text = re.split(r"\b(between|from|and|,|:)\b", text, flags=re.IGNORECASE)[0].strip()
    text = " ".join(w.capitalize() for w in text.split())
    if not text:
        return ""
    return f"1 {text}"


def geocode(location: str, borough: str, cache: dict):
    """Return (lat, lng, label) or (None, None, reason). Cached by query."""
    street = primary_street(location)
    if not street:
        return None, None, "no_street"
    boro = BOROUGH_NAMES.get(str(borough or "").lower(), "")
    query = f"{street}, {boro}, NY" if boro else f"{street}, NY"
    if query in cache:
        c = cache[query]
        return c.get("lat"), c.get("lng"), c.get("label") or "cache"
    url = f"{GEOSEARCH}?text={urllib.parse.quote(query)}&size=1"
    data = _get(url)
    time.sleep(0.1)  # be kind to the geocoder
    feats = (data or {}).get("features") or []
    if not feats:
        cache[query] = {"lat": None, "lng": None, "label": None}
        return None, None, "geocode_miss"
    lng, lat = feats[0]["geometry"]["coordinates"]
    label = feats[0]["properties"].get("label")
    if not in_nyc(lat, lng):
        cache[query] = {"lat": None, "lng": None, "label": label}
        return None, None, "out_of_box"
    cache[query] = {"lat": lat, "lng": lng, "label": label}
    return lat, lng, label


def valid_day(value: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(value or ""))
    if not m:
        return ""
    try:
        datetime.strptime(m.group(1), "%Y-%m-%d")
        return m.group(1)
    except ValueError:
        return ""


def _fetch_where(where: str) -> list:
    url = f"{SODA}?$where={urllib.parse.quote(where)}&$limit=5000"
    return _get(url) or []


def fetch_rows() -> list:
    """Pull curated marquee *types* AND marquee-*titled* events, then dedupe.

    Two queries, unioned on event_id so a Production/Plaza permit named
    "FIFA House..." is captured alongside a "Street Festival" typed row.
    """
    today = date.today()
    end = today + timedelta(days=WINDOW_DAYS)
    window = (
        f"end_date_time >= '{today.isoformat()}T00:00:00' "
        f"AND start_date_time <= '{end.isoformat()}T23:59:59'"
    )

    types = ",".join("'" + t.replace("'", "''") + "'" for t in EVENT_TYPES)
    by_type = _fetch_where(f"event_type in({types}) AND {window}")

    likes = " OR ".join(
        f"upper(event_name) like '%{kw}%'" for kw in MARQUEE_LIKE
    )
    by_name = _fetch_where(f"({likes}) AND {window}")

    merged: dict[str, dict] = {}
    for r in by_type + by_name:
        key = str(r.get("event_id") or r.get("cemsid") or id(r))
        merged.setdefault(key, r)
    return list(merged.values())


def main() -> int:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows = fetch_rows()
    cache = load_cache()

    events = []
    demoted = []
    by_type: dict[str, int] = {}
    for r in rows:
        start = valid_day(r.get("start_date_time"))
        end = valid_day(r.get("end_date_time")) or start
        if not start:
            continue
        etype = r.get("event_type") or "Special Event"
        by_type[etype] = by_type.get(etype, 0) + 1
        lat, lng, why = geocode(r.get("event_location"), r.get("event_borough"), cache)
        base = {
            "id": f"sapo:{r.get('event_id') or r.get('cemsid')}",
            "cemsid": r.get("cemsid"),
            "event_id": r.get("event_id"),
            "title": r.get("event_name") or "NYC event",
            "event_type": etype,
            "start_date_time": r.get("start_date_time"),
            "end_date_time": r.get("end_date_time"),
            "start_date": start,
            "end_date": end,
            "multi_day": end > start,
            "borough": BOROUGH_NAMES.get(str(r.get("event_borough") or "").lower(),
                                         r.get("event_borough")),
            "display_location": r.get("event_location"),
            "street_closure_type": r.get("street_closure_type"),
            "source": {"dataset": "tvpp-9vvx", "source_event_id": str(r.get("event_id") or "")},
        }
        if lat is not None and lng is not None:
            base.update({"latitude": lat, "longitude": lng,
                         "coordinate_status": "map_ready", "certified_pin": True,
                         "pin_integrity_reason": "ok_nyc_geosearch"})
            events.append(base)
        else:
            base.update({"latitude": None, "longitude": None,
                         "coordinate_status": "list_only", "certified_pin": False,
                         "pin_integrity_reason": why})
            demoted.append(base)

    CACHE_PATH.write_text(json.dumps(cache, indent=1), encoding="utf-8")

    payload = {
        "schema_version": "street-festivals-v1",
        "generated_at_utc": generated,
        "window_days": WINDOW_DAYS,
        "source": "NYC Permitted Events (tvpp-9vvx / SAPO) via SODA",
        "premium_label": "NYC Street Festivals, Feasts & Parades",
        "total": len(events),
        "list_only": len(demoted),
        "multi_day": sum(1 for e in events if e["multi_day"]),
        "events": events + demoted,
    }
    OUT_FEED.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    giglio = next((e for e in events
                   if "carmel" in (e["title"] or "").lower()
                   and e["event_type"] == "Street Festival"), None)
    report = {
        "generated_at_utc": generated,
        "fetched_rows": len(rows),
        "map_ready": len(events),
        "list_only": len(demoted),
        "multi_day_map_ready": payload["multi_day"],
        "by_event_type": by_type,
        "giglio_feast_mapped": bool(giglio),
        "giglio_feast": giglio,
        "qa_pass": len(events) > 0,
    }
    OUT_REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ("fetched_rows", "map_ready", "list_only",
                       "multi_day_map_ready", "giglio_feast_mapped", "qa_pass")},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
