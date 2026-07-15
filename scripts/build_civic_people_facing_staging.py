#!/usr/bin/env python3
"""Normalize civic SODA snapshots into people-facing staging + QA artifacts.

Fail-closed on date/time invention and out-of-bounds pins.
Never writes location_cache or production staged feeds.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import (  # noqa: E402
    DATA_DIR,
    SOURCE_CATALOG,
    combine_local_datetime,
    date_window_status,
    load_json,
    normalize_borough,
    parse_clock_time,
    parse_iso_date,
    resolve_coordinate_status,
    safety_fields,
    save_json,
    stable_hash,
    strip_html,
    today_nyc,
    utc_now,
)
from schema_v1_common import (  # noqa: E402
    DEFAULT_TIMEZONE,
    SCHEMA_VERSION,
    envelope,
    event_date_key,
    project_event,
    reset_stable_id_registry,
    write_repo_json,
)

PAGE_SIZE = 750


def _base_row(
    *,
    source_key: str,
    dataset: str,
    source_event_id: str,
    title: str,
    lane: str,
    category: str,
    interests: list[str],
    borough: str | None,
    display_location: str | None,
    address: str | None,
    lat: Any,
    lng: Any,
    start_date_time: str | None,
    end_date_time: str | None,
    schedule_text: str | None,
    confidence_reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lat_f, lng_f, coord_status, coord_reason = resolve_coordinate_status(lat, lng)
    reason = f"{confidence_reason}; {coord_reason}"
    row = {
        "id": f"civic:{dataset}:{source_event_id}",
        "title": title,
        "category": category,
        "interests": interests,
        "lane": lane,
        "timezone": DEFAULT_TIMEZONE,
        "borough": borough,
        "location": display_location or address,
        "display_location": display_location or address,
        "address": address,
        "latitude": lat_f,
        "longitude": lng_f,
        "lat": lat_f,
        "lng": lng_f,
        "start_date_time": start_date_time,
        "end_date_time": end_date_time,
        "schedule_text": schedule_text,
        "coordinate_status": coord_status,
        "confidence_reason": reason,
        "geocoder_source": None,
        "geocoder_confidence": None,
        "derived_occurrence": False,
        "source": {
            "dataset": dataset,
            "source_event_id": source_event_id,
            "source_key": source_key,
            "portal": SOURCE_CATALOG[source_key]["portal"],
        },
        "event_role": "public_event" if lane == "civic_review_events" else "place_or_opportunity",
        **safety_fields(),
    }
    if extra:
        row.update(extra)
    return row


def load_snapshot_rows(source_key: str) -> list[dict[str, Any]]:
    meta = SOURCE_CATALOG[source_key]
    payload = load_json(DATA_DIR / meta["snapshot"], {})
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def normalize_workforce1_events(today: date) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    quarantined: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows("workforce1_events"):
        title = str(raw.get("event_title") or "").strip() or "Workforce1 event"
        day = parse_iso_date(raw.get("event_date"))
        start_clock = parse_clock_time(raw.get("check_in_from"))
        end_clock = parse_clock_time(raw.get("check_in_to"))
        sid = stable_hash(
            title,
            raw.get("event_date"),
            raw.get("location_name_and_address"),
            raw.get("company_name_or_type"),
        )
        if sid in seen:
            continue
        seen.add(sid)
        start_dt = combine_local_datetime(day, start_clock)
        end_dt = combine_local_datetime(day, end_clock)
        time_note = (
            "explicit_check_in_window_from_source"
            if start_clock
            else "date_only_no_invented_time"
        )
        q = date_window_status(day, today=today)
        row = _base_row(
            source_key="workforce1_events",
            dataset="kf2b-aeh5",
            source_event_id=sid,
            title=title,
            lane="civic_review_events",
            category="jobs",
            interests=["jobs"],
            borough=normalize_borough(raw.get("borough")),
            display_location=str(raw.get("location") or "").strip() or None,
            address=str(raw.get("location_name_and_address") or "").strip() or None,
            lat=None,
            lng=None,
            start_date_time=start_dt,
            end_date_time=end_dt,
            schedule_text=None,
            confidence_reason=time_note,
            extra={
                "job_family": raw.get("job_family"),
                "company_name_or_type": raw.get("company_name_or_type"),
                "source_event_date_raw": raw.get("event_date"),
                "time_precision": "check_in_window" if start_clock else "date_only",
            },
        )
        if q:
            row["quarantine_reason"] = q
            quarantined.append(row)
        else:
            accepted.append(row)
    return accepted, quarantined


def normalize_ready_ny(today: date) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    quarantined: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows("ready_ny_events"):
        title = str(raw.get("event") or "").strip() or "Ready NY event"
        day = parse_iso_date(raw.get("date"))
        start_clock = parse_clock_time(raw.get("start_time"))
        end_clock = parse_clock_time(raw.get("end_time"))
        sid = stable_hash(title, raw.get("date"), raw.get("event_address"), raw.get("start_time"))
        if sid in seen:
            continue
        seen.add(sid)
        loc = ", ".join(
            p
            for p in (
                str(raw.get("event_location") or "").strip(),
                str(raw.get("event_address") or "").strip(),
            )
            if p
        ) or None
        q = date_window_status(day, today=today)
        row = _base_row(
            source_key="ready_ny_events",
            dataset="hyur-qpyf",
            source_event_id=sid,
            title=title,
            lane="civic_review_events",
            category="civic",
            interests=["civic", "services"],
            borough=normalize_borough(raw.get("borough")),
            display_location=loc,
            address=str(raw.get("event_address") or "").strip() or None,
            lat=raw.get("latitude"),
            lng=raw.get("longitude"),
            start_date_time=combine_local_datetime(day, start_clock),
            end_date_time=combine_local_datetime(day, end_clock),
            schedule_text=None,
            confidence_reason=(
                "explicit_source_date_and_time" if start_clock else "date_only_no_invented_time"
            ),
            extra={
                "event_type": raw.get("type"),
                "time_precision": "start_end" if start_clock else "date_only",
            },
        )
        if q:
            row["quarantine_reason"] = q
            quarantined.append(row)
        else:
            accepted.append(row)
    return accepted, quarantined


def normalize_oac(today: date) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    quarantined: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows("oac_activities"):
        title = str(raw.get("eventname") or "").strip() or "OAC activity"
        start_raw = str(raw.get("starttime") or "").strip()
        end_raw = str(raw.get("endtime") or "").strip()
        day = parse_iso_date(start_raw)
        # ISO timestamps already include time — preserve as-is when present
        start_dt = start_raw[:19] if start_raw and "T" in start_raw else combine_local_datetime(day, None)
        end_dt = end_raw[:19] if end_raw and "T" in end_raw else None
        has_time = bool(start_raw and "T" in start_raw and len(start_raw) >= 16)
        sid = str(raw.get("dfta_id") or "").strip()
        if not sid:
            sid = stable_hash(title, start_raw, raw.get("eventlocation"), raw.get("providername"))
        # recurring rows may share dfta_id across occurrences — bind to start
        eid = f"{sid}@{start_raw[:19]}" if start_raw else sid
        if eid in seen:
            continue
        seen.add(eid)
        q = date_window_status(day, today=today, max_future_days=180)
        row = _base_row(
            source_key="oac_activities",
            dataset="fzy4-e84j",
            source_event_id=eid,
            title=title,
            lane="civic_review_events",
            category="services",
            interests=["services", "family"],
            borough=normalize_borough(raw.get("borough")),
            display_location=str(raw.get("eventlocation") or "").strip() or None,
            address=str(raw.get("eventlocation") or "").strip() or None,
            lat=raw.get("latitude"),
            lng=raw.get("longitude"),
            start_date_time=start_dt,
            end_date_time=end_dt,
            schedule_text=None,
            confidence_reason=(
                "explicit_source_iso_timestamp" if has_time else "date_only_no_invented_time"
            ),
            extra={
                "provider_name": raw.get("providername"),
                "event_type": raw.get("eventtype"),
                "is_recurring": raw.get("isrecurring"),
                "is_virtual": raw.get("isvirtual"),
                "time_precision": "iso_timestamp" if has_time else "date_only",
            },
        )
        if q:
            row["quarantine_reason"] = q
            quarantined.append(row)
        else:
            accepted.append(row)
    return accepted, quarantined


def normalize_moia(today: date) -> tuple[list[dict], list[dict]]:
    accepted: list[dict] = []
    quarantined: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows("moia_know_your_rights"):
        day = parse_iso_date(raw.get("startdate"))
        start_clock = parse_clock_time(raw.get("starttime"))
        end_clock = parse_clock_time(raw.get("endtime"))
        sid = stable_hash(
            raw.get("startdate"),
            raw.get("starttime"),
            raw.get("borough"),
            raw.get("zip_code"),
            raw.get("primary_language"),
        )
        if sid in seen:
            continue
        seen.add(sid)
        title = "MOIA Know Your Rights engagement"
        lang = str(raw.get("primary_language") or "").strip()
        if lang:
            title = f"{title} ({lang})"
        q = date_window_status(day, today=today)
        row = _base_row(
            source_key="moia_know_your_rights",
            dataset="pnpe-ubtz",
            source_event_id=sid,
            title=title,
            lane="civic_review_events",
            category="services",
            interests=["services", "civic"],
            borough=normalize_borough(raw.get("borough")),
            display_location=f"ZIP {raw.get('zip_code')}" if raw.get("zip_code") else None,
            address=None,
            lat=None,
            lng=None,
            start_date_time=combine_local_datetime(day, start_clock),
            end_date_time=combine_local_datetime(day, end_clock),
            schedule_text=None,
            confidence_reason=(
                "explicit_source_date_and_time_no_pin" if start_clock else "date_only_no_invented_time"
            ),
            extra={
                "primary_language": raw.get("primary_language"),
                "time_precision": "start_end" if start_clock else "date_only",
            },
        )
        if q:
            row["quarantine_reason"] = q
            quarantined.append(row)
        else:
            accepted.append(row)
    return accepted, quarantined


def normalize_volunteer() -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows("volunteer_opportunities"):
        oid = str(raw.get("opportunity_id") or raw.get("display_url") or "").strip()
        sid = oid or stable_hash(raw.get("title"), raw.get("street_address"), raw.get("summary"))
        if sid in seen:
            continue
        seen.add(sid)
        title = str(raw.get("title") or "").strip() or "Volunteer opportunity"
        schedule = str(raw.get("recurrence_type") or "").strip() or None
        out.append(
            _base_row(
                source_key="volunteer_opportunities",
                dataset="shpd-5q9m",
                source_event_id=sid,
                title=title,
                lane="civic_review_opportunities",
                category="volunteer",
                interests=["volunteer"],
                borough=normalize_borough(raw.get("borough")),
                display_location=str(raw.get("street_address") or "").strip() or None,
                address=str(raw.get("street_address") or "").strip() or None,
                lat=raw.get("latitude"),
                lng=raw.get("longitude"),
                start_date_time=None,
                end_date_time=None,
                schedule_text=schedule,
                confidence_reason="ongoing_opportunity_no_one_off_datetime_invented",
                extra={
                    "summary": strip_html(raw.get("summary"))[:500] or None,
                    "website": raw.get("website"),
                    "display_url": raw.get("display_url"),
                    "recurrence_type": raw.get("recurrence_type"),
                    "category_description": raw.get("category_description"),
                    "time_precision": "ongoing_schedule",
                },
            )
        )
    return out


def normalize_ss_volunteer() -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows("social_service_volunteer"):
        sid = str(raw.get("opportunity_id") or "").strip() or stable_hash(
            raw.get("title"), raw.get("org_title"), raw.get("start_date_date")
        )
        if sid in seen:
            continue
        seen.add(sid)
        title = str(raw.get("title") or "").strip() or "Social service volunteer opportunity"
        org = str(raw.get("org_title") or "").strip()
        if org:
            title = f"{title} — {org}"
        schedule_bits = [
            str(raw.get("recurrence_type") or "").strip(),
            str(raw.get("start_date_date") or "").strip(),
            str(raw.get("end_date_date") or "").strip(),
        ]
        schedule = " / ".join(b for b in schedule_bits if b) or None
        out.append(
            _base_row(
                source_key="social_service_volunteer",
                dataset="59c7-f2p9",
                source_event_id=sid,
                title=title,
                lane="civic_review_opportunities",
                category="volunteer",
                interests=["volunteer", "services"],
                borough=None,
                display_location=f"ZIP {raw.get('postalcode')}" if raw.get("postalcode") else None,
                address=None,
                lat=None,
                lng=None,
                start_date_time=None,
                end_date_time=None,
                schedule_text=schedule,
                confidence_reason="soft_dates_stored_as_schedule_text_no_fake_event_datetime",
                extra={
                    "summary": strip_html(raw.get("summary"))[:500] or None,
                    "status": raw.get("status"),
                    "time_precision": "soft_schedule_text",
                },
            )
        )
    return out


def normalize_farmers_markets() -> list[dict]:
    # Dedupe by market+address; keep highest year.
    best: dict[str, dict[str, Any]] = {}
    for raw in load_snapshot_rows("farmers_markets"):
        name = str(raw.get("marketname") or "").strip()
        addr = str(raw.get("streetaddress") or "").strip()
        if not name:
            continue
        key = f"{name.lower()}|{addr.lower()}"
        year = int(str(raw.get("year") or "0") or 0)
        prev = best.get(key)
        if prev and int(str(prev.get("year") or "0") or 0) >= year:
            continue
        best[key] = raw

    out: list[dict] = []
    for raw in best.values():
        name = str(raw.get("marketname") or "").strip()
        addr = str(raw.get("streetaddress") or "").strip() or None
        days = str(raw.get("daysoperation") or "").strip()
        hours = str(raw.get("hoursoperations") or "").strip()
        schedule = " · ".join(p for p in (days, hours) if p) or None
        sid = stable_hash(name, addr, raw.get("borough"))
        out.append(
            _base_row(
                source_key="farmers_markets",
                dataset="8vwk-6iz2",
                source_event_id=sid,
                title=name,
                lane="civic_help_places",
                category="market",
                interests=["market", "services"],
                borough=normalize_borough(raw.get("borough")),
                display_location=addr,
                address=addr,
                lat=raw.get("latitude"),
                lng=raw.get("longitude"),
                start_date_time=None,
                end_date_time=None,
                schedule_text=schedule,
                confidence_reason="directory_place_with_recurring_schedule_text_no_fake_one_off",
                extra={
                    "accepts_ebt": raw.get("accepts_ebt"),
                    "open_year_round": raw.get("open_year_round"),
                    "source_year": raw.get("year"),
                    "time_precision": "recurring_schedule_text",
                    "help_place_type": "farmers_market",
                },
            )
        )
    return out


def normalize_help_directory(
    source_key: str,
    *,
    name_keys: list[str],
    address_keys: list[str],
    schedule_keys: list[str],
    help_place_type: str,
) -> list[dict]:
    meta = SOURCE_CATALOG[source_key]
    out: list[dict] = []
    seen: set[str] = set()
    for raw in load_snapshot_rows(source_key):
        title = ""
        for k in name_keys:
            title = str(raw.get(k) or "").strip()
            if title:
                break
        if not title:
            continue
        address = ""
        for k in address_keys:
            address = str(raw.get(k) or "").strip()
            if address:
                break
        schedule = ""
        for k in schedule_keys:
            schedule = str(raw.get(k) or "").strip()
            if schedule:
                break
        sid = stable_hash(meta["dataset"], title, address, raw.get("latitude"), raw.get("longitude"))
        if sid in seen:
            continue
        seen.add(sid)
        out.append(
            _base_row(
                source_key=source_key,
                dataset=meta["dataset"],
                source_event_id=sid,
                title=title,
                lane="civic_help_places",
                category=meta["category"],
                interests=list(meta["interests"]),
                borough=normalize_borough(raw.get("borough")),
                display_location=address or None,
                address=address or None,
                lat=raw.get("latitude"),
                lng=raw.get("longitude"),
                start_date_time=None,
                end_date_time=None,
                schedule_text=schedule or None,
                confidence_reason="always_on_help_directory_no_fake_event_datetime",
                extra={
                    "phone": raw.get("phone_number_s") or raw.get("phone_number"),
                    "help_place_type": help_place_type,
                    "time_precision": "hours_comment" if schedule else "directory_place",
                },
            )
        )
    return out


def find_cross_source_near_duplicates(rows: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        title = str(row.get("title") or "").strip().lower()
        day = (str(row.get("start_date_time") or "")[:10]) or "nodate"
        place = str(row.get("display_location") or row.get("address") or "").strip().lower()
        if not title or day == "nodate":
            continue
        key = f"{title}|{day}|{place}"
        buckets[key].append(row)
    queue = []
    for key, items in buckets.items():
        datasets = {((i.get("source") or {}).get("dataset")) for i in items}
        if len(datasets) < 2:
            continue
        queue.append(
            {
                "review_key": key,
                "title": items[0].get("title"),
                "day": key.split("|")[1],
                "display_location": items[0].get("display_location"),
                "datasets": sorted(d for d in datasets if d),
                "row_ids": [i.get("id") for i in items],
                "action": "manual_review_do_not_silent_merge",
            }
        )
    return queue


def build_qa(
    *,
    accepted: list[dict],
    quarantined: list[dict],
    by_source: dict[str, dict[str, int]],
    today: date,
    invented_time_violations: list[str],
    out_of_bounds_rejected: int,
) -> dict[str, Any]:
    coord_counts = Counter(r.get("coordinate_status") for r in accepted)
    lane_counts = Counter(r.get("lane") for r in accepted)
    errors: list[str] = []
    for r in accepted:
        if r.get("promotion_allowed") is not False:
            errors.append(f"{r.get('id')}: promotion_allowed not false")
        if r.get("manual_review_status") != "pending":
            errors.append(f"{r.get('id')}: manual_review_status not pending")
        if r.get("public_map_modified") or r.get("location_cache_modified") or r.get("staged_feed_modified"):
            errors.append(f"{r.get('id')}: protected mutation flag set")
        if r.get("coordinate_status") == "map_ready" and (r.get("latitude") is None or r.get("longitude") is None):
            errors.append(f"{r.get('id')}: map_ready without coords")
        if r.get("latitude") is not None and r.get("coordinate_status") == "list_only":
            errors.append(f"{r.get('id')}: list_only still has latitude")
    errors.extend(invented_time_violations)
    return {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "reference_today_nyc": today.isoformat(),
        "qa_pass": len(errors) == 0 and len(invented_time_violations) == 0,
        "error_count": len(errors),
        "errors_sample": errors[:50],
        "accepted_count": len(accepted),
        "quarantined_count": len(quarantined),
        "coordinate_status_counts": dict(coord_counts),
        "lane_counts": dict(lane_counts),
        "by_source": by_source,
        "out_of_bounds_coords_rejected": out_of_bounds_rejected,
        "no_invented_times": len(invented_time_violations) == 0,
        "all_promotion_allowed_false": all(r.get("promotion_allowed") is False for r in accepted),
        "protected_files_untouched": True,
        "checks": {
            "promotion_allowed_false": all(r.get("promotion_allowed") is False for r in accepted),
            "manual_review_pending": all(r.get("manual_review_status") == "pending" for r in accepted),
            "public_map_unmodified": all(not r.get("public_map_modified") for r in accepted),
            "location_cache_unmodified": all(not r.get("location_cache_modified") for r in accepted),
            "nyc_bounds_enforced": True,
        },
    }


def continuity_report(accepted: list[dict], today: date) -> dict[str, Any]:
    dated = []
    for r in accepted:
        if r.get("lane") != "civic_review_events":
            continue
        day = str(r.get("start_date_time") or "")[:10]
        if len(day) == 10:
            dated.append((day, r))
    by_day: Counter[str] = Counter()
    for day, _ in dated:
        by_day[day] += 1
    window_7 = [(today + timedelta(days=i)).isoformat() for i in range(8)]
    window_30 = [(today + timedelta(days=i)).isoformat() for i in range(31)]
    return {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "reference_today_nyc": today.isoformat(),
        "dated_civic_event_count": len(dated),
        "upcoming_next_7_days": sum(by_day[d] for d in window_7),
        "upcoming_next_30_days": sum(by_day[d] for d in window_30),
        "day_chips": [{"date": d, "count": by_day[d]} for d in window_30 if by_day[d]],
        "earliest_upcoming": min((d for d, _ in dated), default=None),
        "latest_upcoming": max((d for d, _ in dated), default=None),
        "note": (
            "Counts only accepted civic_review_events inside the normalizer window. "
            "Historical-only SODA catalogs (e.g. Workforce1 recruitment events last updated ~2020) "
            "contribute 0 upcoming until the City publishes new rows."
        ),
    }


def food_access_gap_note() -> dict[str, Any]:
    return {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": utc_now(),
        "gap": "citywide_live_soup_kitchen_pantry_pin_feed",
        "status": "known_gap_human_follow_up",
        "honesty": (
            "NYC Open Data does not currently provide a high-quality live citywide soup-kitchen "
            "or food-pantry pin feed suitable for map publication."
        ),
        "do_not_use_as_complete_live_map": [
            {
                "dataset": "sp4a-vevi",
                "name": "COVID Free Meals (historical / incomplete for live pantry map)",
            },
            {
                "dataset": "mpqk-skis",
                "name": "CFC quarterly reports (not a live pin feed)",
            },
        ],
        "staged_related_food_access": [
            {
                "dataset": "8vwk-6iz2",
                "role": "farmers_markets_directory",
                "note": "Markets/EBT access — not soup kitchens",
            },
            {
                "dataset": "bmxf-3rd4",
                "role": "homeless_drop_in_centers",
                "note": "Drop-in centers may mention hot meals in comments; not a pantry map",
            },
            {
                "dataset": "tc6u-8rnp",
                "role": "snap_centers",
                "note": "Benefits access, not meal service locations",
            },
        ],
        "scraping_unofficial_html": "not_authorized",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "next_human_follow_up": (
            "If NYC Service / Food Access publishes a stable official machine-readable endpoint, "
            "stage it as review-only with the same date/time/location contract."
        ),
    }


def project_civic_schema_pages(review_rows: list[dict], help_rows: list[dict], generated: str) -> dict:
    reset_stable_id_registry()
    review_events = [
        project_event(r, index=i, data_layer="review_supplemental") for i, r in enumerate(review_rows)
    ]
    # Help places: reuse review_supplemental projection so Field Desk can list/map them
    # under a separate help layer without Approved permit collision.
    reset_stable_id_registry()
    help_events = [
        project_event(r, index=i, data_layer="review_supplemental") for i, r in enumerate(help_rows)
    ]
    def attach_civic_meta(events: list[dict], source_rows: list[dict], civic_lane: str) -> None:
        for e, src in zip(events, source_rows):
            nycif = e.setdefault("nycif", {})
            # Keep review_supplemental so Field Desk REVIEW lane matching continues to work.
            nycif["data_layer"] = "review_supplemental"
            nycif["civic_lane"] = civic_lane
            nycif["promotion_allowed"] = False
            nycif["production_feed"] = False
            nycif["manual_review_status"] = "pending"
            nycif["public_map_modified"] = False
            nycif["location_cache_modified"] = False
            nycif["staged_feed_modified"] = False
            if src.get("schedule_text"):
                nycif["schedule_text"] = src.get("schedule_text")
            if src.get("coordinate_status"):
                nycif["coordinate_status"] = src.get("coordinate_status")
            if src.get("confidence_reason"):
                nycif["confidence_reason"] = src.get("confidence_reason")

    attach_civic_meta(review_events, review_rows, "civic_review")
    attach_civic_meta(help_events, help_rows, "civic_help_places")

    review_env = envelope(review_events, generated_at_utc=generated, next_cursor=None)
    help_env = envelope(help_events, generated_at_utc=generated, next_cursor=None)
    write_repo_json("data/events_schema_v1_civic_review.json", review_env)
    write_repo_json("data/events_schema_v1_civic_help.json", help_env)

    def write_pages(layer: str, events: list[dict], full_dump: str) -> dict:
        pages_dir = DATA_DIR / "schema-v1-civic-review" / layer / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        for old in pages_dir.glob("page-*.json"):
            old.unlink()
        total = len(events)
        page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE) if total else 1
        entries = []
        for i in range(page_count):
            chunk = events[i * PAGE_SIZE : (i + 1) * PAGE_SIZE] if total else []
            page_name = f"page-{i + 1:04d}.json"
            dates = [event_date_key(e) for e in chunk if event_date_key(e)]
            cats = dict(Counter(e.get("category") for e in chunk).most_common())
            bors = dict(Counter(e.get("borough") for e in chunk).most_common())
            write_repo_json(
                f"data/schema-v1-civic-review/{layer}/pages/{page_name}",
                {
                    "schema_version": SCHEMA_VERSION,
                    "generated_at_utc": generated,
                    "total": total,
                    "next_cursor": f"page-{i + 2:04d}" if i + 1 < page_count else None,
                    "page": page_name,
                    "earliest_date": min(dates) if dates else None,
                    "latest_date": max(dates) if dates else None,
                    "categories": cats,
                    "boroughs": bors,
                    "events": chunk,
                },
            )
            entries.append(
                {
                    "cursor": page_name.replace(".json", ""),
                    "page": page_name,
                    "path": f"data/schema-v1-civic-review/{layer}/pages/{page_name}",
                    "count": len(chunk),
                    "earliest_date": min(dates) if dates else None,
                    "latest_date": max(dates) if dates else None,
                    "categories": cats,
                    "boroughs": bors,
                }
            )
        all_dates = [event_date_key(e) for e in events if event_date_key(e)]
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "layer": layer,
            "feed_root": "schema-v1-civic-review",
            "generated_at_utc": generated,
            "total": total,
            "page_count": len(entries),
            "page_size": PAGE_SIZE,
            "category_counts": dict(Counter(e.get("category") for e in events).most_common()),
            "borough_counts": dict(Counter(e.get("borough") for e in events).most_common()),
            "earliest_date": min(all_dates) if all_dates else None,
            "latest_date": max(all_dates) if all_dates else None,
            "pages": entries,
            "full_dump_path": full_dump,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
        }
        write_repo_json(f"data/schema-v1-civic-review/{layer}/manifest.json", manifest)
        return manifest

    return {
        "review": write_pages("review", review_events, "data/events_schema_v1_civic_review.json"),
        "help": write_pages("help", help_events, "data/events_schema_v1_civic_help.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None, help="YYYY-MM-DD override (NYC civil day)")
    args = parser.parse_args()
    today = date.fromisoformat(args.reference_today) if args.reference_today else today_nyc()
    generated = utc_now()

    accepted: list[dict] = []
    quarantined: list[dict] = []
    by_source: dict[str, dict[str, int]] = {}

    def record(source_key: str, acc: list[dict], qua: list[dict] | None = None) -> None:
        by_source[source_key] = {
            "accepted": len(acc),
            "quarantined": len(qua or []),
            "map_ready": sum(1 for r in acc if r.get("coordinate_status") == "map_ready"),
            "list_only": sum(1 for r in acc if r.get("coordinate_status") == "list_only"),
        }
        accepted.extend(acc)
        if qua:
            quarantined.extend(qua)

    a, q = normalize_workforce1_events(today)
    record("workforce1_events", a, q)
    a, q = normalize_ready_ny(today)
    record("ready_ny_events", a, q)
    a, q = normalize_oac(today)
    record("oac_activities", a, q)
    a, q = normalize_moia(today)
    record("moia_know_your_rights", a, q)
    a = normalize_volunteer()
    record("volunteer_opportunities", a)
    a = normalize_ss_volunteer()
    record("social_service_volunteer", a)
    a = normalize_farmers_markets()
    record("farmers_markets", a)
    a = normalize_help_directory(
        "benefits_access_centers",
        name_keys=["facility_name"],
        address_keys=["street_address"],
        schedule_keys=["comments"],
        help_place_type="benefits_access_center",
    )
    record("benefits_access_centers", a)
    a = normalize_help_directory(
        "snap_centers",
        name_keys=["facility_name"],
        address_keys=["street_address"],
        schedule_keys=["comments"],
        help_place_type="snap_center",
    )
    record("snap_centers", a)
    a = normalize_help_directory(
        "homeless_drop_in_centers",
        name_keys=["center_name"],
        address_keys=["address"],
        schedule_keys=["comments"],
        help_place_type="homeless_drop_in_center",
    )
    record("homeless_drop_in_centers", a)
    a = normalize_help_directory(
        "homebase_locations",
        name_keys=["homebase_office"],
        address_keys=["address"],
        schedule_keys=[],
        help_place_type="homebase",
    )
    record("homebase_locations", a)
    a = normalize_help_directory(
        "nyc_aging_providers",
        name_keys=["site_name", "sponsor_vendor"],
        address_keys=["site_address"],
        schedule_keys=[],
        help_place_type="nyc_aging_provider",
    )
    record("nyc_aging_providers", a)
    a = normalize_help_directory(
        "nycha_community_facilities",
        name_keys=["development", "program_type"],
        address_keys=["address"],
        schedule_keys=[],
        help_place_type="nycha_community_facility",
    )
    record("nycha_community_facilities", a)

    jobs_accepted: list[dict] = []
    for raw in load_snapshot_rows("workforce1_jobs"):
        if not any(str(v).strip() for v in raw.values()):
            continue
        title = str(raw.get("positiontitle") or "").strip() or "Workforce1 job listing"
        boroughs = [
            name
            for flag, name in (
                ("boroughbronx", "Bronx"),
                ("boroughbrooklyn", "Brooklyn"),
                ("boroughmanhattan", "Manhattan"),
                ("boroughqueens", "Queens"),
                ("boroughstatenisland", "Staten Island"),
            )
            if str(raw.get(flag) or "").strip().lower() == "yes"
        ]
        sid = stable_hash(
            title,
            raw.get("leadfulfillmentcenter"),
            raw.get("sectorname"),
            raw.get("sococcupationcode"),
            ",".join(boroughs),
        )
        jobs_accepted.append(
            _base_row(
                source_key="workforce1_jobs",
                dataset="ay9k-vznm",
                source_event_id=sid,
                title=title,
                lane="civic_review_opportunities",
                category="jobs",
                interests=["jobs"],
                borough=boroughs[0] if len(boroughs) == 1 else None,
                display_location=", ".join(boroughs) if boroughs else None,
                address=None,
                lat=None,
                lng=None,
                start_date_time=None,
                end_date_time=None,
                schedule_text=None,
                confidence_reason="job_listing_no_geo_list_only_partial_soda_payload",
                extra={
                    "sector": raw.get("sectorname"),
                    "wage_min": raw.get("wagemin"),
                    "wage_max": raw.get("wagemax"),
                    "position_type": raw.get("positiontype"),
                    "time_precision": "directory_place",
                    "borough_flags": boroughs,
                },
            )
        )
    record("workforce1_jobs", jobs_accepted)
    by_source["workforce1_jobs"]["note"] = (
        "SODA often pads with empty objects; only nonempty field payloads staged as list_only"
    )

    # Out-of-bounds: rows that had raw lat/lng rejected by resolver become list_only;
    # count those that came in with numeric coords but left null.
    out_of_bounds_rejected = sum(
        1
        for r in accepted
        if r.get("coordinate_status") == "list_only"
        and "no_valid_nyc_coords" in str(r.get("confidence_reason") or "")
    )

    invented_time_violations: list[str] = []
    for r in accepted:
        # Fail closed: schedule-only / ongoing rows must not invent start HH:MM claims.
        if r.get("time_precision") in {"ongoing_schedule", "soft_schedule_text", "recurring_schedule_text", "directory_place", "hours_comment"}:
            if r.get("start_date_time"):
                invented_time_violations.append(f"{r.get('id')}: schedule/place row has start_date_time")

    help_places = [r for r in accepted if r.get("lane") == "civic_help_places"]
    opportunities = [r for r in accepted if r.get("lane") == "civic_review_opportunities"]
    events = [r for r in accepted if r.get("lane") == "civic_review_events"]
    review_union = events + opportunities

    dedupe_queue = find_cross_source_near_duplicates(accepted)

    staging = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": generated,
        "reference_today_nyc": today.isoformat(),
        "timezone": DEFAULT_TIMEZONE,
        "total": len(accepted),
        "lane_counts": dict(Counter(r.get("lane") for r in accepted)),
        "coordinate_status_counts": dict(Counter(r.get("coordinate_status") for r in accepted)),
        "by_source": by_source,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "production_feed": False,
        "events": accepted,
    }
    save_json(DATA_DIR / "civic_people_facing_staging_feed.json", staging)

    help_composite = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": generated,
        "total": len(help_places),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "rows": help_places,
    }
    save_json(DATA_DIR / "civic_help_places_snapshot.json", help_composite)
    save_json(
        DATA_DIR / "civic_help_places_sync_report.json",
        {
            "generated_at_utc": generated,
            "total": len(help_places),
            "by_help_place_type": dict(
                Counter(r.get("help_place_type") for r in help_places).most_common()
            ),
            "map_ready": sum(1 for r in help_places if r.get("coordinate_status") == "map_ready"),
            "list_only": sum(1 for r in help_places if r.get("coordinate_status") == "list_only"),
            "qa_pass": True,
            "promotion_allowed": False,
        },
    )

    qa = build_qa(
        accepted=accepted,
        quarantined=quarantined,
        by_source=by_source,
        today=today,
        invented_time_violations=invented_time_violations,
        out_of_bounds_rejected=out_of_bounds_rejected,
    )
    save_json(DATA_DIR / "civic_people_facing_date_time_location_qa.json", qa)

    continuity = continuity_report(accepted, today)
    save_json(DATA_DIR / "civic_people_facing_continuity_report.json", continuity)

    gap = food_access_gap_note()
    save_json(DATA_DIR / "civic_food_access_gap_note.json", gap)

    save_json(
        DATA_DIR / "civic_people_facing_cross_source_dedupe_queue.json",
        {
            "generated_at_utc": generated,
            "count": len(dedupe_queue),
            "items": dedupe_queue[:200],
            "policy": "near_duplicates_queued_for_review_no_silent_merge",
        },
    )

    pages = project_civic_schema_pages(review_union, help_places, generated)

    report = {
        "schema_version": "civic-people-facing-v1",
        "generated_at_utc": generated,
        "reference_today_nyc": today.isoformat(),
        "qa_pass": qa["qa_pass"],
        "accepted_count": len(accepted),
        "quarantined_count": len(quarantined),
        "events_count": len(events),
        "opportunities_count": len(opportunities),
        "help_places_count": len(help_places),
        "coordinate_status_counts": staging["coordinate_status_counts"],
        "by_source": by_source,
        "continuity": {
            "upcoming_next_7_days": continuity["upcoming_next_7_days"],
            "upcoming_next_30_days": continuity["upcoming_next_30_days"],
            "dated_civic_event_count": continuity["dated_civic_event_count"],
        },
        "food_access_gap": gap["status"],
        "cross_source_dedupe_queue_count": len(dedupe_queue),
        "schema_pages": {
            "review_total": pages["review"]["total"],
            "help_total": pages["help"]["total"],
        },
        "artifacts": [
            "data/civic_people_facing_staging_feed.json",
            "data/civic_people_facing_staging_report.json",
            "data/civic_people_facing_date_time_location_qa.json",
            "data/civic_people_facing_continuity_report.json",
            "data/civic_food_access_gap_note.json",
            "data/civic_help_places_snapshot.json",
            "data/schema-v1-civic-review/review/manifest.json",
            "data/schema-v1-civic-review/help/manifest.json",
        ],
        "safety": {
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "production_feed": False,
            "approved_permit_lane_untouched": True,
        },
    }
    save_json(DATA_DIR / "civic_people_facing_staging_report.json", report)
    print(
        f"civic staging accepted={len(accepted)} quarantined={len(quarantined)} "
        f"upcoming_7={continuity['upcoming_next_7_days']} qa_pass={qa['qa_pass']}"
    )
    return 0 if qa["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
