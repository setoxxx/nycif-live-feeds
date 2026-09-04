#!/usr/bin/env python3
"""Catch today's official city snapshots into staging event_occurrences.

GitHub is the daily factory. Discovery writes SODA/JSON snapshots into this
repo. This script then pushes those snapshots into Supabase event_occurrences,
which is what the iOS/Android app reads. Supabase does not poll GitHub JSON.

Uses the existing Rung 8 writer. Occurrence IDs come from OccurrenceIdentityV2
only. Every public TVPP street permit is pinned from Parks facilities, NYC DCP
LION centerlines, Geoclient, or NYC GeoSearch. Parks rows with official source
coordinates certify as map pins. Calendar rows stay list-only unless the
snapshot already has official coordinates. Projected feast stays list-only.
Expiration is never enabled.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import official_event_contract as contract
from scripts import supabase_event_writer as writer
from scripts.discovery_v02 import classification_blob, classify_record, infer_event_role
from scripts.tvpp_pin_resolver import TvppPinResolver

REPORT_FILENAME = "supabase_official_source_catchup_report.json"
BATCH_FILENAME = "supabase_official_event_batch.json"
TODAY_LISTING_FILENAME = "supabase_official_today_listing.json"
REPORTS_DIR = ROOT / "data" / "reports"
REPORT_PATH = REPORTS_DIR / REPORT_FILENAME
BATCH_PATH = REPORTS_DIR / BATCH_FILENAME
TODAY_LISTING_PATH = REPORTS_DIR / TODAY_LISTING_FILENAME
TVPP_PATH = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
PARKS_PATH = ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json"
CALENDAR_PATH = ROOT / "data" / "nyc_citywide_events_calendar_snapshot.json"
FEAST_PATH = ROOT / "data" / "staging" / "projected_feast_events_map_intake.json"
BATCH_SCHEMA = "nycif_apply_staging_event_batch.v1"
TODAY_LISTING_SCHEMA = "event_reader_rolling_v1.today_overlap.v1"
EXPECTED_PROJECT_REF = "oggwpvdirkrnzoolparx"
# Matches public.event_reader_rolling_v1: coalesce(end_at, start_at + 3 hours).
READER_END_PAD = timedelta(hours=3)

SOURCE_NAME = "nyc_open_data"
TIMEZONE = "America/New_York"
CLASSIFICATION_REASON = "rung8_official_snapshot_catchup"
CLASSIFIER_VERSION = "official-snapshot-catchup-v1"
# event_classifications.confidence is numeric; do not send "high"/"medium" labels.
CLASSIFICATION_CONFIDENCE = 0.95
DEFAULT_CHUNK_SIZE = 20
MAX_CHUNK_SIZE = 100
MIN_CHUNK_SIZE = 1
WRITE_RPC_TIMEOUT_SEC = 180

DATASET_TVPP = contract.DATASET_TVPP
DATASET_PARKS = contract.DATASET_PARKS
DATASET_CALENDAR = contract.DATASET_CALENDAR
DATASET_FEAST = contract.DATASET_FEAST
OFFICIAL_DATASETS = contract.OFFICIAL_DATASETS

NYC_LAT_RANGE = contract.NYC_LAT_RANGE
NYC_LNG_RANGE = contract.NYC_LNG_RANGE
NY_TZ = ZoneInfo(TIMEZONE)
MAX_SNAPSHOT_AGE = timedelta(hours=18)
FIVE_BOROUGHS = frozenset({"Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"})
BOROUGH_ALIASES = {
    "mn": "Manhattan",
    "manhattan": "Manhattan",
    "new york": "Manhattan",
    "bk": "Brooklyn",
    "brooklyn": "Brooklyn",
    "qn": "Queens",
    "q": "Queens",
    "queens": "Queens",
    "bx": "Bronx",
    "bronx": "Bronx",
    "the bronx": "Bronx",
    "si": "Staten Island",
    "staten island": "Staten Island",
}
TVPP_NON_PUBLIC_TYPES = {
    "shooting permit",
    "clean-up",
    "theater load in and load outs",
    "production event",
}
TVPP_NON_PUBLIC_NAME = re.compile(
    r"\bclosure\b|production parking|^maintenance$|shooting permit",
    re.IGNORECASE,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finite_coord(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _ny_timestamptz(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY_TZ)
    return parsed.isoformat()


def _parsed_ny(value: Any) -> datetime | None:
    text = _ny_timestamptz(value)
    if not text:
        return None
    return datetime.fromisoformat(text)


def _valid_interval(start_at: Any, end_at: Any) -> bool:
    start = _parsed_ny(start_at)
    if start is None:
        return False
    if end_at in (None, ""):
        return True
    end = _parsed_ny(end_at)
    if end is None:
        return False
    return end >= start


def _note_rejection(
    rejections: list[dict[str, Any]] | None,
    *,
    dataset: str,
    source_event_id: str,
    title: str,
    reason: str,
) -> None:
    if rejections is None:
        return
    rejections.append(
        {
            "source_dataset": dataset,
            "source_event_id": source_event_id,
            "title": title,
            "reason": reason,
        }
    )


def assert_official_snapshots_fresh() -> None:
    payload = _load_json(PARKS_PATH)
    generated = _text(payload.get("generated_at_utc") if isinstance(payload, dict) else "")
    if not generated:
        raise RuntimeError("Parks snapshot missing generated_at_utc; wait for Discovery Feed Refresh")
    generated_at = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - generated_at
    if age > MAX_SNAPSHOT_AGE:
        raise RuntimeError(
            f"official snapshots are {age} old; catch-up writes only after a successful Discovery run"
        )


def _write_report_json(filename: str, payload: dict[str, Any]) -> Path:
    reports_dir = REPORTS_DIR.resolve()
    path = (reports_dir / filename).resolve()
    if path.parent != reports_dir or path.name != filename:
        raise SystemExit(f"catch-up report path escaped data/reports: {filename}")
    reports_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_catchup_report(report: dict[str, Any]) -> None:
    _write_report_json(REPORT_FILENAME, report)


def today_nyc(now: datetime | None = None) -> str:
    current = now or datetime.now(NY_TZ)
    return current.astimezone(NY_TZ).date().isoformat()


def ny_day_bounds(today: str | None = None) -> tuple[datetime, datetime]:
    day = datetime.fromisoformat(today).date() if today else datetime.now(NY_TZ).date()
    start = datetime(day.year, day.month, day.day, tzinfo=NY_TZ)
    return start, start + timedelta(days=1)


def overlaps_today(start_at: Any, end_at: Any, today: str | None = None) -> bool:
    start = _parsed_ny(start_at)
    if start is None:
        return False
    day_start, day_end = ny_day_bounds(today)
    end = _parsed_ny(end_at) or (start + READER_END_PAD)
    return start < day_end and end >= day_start


def official_parks_pin(row: dict[str, Any]) -> tuple[float | None, float | None, bool]:
    return contract.apply_pin_policy(
        DATASET_PARKS,
        row.get("lat") if row.get("lat") is not None else row.get("latitude"),
        row.get("lng") if row.get("lng") is not None else row.get("longitude"),
        row.get("location_evidence"),
    )


def _category_from_text(text: str, default: str) -> tuple[str, str | None]:
    lower = text.lower()
    subtype = text or None
    if any(token in lower for token in ("hous", "hpd")):
        return "housing", subtype
    if any(token in lower for token in ("sport", "fitness", "athletic", "swim", "tennis", "basketball")):
        return "sports", subtype
    if any(token in lower for token in ("kid", "family", "holiday")):
        return "family", subtype
    if any(token in lower for token in ("art", "music", "film", "theater", "culture")):
        return "arts", subtype
    if any(token in lower for token in ("market", "farmers")):
        return "market", subtype
    if any(token in lower for token in ("park", "recreation", "garden")):
        return "parks", subtype
    return default, subtype


def _one_borough(value: Any) -> str | None:
    text = _text(value)
    if not text:
        return None
    return BOROUGH_ALIASES.get(text.casefold(), text)


def _borough(value: Any) -> str | None:
    if isinstance(value, list):
        labels: list[str] = []
        seen: set[str] = set()
        for item in value:
            label = _one_borough(item)
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
        if not labels:
            return None
        if set(labels) >= FIVE_BOROUGHS:
            return "Citywide"
        return ", ".join(labels)
    return _one_borough(value)


def _canonical(
    *,
    source_dataset: str,
    source_event_id: str,
    title: str,
    start_at: Any,
    end_at: Any,
    borough: Any,
    display_location: Any,
    lat: float | None,
    lng: float | None,
    map_ready: bool,
    public_category: str,
    public_subtype: str | None,
    source_event_type: Any,
    source_agency: Any,
    source_url: Any,
    source_cemsid: Any,
    seen_at: str,
    raw_record: dict[str, Any],
    location_authority: str,
    event_role: str = "public_event",
) -> dict[str, Any]:
    if not source_event_id or not title or not start_at:
        raise ValueError("official catch-up row is missing identity, title, or start")
    start_stamp = _ny_timestamptz(start_at)
    end_stamp = _ny_timestamptz(end_at)
    if not start_stamp:
        raise ValueError("official catch-up row is missing a parseable start time")
    display = _text(display_location) or "Location under review"
    payload = {
        "title": title,
        "start_at": start_stamp,
        "end_at": end_stamp,
        "timezone": TIMEZONE,
        "borough": _borough(borough),
        "display_location": display,
        "lat": lat,
        "lng": lng,
        "public_category": public_category,
        "public_subtype": public_subtype,
        "status": "active",
        "source_active": True,
        "map_ready": map_ready,
        "editorial_priority": "normal",
        "metadata": {
            "reader": {
                "event_role": event_role,
                "certified_pin": map_ready,
                "map_eligibility_state": "MAP_READY" if map_ready else "LIST_ONLY",
                "display_disposition": "MAP" if map_ready else "LIST_ONLY",
                "location_authority": location_authority,
                "source_dataset": source_dataset,
                "source_event_id": source_event_id,
                "public_url": source_url,
                "is_major": False,
                "photo_pick": False,
                "significance": "standard",
            }
        },
        "source": {
            "source_name": SOURCE_NAME,
            "source_dataset": source_dataset,
            "source_event_id": source_event_id,
            "source_cemsid": source_cemsid,
            "source_event_type": source_event_type,
            "source_agency": source_agency,
            "source_url": source_url,
            "source_first_seen": seen_at,
            "source_last_seen": seen_at,
            "source_active": True,
            "raw_record": raw_record,
        },
        "classification": {
            "public_category": public_category,
            "public_subtype": public_subtype,
            "classification_reason": CLASSIFICATION_REASON,
            "classifier_version": CLASSIFIER_VERSION,
            "confidence": CLASSIFICATION_CONFIDENCE,
            "source_event_type": source_event_type,
            "source_agency": source_agency,
        },
        "quality": {
            "quality_status": "VALID",
            "quality_flags": [],
            "public_display_status": "FULL_TIME" if map_ready else "LIST_ONLY",
            "details": {
                "catchup": True,
                "official_source": True,
                "certified_from_official_coordinate": map_ready,
            },
        },
    }
    return contract.apply_reader_display(payload)


def parks_events(
    path: Path = PARKS_PATH,
    rejections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("events", []) if isinstance(payload, dict) else payload
    seen_at = _text(payload.get("generated_at_utc") if isinstance(payload, dict) else "") or _now_iso()
    events: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            _note_rejection(rejections, dataset=DATASET_PARKS, source_event_id="", title="", reason="not_an_object")
            continue
        source_event_id = _text(row.get("source_event_id") or row.get("guid"))
        title = _text(row.get("title") or row.get("event_name"))
        start_at = row.get("start_date_time") or row.get("start_at")
        end_at = row.get("end_date_time") or row.get("end_at")
        if not source_event_id or not title or not start_at:
            _note_rejection(
                rejections,
                dataset=DATASET_PARKS,
                source_event_id=source_event_id,
                title=title,
                reason="missing_id_title_or_start",
            )
            continue
        if not _valid_interval(start_at, end_at):
            _note_rejection(
                rejections,
                dataset=DATASET_PARKS,
                source_event_id=source_event_id,
                title=title,
                reason="invalid_interval",
            )
            continue
        lat, lng, map_ready = official_parks_pin(row)
        categories = row.get("categories")
        category_text = (
            " | ".join(_text(item) for item in categories if _text(item))
            if isinstance(categories, list)
            else _text(categories)
        )
        public_category, public_subtype = _category_from_text(category_text, "parks")
        link = row.get("link")
        source_url = link.get("url") if isinstance(link, dict) else link
        events.append(
            _canonical(
                source_dataset=DATASET_PARKS,
                source_event_id=source_event_id,
                title=title,
                start_at=start_at,
                end_at=end_at,
                borough=row.get("borough") or row.get("event_borough"),
                display_location=row.get("display_location") or row.get("location"),
                lat=lat,
                lng=lng,
                map_ready=map_ready,
                public_category=public_category,
                public_subtype=public_subtype,
                source_event_type=category_text or "Parks",
                source_agency="Parks Department",
                source_url=source_url,
                source_cemsid=row.get("park_ids"),
                seen_at=seen_at,
                raw_record={
                    "source_dataset": DATASET_PARKS,
                    "source_authority_dataset": row.get("source_authority_dataset") or "w3wp-dpdi",
                    "source_event_id": source_event_id,
                    "title": title,
                    "start_date_time": start_at,
                    "end_date_time": row.get("end_date_time"),
                    "location": row.get("display_location") or row.get("location"),
                    "lat": lat,
                    "lng": lng,
                    "location_evidence": row.get("location_evidence"),
                },
                location_authority="nyc_parks_open_data_official_coordinate"
                if map_ready
                else "list_only_official_parks_snapshot",
            )
        )
    return events


def calendar_events(
    path: Path = CALENDAR_PATH,
    rejections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = payload if isinstance(payload, list) else payload.get("events", [])
    seen_at = _now_iso()
    events: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            _note_rejection(rejections, dataset=DATASET_CALENDAR, source_event_id="", title="", reason="not_an_object")
            continue
        if row.get("canceled") is True:
            _note_rejection(
                rejections,
                dataset=DATASET_CALENDAR,
                source_event_id=_text(row.get("source_event_id") or row.get("id")),
                title=_text(row.get("title") or row.get("name")),
                reason="canceled",
            )
            continue
        source_event_id = _text(row.get("source_event_id") or row.get("id"))
        title = _text(row.get("title") or row.get("name"))
        start_at = row.get("start_date_time") or row.get("startDate")
        end_at = row.get("end_date_time") or row.get("endDate")
        if not source_event_id or not title or not start_at:
            _note_rejection(
                rejections,
                dataset=DATASET_CALENDAR,
                source_event_id=source_event_id,
                title=title,
                reason="missing_id_title_or_start",
            )
            continue
        if not _valid_interval(start_at, end_at):
            _note_rejection(
                rejections,
                dataset=DATASET_CALENDAR,
                source_event_id=source_event_id,
                title=title,
                reason="invalid_interval",
            )
            continue
        lat, lng, map_ready = contract.apply_pin_policy(
            DATASET_CALENDAR,
            row.get("lat") if row.get("lat") is not None else row.get("latitude"),
            row.get("lng") if row.get("lng") is not None else row.get("longitude"),
        )
        categories = row.get("categories")
        category_text = (
            ", ".join(_text(item) for item in categories if _text(item))
            if isinstance(categories, list)
            else _text(categories)
        )
        public_category, public_subtype = _category_from_text(category_text, "general")
        events.append(
            _canonical(
                source_dataset=DATASET_CALENDAR,
                source_event_id=source_event_id,
                title=title,
                start_at=start_at,
                end_at=end_at,
                borough=row.get("boroughs") or row.get("borough"),
                display_location=row.get("address") or row.get("location"),
                lat=lat if map_ready else None,
                lng=lng if map_ready else None,
                map_ready=map_ready,
                public_category=public_category,
                public_subtype=public_subtype,
                source_event_type=category_text or "Citywide Calendar",
                source_agency=row.get("agency_name") or "NYC Gov",
                source_url=row.get("permalink") or row.get("website"),
                source_cemsid=None,
                seen_at=seen_at,
                raw_record={
                    "source_dataset": DATASET_CALENDAR,
                    "source_event_id": source_event_id,
                    "title": title,
                    "start_date_time": start_at,
                    "end_date_time": row.get("end_date_time"),
                    "address": row.get("address"),
                    "permalink": row.get("permalink"),
                    "canceled": False,
                },
                location_authority="official_calendar_coordinate"
                if map_ready
                else "list_only_official_calendar_snapshot",
            )
        )
    return events


def tvpp_events(
    path: Path = TVPP_PATH,
    rejections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = payload if isinstance(payload, list) else payload.get("events", [])
    seen_at = _now_iso()
    events: list[dict[str, Any]] = []
    resolver = TvppPinResolver.load_default()
    for row in rows:
        if not isinstance(row, dict):
            _note_rejection(rejections, dataset=DATASET_TVPP, source_event_id="", title="", reason="not_an_object")
            continue
        source_event_id = _text(row.get("source_event_id") or row.get("event_id"))
        title = _text(row.get("event_name") or row.get("title"))
        start_at = row.get("start_date_time") or row.get("start_at")
        end_at = row.get("end_date_time") or row.get("end_at")
        if not source_event_id or not title or not start_at:
            _note_rejection(
                rejections,
                dataset=DATASET_TVPP,
                source_event_id=source_event_id,
                title=title,
                reason="missing_id_title_or_start",
            )
            continue
        if not _valid_interval(start_at, end_at):
            _note_rejection(
                rejections,
                dataset=DATASET_TVPP,
                source_event_id=source_event_id,
                title=title,
                reason="invalid_interval",
            )
            continue
        event_type = _text(row.get("event_type"))
        classified = classify_record(row)
        role = classified.get("event_role") or infer_event_role(row, classification_blob(row))[0]
        if (
            role != "public_event"
            or event_type.casefold() in TVPP_NON_PUBLIC_TYPES
            or TVPP_NON_PUBLIC_NAME.search(title)
        ):
            _note_rejection(
                rejections,
                dataset=DATASET_TVPP,
                source_event_id=source_event_id,
                title=title,
                reason=f"not_public_event:{role}",
            )
            continue
        public_category = str(classified.get("category") or "general")
        _, public_subtype = _category_from_text(event_type or title, public_category)
        display_location = row.get("event_location") or row.get("location")
        borough = row.get("event_borough") or row.get("borough")
        pin = resolver.resolve(str(display_location or ""), str(borough or "") or None)
        lat, lng, map_ready = (pin.lat, pin.lng, True) if pin.resolved else (None, None, False)
        evidence = pin.evidence() if pin.resolved else None
        events.append(
            _canonical(
                source_dataset=DATASET_TVPP,
                source_event_id=source_event_id,
                title=title,
                start_at=start_at,
                end_at=end_at,
                borough=borough,
                display_location=display_location,
                lat=lat,
                lng=lng,
                map_ready=map_ready,
                public_category=public_category,
                public_subtype=public_subtype or event_type or None,
                source_event_type=event_type or "Street Activity Permit",
                source_agency=row.get("event_agency") or "Street Activity Permit Office",
                source_url=None,
                source_cemsid=row.get("source_cemsid"),
                seen_at=seen_at,
                raw_record={
                    "source_dataset": DATASET_TVPP,
                    "source_event_id": source_event_id,
                    "event_name": title,
                    "start_date_time": start_at,
                    "end_date_time": row.get("end_date_time"),
                    "event_location": row.get("event_location"),
                    "event_type": event_type,
                    "event_agency": row.get("event_agency"),
                    "street_closure_type": row.get("street_closure_type"),
                    "event_role": role,
                    "location_evidence": evidence,
                },
                location_authority=pin.source or "tvpp_pin_unresolved",
                event_role=role,
            )
        )
    if resolver.live_calls:
        resolver.save_cache()
    return events


def feast_events(
    path: Path = FEAST_PATH,
    rejections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    payload = _load_json(path)
    rows = payload.get("events", []) if isinstance(payload, dict) else payload
    seen_at = _now_iso()
    events: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            _note_rejection(rejections, dataset=DATASET_FEAST, source_event_id="", title="", reason="not_an_object")
            continue
        source_event_id = _text(row.get("source_event_id") or row.get("projected_feast_key"))
        title = _text(row.get("title") or row.get("event_name"))
        start_at = row.get("start_date_time") or row.get("start_at")
        end_at = row.get("end_date_time") or row.get("end_at")
        if not source_event_id or not title or not start_at:
            _note_rejection(
                rejections,
                dataset=DATASET_FEAST,
                source_event_id=source_event_id,
                title=title,
                reason="missing_id_title_or_start",
            )
            continue
        if not _valid_interval(start_at, end_at):
            _note_rejection(
                rejections,
                dataset=DATASET_FEAST,
                source_event_id=source_event_id,
                title=title,
                reason="invalid_interval",
            )
            continue
        public_category, public_subtype = _category_from_text(
            _text(row.get("event_type") or row.get("projected_event_kind")),
            "arts",
        )
        events.append(
            _canonical(
                source_dataset=DATASET_FEAST,
                source_event_id=source_event_id,
                title=title,
                start_at=start_at,
                end_at=end_at,
                borough=row.get("event_borough") or row.get("borough"),
                display_location=row.get("display_location") or row.get("location"),
                lat=None,
                lng=None,
                map_ready=False,
                public_category=public_category,
                public_subtype=public_subtype,
                source_event_type=row.get("event_type") or "Projected feast",
                source_agency="NYCIF projected feast reference",
                source_url=None,
                source_cemsid=None,
                seen_at=seen_at,
                raw_record={
                    "source_dataset": DATASET_FEAST,
                    "source_event_id": source_event_id,
                    "title": title,
                    "start_date_time": start_at,
                    "end_date_time": end_at,
                    "location": row.get("display_location") or row.get("location"),
                    "intake_type": row.get("intake_type"),
                    "promotion_allowed": False,
                },
                location_authority="list_only_projected_feast_reference",
            )
        )
    return events


def events_for_dataset(
    dataset: str,
    rejections: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if dataset == DATASET_PARKS:
        return parks_events(rejections=rejections)
    if dataset == DATASET_CALENDAR:
        return calendar_events(rejections=rejections)
    if dataset == DATASET_TVPP:
        return tvpp_events(rejections=rejections)
    if dataset == DATASET_FEAST:
        return feast_events(rejections=rejections)
    raise ValueError(f"unsupported official dataset: {dataset}")


def normalize_dataset(dataset: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rejections: list[dict[str, Any]] = []
    normalized = [writer.normalize_event(event) for event in events_for_dataset(dataset, rejections)]
    unique = contract.assert_official_batch(normalized, dataset)
    return unique, rejections


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "rows": len(rows),
        "map_ready": sum(1 for row in rows if row.get("map_ready") is True),
        "list_only": sum(1 for row in rows if row.get("map_ready") is not True),
        "with_coords": sum(1 for row in rows if row.get("lat") is not None and row.get("lng") is not None),
    }


def reader_listing_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    reader = metadata.get("reader") if isinstance(metadata.get("reader"), dict) else {}
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    map_ready = row.get("map_ready") is True
    return {
        "occurrence_id": row.get("occurrence_id"),
        "title": row.get("title"),
        "start_at": row.get("start_at"),
        "end_at": row.get("end_at"),
        "timezone": row.get("timezone") or TIMEZONE,
        "borough": row.get("borough"),
        "display_location": row.get("display_location"),
        "lat": row.get("lat") if map_ready else None,
        "lng": row.get("lng") if map_ready else None,
        "public_category": row.get("public_category"),
        "public_subtype": row.get("public_subtype"),
        "map_ready": map_ready,
        "editorial_priority": row.get("editorial_priority") or "normal",
        "event_role": reader.get("event_role") or "public_event",
        "certified_pin": bool(reader.get("certified_pin")) if reader.get("certified_pin") is not None else map_ready,
        "map_eligibility_state": reader.get("map_eligibility_state")
        or ("MAP_READY" if map_ready else "LIST_ONLY"),
        "location_authority": reader.get("location_authority"),
        "display_disposition": reader.get("display_disposition") or ("MAP" if map_ready else "LIST_ONLY"),
        "is_major": bool(reader.get("is_major", False)),
        "photo_pick": bool(reader.get("photo_pick", False)),
        "significance": reader.get("significance") or "standard",
        "source_dataset": reader.get("source_dataset") or source.get("source_dataset"),
        "source_event_id": reader.get("source_event_id") or source.get("source_event_id"),
        "public_url": reader.get("public_url") or source.get("source_url"),
    }


def today_listing_events(
    rows: list[dict[str, Any]],
    today: str | None = None,
) -> list[dict[str, Any]]:
    day = today or today_nyc()
    listing = [
        reader_listing_row(row)
        for row in rows
        if overlaps_today(row.get("start_at"), row.get("end_at"), day)
    ]
    listing.sort(key=lambda item: (str(item.get("start_at") or ""), str(item.get("title") or "")))
    return listing


def build_today_listing_payload(
    rows_by_dataset: dict[str, list[dict[str, Any]]],
    today: str | None = None,
) -> dict[str, Any]:
    day = today or today_nyc()
    day_start, day_end = ny_day_bounds(day)
    events: list[dict[str, Any]] = []
    by_dataset: dict[str, dict[str, int]] = {}
    for dataset, rows in rows_by_dataset.items():
        listing = today_listing_events(rows, day)
        by_dataset[dataset] = summarize(listing)
        events.extend(listing)
    events.sort(key=lambda item: (str(item.get("start_at") or ""), str(item.get("title") or "")))
    return {
        "schema": TODAY_LISTING_SCHEMA,
        "generated_at_utc": _now_iso(),
        "today_nyc": day,
        "timezone": TIMEZONE,
        "reader_view": "event_reader_rolling_v1",
        "window": {
            "start": day_start.isoformat(),
            "end": day_end.isoformat(),
            "rule": "start_at < day_end AND coalesce(end_at, start_at + 3 hours) >= day_start",
        },
        **summarize(events),
        "by_dataset": by_dataset,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "promotion_allowed": False,
        "events": events,
    }


def build_official_batch_payload(
    rows_by_dataset: dict[str, list[dict[str, Any]]],
    today: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": BATCH_SCHEMA,
        "generated_at_utc": _now_iso(),
        "today_nyc": today or today_nyc(),
        "p_source_name": SOURCE_NAME,
        "p_allow_expire": False,
        "p_simulate_failure": False,
        "p_expected_project_ref": EXPECTED_PROJECT_REF,
        "datasets": {dataset: {"p_events": rows} for dataset, rows in rows_by_dataset.items()},
    }


def export_official_payloads(
    rows_by_dataset: dict[str, list[dict[str, Any]]],
    today: str | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    day = today or today_nyc()
    batch = build_official_batch_payload(rows_by_dataset, day)
    listing = build_today_listing_payload(rows_by_dataset, day)
    batch_path = _write_report_json(BATCH_FILENAME, batch)
    listing_path = _write_report_json(TODAY_LISTING_FILENAME, listing)
    return batch_path, listing_path, listing


def load_official_batch(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise RuntimeError("official event batch must be a JSON object")
    if payload.get("schema") != BATCH_SCHEMA:
        raise RuntimeError(f"official event batch schema must be {BATCH_SCHEMA}")
    if payload.get("p_source_name") != SOURCE_NAME:
        raise RuntimeError("official event batch source_name mismatch")
    if payload.get("p_allow_expire") is not False:
        raise RuntimeError("official event batch must never expire")
    if payload.get("p_expected_project_ref") != EXPECTED_PROJECT_REF:
        raise RuntimeError("official event batch project ref mismatch")
    datasets = payload.get("datasets")
    if not isinstance(datasets, dict) or not datasets:
        raise RuntimeError("official event batch is missing datasets")
    for name, block in datasets.items():
        events = block.get("p_events") if isinstance(block, dict) else None
        if not isinstance(events, list) or not events:
            raise RuntimeError(f"official event batch {name} has no p_events")
        for event in events:
            if not isinstance(event, dict) or not event.get("occurrence_id"):
                raise RuntimeError(f"official event batch {name} has a row without occurrence_id")
    return payload


def _statement_timeout(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "57014" in text or "statement timeout" in text


def write_chunks(
    rows: list[dict[str, Any]],
    chunk_size: int,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if chunk_size < MIN_CHUNK_SIZE or chunk_size > MAX_CHUNK_SIZE:
        raise ValueError(f"chunk size must be between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE}")
    project_ref, target_url = writer.validate_write_target()
    service_key = __import__("os").environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_key:
        raise writer.WriteGuardError("SUPABASE_SERVICE_ROLE_KEY is required in the environment")
    actions = {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 0, "EXPIRE": 0}
    run_ids: list[int] = []
    chunk_count = (len(rows) + chunk_size - 1) // chunk_size
    committed = 0

    def record_success(result: dict[str, Any]) -> None:
        nonlocal committed
        if result.get("newsroom_queue_delta") not in (0, None):
            raise RuntimeError("official catch-up mutated newsroom_queue")
        chunk_actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
        for key in actions:
            actions[key] += int(chunk_actions.get(key, 0) or 0)
        if isinstance(result.get("pipeline_run_id"), int):
            run_ids.append(result["pipeline_run_id"])
        committed += 1
        if progress is not None:
            progress["database_write_performed"] = True
            progress["chunks_committed"] = committed
            progress["pipeline_run_ids"] = list(run_ids)
            progress["actions"] = dict(actions)
            _write_catchup_report(progress)

    def post_chunk(chunk: list[dict[str, Any]]) -> None:
        payload = {
            "p_events": chunk,
            "p_source_name": SOURCE_NAME,
            "p_allow_expire": False,
            "p_simulate_failure": False,
            "p_expected_project_ref": project_ref,
        }
        try:
            result = writer.post_atomic_batch(
                target_url,
                service_key,
                payload,
                timeout=WRITE_RPC_TIMEOUT_SEC,
            )
        except writer.SupabaseRPCError as exc:
            if len(chunk) > 1 and _statement_timeout(exc):
                mid = max(1, len(chunk) // 2)
                post_chunk(chunk[:mid])
                post_chunk(chunk[mid:])
                return
            raise
        record_success(result)

    try:
        for index in range(0, len(rows), chunk_size):
            post_chunk(rows[index : index + chunk_size])
    except Exception as exc:
        if progress is not None:
            progress["database_write_performed"] = committed > 0
            progress["write_error"] = str(exc)
            progress["chunks_committed"] = committed
            progress["pipeline_run_ids"] = list(run_ids)
            progress["actions"] = dict(actions)
            _write_catchup_report(progress)
        raise
    return {
        "actions": actions,
        "pipeline_run_ids": run_ids,
        "chunk_count": chunk_count,
        "chunks_committed": committed,
    }


def write_official_batch(
    batch: dict[str, Any],
    chunk_size: int,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if batch.get("p_allow_expire") is not False:
        raise RuntimeError("official event batch must never expire")
    dataset_results: dict[str, Any] = {}
    for dataset, block in (batch.get("datasets") or {}).items():
        rows = list(block.get("p_events") or [])
        dataset_results[dataset] = {
            "dataset": dataset,
            **summarize(rows),
            **write_chunks(rows, chunk_size, progress=progress),
        }
    return dataset_results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=(*OFFICIAL_DATASETS, "all"), default="all")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--from-batch", type=Path)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    args = parser.parse_args()
    if args.from_batch and not args.write:
        raise SystemExit("--from-batch is only valid with --write")
    if args.write:
        assert_official_snapshots_fresh()
    datasets = list(OFFICIAL_DATASETS) if args.dataset == "all" else [args.dataset]
    report: dict[str, Any] = {
        "run_type": "official_source_catchup_write" if args.write else "official_source_catchup_plan",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_name": SOURCE_NAME,
        "expire_enabled": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
        "batch_schema": BATCH_SCHEMA,
        "today_listing_schema": TODAY_LISTING_SCHEMA,
        "datasets": {},
        "database_write_performed": False,
    }
    rows_by_dataset: dict[str, list[dict[str, Any]]] = {}
    rejections_by_dataset: dict[str, list[dict[str, Any]]] = {}
    if args.from_batch:
        batch = load_official_batch(args.from_batch)
        missing = [name for name in datasets if name not in (batch.get("datasets") or {})]
        if missing:
            raise RuntimeError(f"official event batch is missing {', '.join(missing)}")
        for dataset in datasets:
            rows_by_dataset[dataset] = list(batch["datasets"][dataset]["p_events"])
            report["datasets"][dataset] = {
                "dataset": dataset,
                **summarize(rows_by_dataset[dataset]),
            }
    else:
        for dataset in datasets:
            rows, rejections = normalize_dataset(dataset)
            reasons = Counter(item.get("reason") or "unspecified" for item in rejections)
            rows_by_dataset[dataset] = rows
            rejections_by_dataset[dataset] = rejections
            report["datasets"][dataset] = {
                "dataset": dataset,
                **summarize(rows),
                "rejected_rows": len(rejections),
                "rejection_reason_counts": dict(reasons),
                "rejection_samples": rejections[:20],
                "occurrence_ids": [row["occurrence_id"] for row in rows],
            }
        from scripts import official_daily_machine as machine

        machine_report = machine.build_and_persist(
            rows_by_dataset=rows_by_dataset,
            rejections_by_dataset=rejections_by_dataset,
        )
        report["daily_machine"] = machine.summary_for_catchup(machine_report)
        if machine_report.get("qa_pass") is not True:
            _write_catchup_report(report)
            raise SystemExit(
                "official daily machine failed; pin coverage or silent-drop gate blocked catch-up"
            )
    batch_path, listing_path, listing = export_official_payloads(rows_by_dataset)
    report["today"] = {
        "today_nyc": listing["today_nyc"],
        "window": listing["window"],
        "rows": listing["rows"],
        "map_ready": listing["map_ready"],
        "list_only": listing["list_only"],
        "by_dataset": listing["by_dataset"],
        "listing_file": TODAY_LISTING_FILENAME,
        "batch_file": BATCH_FILENAME,
    }
    report["payload_paths"] = {
        "batch": str(batch_path),
        "today_listing": str(listing_path),
    }
    _write_catchup_report(report)
    if args.write:
        written = write_official_batch(
            load_official_batch(batch_path),
            args.chunk_size,
            progress=report,
        )
        for dataset, result in written.items():
            report["datasets"].setdefault(dataset, {}).update(result)
        report["database_write_performed"] = True
        _write_catchup_report(report)
    printable = json.loads(json.dumps(report))
    for block in printable.get("datasets", {}).values():
        block.pop("occurrence_ids", None)
    print(json.dumps(printable, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
