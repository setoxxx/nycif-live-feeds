#!/usr/bin/env python3
"""Build the comprehensive, categorized public event feed ("100% of the city").

The public map historically shows only the ~800 "major" discovery events. This
builder takes the FULL already-coordinated staged live feed (every NYC permitted
event, all 31 event types) and turns it into one public feed the frontend can
show in full, organized into the existing category taxonomy with a raw
event_type preserved for rich filtering.

What it adds on top of the staged rows:
  * category            — every one of NYC's 31 permit types mapped to a
                          category slug (see NYC_TYPE_CATEGORY). Types with no
                          natural home fall back to the staged row's own
                          category, then "general". Nothing is dropped.
  * event_type          — the raw NYC permit type, so the frontend can build a
                          fine-grained filter and gray out empty lanes.
  * multi_day / span    — true start_date -> end_date span.
  * is_past             — end_date < today at build time (a hint; the frontend
                          recomputes this live against the viewer's date so
                          "past = grayed" is always accurate without a rebuild).
  * first_seen_utc / is_new
                        — stable per-event first-seen stamp via a persisted
                          seen-index, so the admin "What's New" panel can
                          separate already-tracked events from newly-arrived
                          permits. is_new = event_id not tracked before this run.

Safety: reads only the staged feed + its own seen-index. Does NOT touch
location_cache.json, GPS/approval artifacts, or raw source datasets. Coordinates
are never invented — a row whose coordinates are missing or outside the NYC box
is emitted list_only (no pin), never relocated.

Outputs:
  data/schema-v1-discovery/all/events.json    comprehensive feed (major-shaped)
  data/schema-v1-discovery/all/manifest.json  small manifest
  data/nycif_new_events.json                  admin "What's New" diff
  data/comprehensive_feed_report.json         per-category / per-type counts
  data/_event_seen_index.json                 persisted first-seen index
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STAGED = DATA / "nycif_staged_live_events.json"

OUT_DIR = DATA / "schema-v1-discovery" / "all"
OUT_FEED = OUT_DIR / "events.json"
OUT_MANIFEST = OUT_DIR / "manifest.json"
OUT_NEW = DATA / "nycif_new_events.json"
OUT_REPORT = DATA / "comprehensive_feed_report.json"
SEEN_INDEX = DATA / "_event_seen_index.json"

# Keep recent past (grayed) + everything forward. Bounds "100%" so the feed and
# the daily refresh stay cheap; older-than-PAST_WINDOW permits drop off.
PAST_WINDOW_DAYS = 14

NYC = {"min_lat": 40.4774, "max_lat": 40.9176, "min_lng": -74.2591, "max_lng": -73.7004}

# Complete map of NYC's published permit types -> our existing category slugs.
# "media" is the one added lane: the production / film / press family is a
# distinct, operator-valuable group ("money shots") with no home in the base
# taxonomy. Everything here maps to a category so no permit type is orphaned;
# the frontend grays any category chip whose count is 0.
NYC_TYPE_CATEGORY: dict[str, str] = {
    "open culture": "arts",
    "public program/exhibitions": "arts",
    "concert": "arts",
    "single block festival": "arts",
    "street festival": "arts",
    "athletic-charitable": "sports",
    "athletic race / tour": "sports",
    "athletic race/tour": "sports",
    "marathon": "sports",
    "sport - youth": "sports",
    "sport - adult": "sports",
    "farmers market": "market",
    "sidewalk sale": "market",
    "block party": "civic",
    "parade": "civic",
    "play streets": "civic",
    "street event": "civic",
    "open street partner event": "civic",
    "religious event": "civic",
    "rally": "civic",
    "stationary demonstration": "civic",
    "clean-up": "environment",
    "health fair": "services",
    "mobile unit": "services",
    "plaza event": "parks",
    "plaza partner event": "parks",
    "dcas prep/shoot/wrap permit": "media",
    "press conference": "media",
    "production event": "media",
    "red carpet event": "media",
    "rigging permit": "media",
    "shooting permit": "media",
    "theater load in and load outs": "media",
    "special event": "general",
    "miscellaneous": "general",
}


def load_json(path: Path, default):
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")


def day_of(value) -> str:
    return str(value or "")[:10]


def valid_coord(lat, lng) -> bool:
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    if abs(lat) < 1e-9 and abs(lng) < 1e-9:  # null island
        return False
    return (NYC["min_lat"] <= lat <= NYC["max_lat"]
            and NYC["min_lng"] <= lng <= NYC["max_lng"])


def category_for(row: dict) -> str:
    etype = str(row.get("event_type") or "").strip().lower()
    if etype in NYC_TYPE_CATEGORY:
        return NYC_TYPE_CATEGORY[etype]
    existing = str(row.get("category") or "").strip().lower()
    return existing or "general"


def main() -> int:
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    today = date.today()
    floor_day = (today - timedelta(days=PAST_WINDOW_DAYS)).isoformat()
    today_iso = today.isoformat()

    staged = load_json(STAGED, {})
    rows = staged.get("events") if isinstance(staged, dict) else (staged or [])

    seen = load_json(SEEN_INDEX, {})
    # "New" means an event_id we had never tracked before THIS run — a permit
    # that arrived since the last refresh. `known` is the id set as of run start;
    # anything outside it is new. A first-ever build (empty index) is a baseline:
    # stamp every id but flag nothing new, so the admin panel isn't flooded with
    # 30k false positives. Real deltas surface from the second run onward.
    known = set(seen.keys())
    baseline_run = not seen
    events, list_only = [], []
    by_cat, by_type, new_events = Counter(), Counter(), []
    dropped_old = 0

    for r in rows:
        start = day_of(r.get("start_date_time"))
        end = day_of(r.get("end_date_time")) or start
        if not start:
            continue
        if end < floor_day:  # older than the rolling past window
            dropped_old += 1
            continue

        # Each staged row is a single-DAY instance of a permit (a 30-day permit
        # appears as 30 rows sharing one permit id). Key per-instance by
        # permit-id@start-day so ids are unique and the seen-index tracks each
        # day-instance, matching the discovery feed's @date convention.
        permit_id = str(r.get("id") or f"{r.get('source_dataset')}:{r.get('source_event_id')}")
        eid = f"{permit_id}@{start}"
        is_new = (not baseline_run) and (eid not in known)
        first_seen = seen.get(eid) or generated
        seen[eid] = first_seen

        etype = r.get("event_type") or "Special Event"
        category = category_for(r)
        lat, lng = r.get("lat"), r.get("lng")
        mapped = valid_coord(lat, lng)

        event = {
            "schema_version": "1.0",
            "id": eid,
            "title": r.get("title") or "NYC event",
            "category": category,
            "event_type": etype,
            "start_date_time": r.get("start_date_time"),
            "end_date_time": r.get("end_date_time"),
            "start_date": start,
            "end_date": end,
            "multi_day": end > start,
            "is_past": end < today_iso,
            "first_seen_utc": first_seen,
            "is_new": is_new,
            "timezone": "America/New_York",
            "borough": r.get("borough"),
            "location": r.get("display_location") or r.get("location"),
            "street_closure_type": r.get("street_closure_type"),
            "latitude": float(lat) if mapped else None,
            "longitude": float(lng) if mapped else None,
            "source": {
                "dataset": r.get("source_dataset") or "tvpp-9vvx",
                "source_event_id": str(r.get("source_event_id") or ""),
            },
            "nycif": {
                "coordinate_status": "map_ready" if mapped else "list_only",
                "certified_pin": bool(mapped),
            },
        }
        by_type[etype] += 1
        by_cat[category] += 1
        (events if mapped else list_only).append(event)
        if is_new:
            new_events.append({k: event[k] for k in
                               ("id", "title", "category", "event_type",
                                "start_date", "end_date", "borough",
                                "first_seen_utc")})

    # Fold in the street-festivals feed when present. The staged snapshot is
    # sports-heavy and drops the multi-day Street Festival / feast / marquee
    # permits (Giglio feast, FIFA House) that live in build_street_festivals_feed
    # output. Union by source_event_id so nothing double-counts; those rows are
    # already geocoded + NYC-certified by that builder.
    have_ids = {e["source"]["source_event_id"] for e in events + list_only
                if e["source"]["source_event_id"]}
    fest = load_json(DATA / "nycif_street_festivals_feed.json", {})
    for r in (fest.get("events") if isinstance(fest, dict) else []) or []:
        sid = str((r.get("source") or {}).get("source_event_id")
                  or r.get("event_id") or "")
        if not sid or sid in have_ids:
            continue
        start = day_of(r.get("start_date_time")) or r.get("start_date")
        end = day_of(r.get("end_date_time")) or r.get("end_date") or start
        if not start or end < floor_day:
            continue
        eid = r.get("id") or f"sapo:{sid}"
        fold_is_new = (not baseline_run) and (eid not in known)
        first_seen = seen.get(eid) or generated
        seen[eid] = first_seen
        mapped = r.get("coordinate_status") == "map_ready" and valid_coord(
            r.get("latitude"), r.get("longitude"))
        category = category_for(r)
        event = {
            "schema_version": "1.0", "id": eid,
            "title": r.get("title") or "NYC event", "category": category,
            "event_type": r.get("event_type") or "Street Festival",
            "start_date_time": r.get("start_date_time"),
            "end_date_time": r.get("end_date_time"),
            "start_date": start, "end_date": end, "multi_day": end > start,
            "is_past": end < today_iso, "first_seen_utc": first_seen,
            "is_new": fold_is_new,
            "timezone": "America/New_York", "borough": r.get("borough"),
            "location": r.get("display_location") or r.get("location"),
            "street_closure_type": r.get("street_closure_type"),
            "latitude": r.get("latitude") if mapped else None,
            "longitude": r.get("longitude") if mapped else None,
            "source": {"dataset": "tvpp-9vvx", "source_event_id": sid},
            "nycif": {"coordinate_status": "map_ready" if mapped else "list_only",
                      "certified_pin": bool(mapped)},
        }
        by_type[event["event_type"]] += 1
        by_cat[category] += 1
        have_ids.add(sid)
        (events if mapped else list_only).append(event)
        if fold_is_new:
            new_events.append({k: event[k] for k in
                               ("id", "title", "category", "event_type",
                                "start_date", "end_date", "borough",
                                "first_seen_utc")})

    all_events = events + list_only
    save_json(SEEN_INDEX, seen)

    payload = {
        "schema_version": "comprehensive-v1",
        "generated_at_utc": generated,
        "classification_version": "categories-v01+nyc-types",
        "window": {"past_floor": floor_day, "today": today_iso},
        "total": len(all_events),
        "map_ready": len(events),
        "list_only": len(list_only),
        "new_this_run": len(new_events),
        "category_counts": dict(by_cat),
        "event_type_counts": dict(by_type),
        "events": all_events,
    }
    save_json(OUT_FEED, payload)
    save_json(OUT_MANIFEST, {
        "schema_version": "comprehensive-v1",
        "generated_at_utc": generated,
        "total": len(all_events),
        "map_ready": len(events),
        "list_only": len(list_only),
        "new_this_run": len(new_events),
        "feed": "schema-v1-discovery/all/events.json",
    })
    save_json(OUT_NEW, {
        "generated_at_utc": generated,
        "new_definition": "event_id not tracked before this refresh run",
        "baseline_run": baseline_run,
        "total_tracked": len(all_events),
        "new_this_run": len(new_events),
        "events": sorted(new_events, key=lambda e: e["start_date"]),
    })
    save_json(OUT_REPORT, {
        "generated_at_utc": generated,
        "source_rows": len(rows),
        "kept": len(all_events),
        "dropped_older_than_window": dropped_old,
        "map_ready": len(events),
        "list_only": len(list_only),
        "multi_day": sum(1 for e in all_events if e["multi_day"]),
        "past_in_window": sum(1 for e in all_events if e["is_past"]),
        "new_this_run": len(new_events),
        "category_counts": dict(by_cat),
        "event_type_counts": dict(by_type),
        "qa_pass": len(events) > 0,
    })
    print(json.dumps({
        "source_rows": len(rows), "kept": len(all_events),
        "map_ready": len(events), "list_only": len(list_only),
        "multi_day": payload_multi(all_events), "new_this_run": len(new_events),
        "categories": len(by_cat), "event_types": len(by_type),
    }, indent=1))
    return 0


def payload_multi(events) -> int:
    return sum(1 for e in events if e["multi_day"])


if __name__ == "__main__":
    raise SystemExit(main())
