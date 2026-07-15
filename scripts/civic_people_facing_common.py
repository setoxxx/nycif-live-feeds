#!/usr/bin/env python3
"""Shared helpers for NYCIF people-facing civic intake (staging / review only)."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

try:
    from scripts.schema_v1_common import DEFAULT_TIMEZONE, borough_label, valid_nyc_coords
except ModuleNotFoundError:  # pragma: no cover
    from schema_v1_common import DEFAULT_TIMEZONE, borough_label, valid_nyc_coords

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
NY_TZ = ZoneInfo(DEFAULT_TIMEZONE)
PAGE_LIMIT = 50000
MAX_ROWS = 300000
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "NYCIF-civic-people-facing/1.0 (+https://github.com/setoxxx/nycif-live-feeds)",
}

SODA_BASE = "https://data.cityofnewyork.us/resource"

SOURCE_CATALOG: dict[str, dict[str, Any]] = {
    "workforce1_events": {
        "dataset": "kf2b-aeh5",
        "lane": "civic_review_events",
        "category": "jobs",
        "interests": ["jobs"],
        "snapshot": "civic_workforce1_events_snapshot.json",
        "report": "civic_workforce1_events_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/kf2b-aeh5",
    },
    "ready_ny_events": {
        "dataset": "hyur-qpyf",
        "lane": "civic_review_events",
        "category": "civic",
        "interests": ["civic", "services"],
        "snapshot": "civic_ready_ny_events_snapshot.json",
        "report": "civic_ready_ny_events_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/hyur-qpyf",
    },
    "oac_activities": {
        "dataset": "fzy4-e84j",
        "lane": "civic_review_events",
        "category": "services",
        "interests": ["services", "family"],
        "snapshot": "civic_oac_activities_snapshot.json",
        "report": "civic_oac_activities_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/fzy4-e84j",
    },
    "moia_know_your_rights": {
        "dataset": "pnpe-ubtz",
        "lane": "civic_review_events",
        "category": "services",
        "interests": ["services", "civic"],
        "snapshot": "civic_moia_know_your_rights_snapshot.json",
        "report": "civic_moia_know_your_rights_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/pnpe-ubtz",
    },
    "volunteer_opportunities": {
        "dataset": "shpd-5q9m",
        "lane": "civic_review_opportunities",
        "category": "volunteer",
        "interests": ["volunteer"],
        "snapshot": "civic_volunteer_opportunities_snapshot.json",
        "report": "civic_volunteer_opportunities_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/shpd-5q9m",
    },
    "social_service_volunteer": {
        "dataset": "59c7-f2p9",
        "lane": "civic_review_opportunities",
        "category": "volunteer",
        "interests": ["volunteer", "services"],
        "snapshot": "civic_social_service_volunteer_snapshot.json",
        "report": "civic_social_service_volunteer_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/59c7-f2p9",
    },
    "workforce1_jobs": {
        "dataset": "ay9k-vznm",
        "lane": "civic_review_opportunities",
        "category": "jobs",
        "interests": ["jobs"],
        "snapshot": "civic_workforce1_jobs_snapshot.json",
        "report": "civic_workforce1_jobs_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/ay9k-vznm",
        "notes": "SODA resource currently returns empty objects; fields documented via metadata only.",
    },
    "farmers_markets": {
        "dataset": "8vwk-6iz2",
        "lane": "civic_help_places",
        "category": "market",
        "interests": ["market", "services"],
        "snapshot": "civic_farmers_markets_snapshot.json",
        "report": "civic_farmers_markets_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/8vwk-6iz2",
    },
    "benefits_access_centers": {
        "dataset": "9d9t-bmk7",
        "lane": "civic_help_places",
        "category": "services",
        "interests": ["services"],
        "snapshot": "civic_benefits_access_centers_snapshot.json",
        "report": "civic_benefits_access_centers_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/9d9t-bmk7",
    },
    "snap_centers": {
        "dataset": "tc6u-8rnp",
        "lane": "civic_help_places",
        "category": "services",
        "interests": ["services"],
        "snapshot": "civic_snap_centers_snapshot.json",
        "report": "civic_snap_centers_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/tc6u-8rnp",
    },
    "homeless_drop_in_centers": {
        "dataset": "bmxf-3rd4",
        "lane": "civic_help_places",
        "category": "services",
        "interests": ["services", "housing"],
        "snapshot": "civic_homeless_drop_in_centers_snapshot.json",
        "report": "civic_homeless_drop_in_centers_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/bmxf-3rd4",
    },
    "homebase_locations": {
        "dataset": "ntcm-2w4k",
        "lane": "civic_help_places",
        "category": "housing",
        "interests": ["housing", "services"],
        "snapshot": "civic_homebase_locations_snapshot.json",
        "report": "civic_homebase_locations_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/ntcm-2w4k",
    },
    "nyc_aging_providers": {
        "dataset": "u7wp-np5k",
        "lane": "civic_help_places",
        "category": "services",
        "interests": ["services", "family"],
        "snapshot": "civic_nyc_aging_providers_snapshot.json",
        "report": "civic_nyc_aging_providers_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/u7wp-np5k",
        "optional": True,
    },
    "nycha_community_facilities": {
        "dataset": "crns-fw6u",
        "lane": "civic_help_places",
        "category": "services",
        "interests": ["services", "family"],
        "snapshot": "civic_nycha_community_facilities_snapshot.json",
        "report": "civic_nycha_community_facilities_sync_report.json",
        "portal": "https://data.cityofnewyork.us/d/crns-fw6u",
        "optional": True,
    },
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# "Tuesday, March 17, 2020" or "March 17 2011"
HUMAN_DATE_RE = re.compile(
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+)?"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),?\s+(\d{4})",
    re.I,
)
ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
# 11:30 AM / 09:30 AM / 13:00:00
TIME_RE = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?$",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_nyc(reference: date | None = None) -> date:
    if reference is not None:
        return reference
    return datetime.now(NY_TZ).date()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_soda_rows(dataset: str, *, order: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params: dict[str, Any] = {"$limit": PAGE_LIMIT, "$offset": offset}
        if order:
            params["$order"] = order
        url = f"{SODA_BASE}/{dataset}.json?{urlencode(params)}"
        request = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError(f"SODA {dataset}: response was not a list")
        page = [row for row in payload if isinstance(row, dict)]
        rows.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        if offset >= MAX_ROWS:
            raise RuntimeError(f"SODA {dataset}: exceeded safety cap {MAX_ROWS}")
    return rows


def stable_hash(*parts: Any) -> str:
    joined = "|".join(str(p or "").strip() for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = ISO_DATE_RE.match(text)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    human = HUMAN_DATE_RE.search(text)
    if not human:
        return None
    month = MONTHS.get(human.group(1).lower())
    if not month:
        return None
    try:
        return date(int(human.group(3)), month, int(human.group(2)))
    except ValueError:
        return None


def parse_clock_time(value: Any) -> tuple[int, int, int] | None:
    """Parse a clock time. Returns None when absent — never invents HH:MM."""
    text = str(value or "").strip()
    if not text:
        return None
    match = TIME_RE.match(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)
    ampm = (match.group(4) or "").upper()
    if ampm:
        if hour == 12:
            hour = 0
        if ampm == "PM":
            hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return None
    return hour, minute, second


def combine_local_datetime(day: date | None, clock: tuple[int, int, int] | None) -> str | None:
    if day is None:
        return None
    if clock is None:
        # Date-only: keep midnight civil marker without inventing a user-facing HH:MM claim.
        return f"{day.isoformat()}T00:00:00"
    h, m, s = clock
    return f"{day.isoformat()}T{h:02d}:{m:02d}:{s:02d}"


def safety_fields() -> dict[str, Any]:
    return {
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "production_feed": False,
    }


def resolve_coordinate_status(
    lat: Any, lng: Any, *, proposed: bool = False
) -> tuple[float | None, float | None, str, str]:
    """Fail-closed: map_ready only after NYC pin certification (pin_integrity)."""
    try:
        from pin_integrity import certify_nyc_pin
    except ImportError:  # pragma: no cover - scripts path normally present
        lat_f, lng_f, ok = valid_nyc_coords(lat, lng)
        if ok and lat_f is not None and lng_f is not None:
            if proposed:
                return lat_f, lng_f, "proposed", "coords_proposed_nyc_bounds_not_native_map_ready"
            return lat_f, lng_f, "map_ready", "native_source_coords_inside_nyc_bounds"
        return None, None, "list_only", "no_valid_nyc_coords_list_only"

    lat_f, lng_f, ok, reason = certify_nyc_pin(lat, lng, allow_swap_correct=True)
    if ok and lat_f is not None and lng_f is not None:
        if proposed:
            return lat_f, lng_f, "proposed", f"coords_proposed_nyc_certified:{reason}"
        return lat_f, lng_f, "map_ready", f"native_source_coords_nyc_certified:{reason}"
    return None, None, "list_only", f"pin_integrity:{reason}"


def normalize_borough(value: Any) -> str | None:
    return borough_label(value)


def strip_html(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def date_window_status(day: date | None, *, today: date, max_future_days: int = 180) -> str | None:
    """Return quarantine reason or None if usable within window."""
    if day is None:
        return None
    if day < today:
        return "past_date_quarantine"
    if day > today + timedelta(days=max_future_days):
        return "far_future_outlier_quarantine"
    return None
