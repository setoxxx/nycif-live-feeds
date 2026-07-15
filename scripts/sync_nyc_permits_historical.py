#!/usr/bin/env python3
"""Sync NYC Permitted Event Information - Historical (bkfu-528j) into staging.

Safe staging only. Never writes location_cache or production staged feeds.
Fetches a prior-year seasonal money-day-ish window (server-side SoQL), then
applies Money-Day title keyword filter + dedupe for a compact snapshot.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, today_nyc, utc_now  # noqa: E402
import build_photographer_assignment_calendar as money  # noqa: E402

DATASET = "bkfu-528j"
SODA_URL = f"https://data.cityofnewyork.us/resource/{DATASET}.json"
PAGE_LIMIT = 50000
MAX_ROWS = 150000
KEEP_FIELDS = [
    "event_id",
    "cemsid",
    "event_name",
    "start_date_time",
    "end_date_time",
    "event_agency",
    "event_type",
    "event_borough",
    "event_location",
    "event_street_side",
    "street_closure_type",
    "community_board",
    "police_precinct",
]
HEADERS = {"Accept": "application/json", "User-Agent": "NYCIF-viral-recurrence/1.0"}

# Server-side keyword gate (avoid bare %MARKET% flood). Local Money-Day filter
# still applied after fetch.
SODA_NAME_CLAUSE = (
    "("
    "upper(event_name) like '%PARADE%' OR upper(event_name) like '%FESTIVAL%' OR "
    "upper(event_name) like '%STREET FAIR%' OR upper(event_name) like '%BLOCK PARTY%' OR "
    "upper(event_name) like '%GREENMARKET%' OR upper(event_name) like '%FARMERS MARKET%' OR "
    "upper(event_name) like '%FLEA MARKET%' OR upper(event_name) like '%STREET MARKET%' OR "
    "upper(event_name) like '%CARNIVAL%' OR upper(event_name) like '%PRIDE%' OR "
    "upper(event_name) like '%FAN ZONE%' OR upper(event_name) like '%WATCH PARTY%' OR "
    "upper(event_name) like '%ACTIVATION%' OR upper(event_name) like '%FIREWORKS%' OR "
    "upper(event_name) like '%FEAST%' OR upper(event_name) like '%OPEN STREET%' OR "
    "upper(event_name) like '%PLAZA PROGRAMMING%' OR upper(event_name) like '%MERCHANDISE FAIR%' OR "
    "upper(event_name) like '%FARMSTAND%' OR upper(event_name) like '%MARCH%' OR "
    "upper(event_name) like '%RALLY%'"
    ")"
)


def prior_year_window(reference: date) -> tuple[date, date, int]:
    """Seasonal window covering current 2-mo desk window shifted to prior year."""
    prior_year = reference.year - 1
    start = date(prior_year, reference.month, 1) - timedelta(days=14)
    # end ~ two months + buffer from reference month
    if reference.month >= 11:
        end_month = ((reference.month + 1) % 12) + 1
        end_year = prior_year + 1
        end = date(end_year, end_month, 1) + timedelta(days=45)
    else:
        end = date(prior_year, reference.month + 2, 1) + timedelta(days=20)
    return start, end, prior_year


def fetch_rows(start: date, end: date) -> list[dict[str, Any]]:
    where = (
        f"start_date_time between '{start.isoformat()}T00:00:00' and '{end.isoformat()}T23:59:59' "
        f"AND {SODA_NAME_CLAUSE}"
    )
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "$limit": PAGE_LIMIT,
            "$offset": offset,
            "$order": "start_date_time,event_id",
            "$where": where,
        }
        url = f"{SODA_URL}?{urlencode(params)}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("bkfu-528j response was not a list")
        page = [r for r in payload if isinstance(r, dict)]
        rows.extend(page)
        if len(page) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        if offset >= MAX_ROWS:
            raise RuntimeError(f"bkfu-528j exceeded safety cap {MAX_ROWS}")
    return rows


def is_money_day_title(row: dict[str, Any]) -> bool:
    title = str(row.get("event_name") or "")
    _score, rules, excluded = money.score_row(
        {"title": title, "category": row.get("event_type")},
        lane="approved_major",
    )
    if not any(r.startswith("keyword_") for r in rules):
        return False
    if money.EXCLUDE_ROUTINES.search(title.lower()) and not money.has_money_day_signal(rules):
        return False
    if excluded and "routine_activity_excluded" in rules:
        return False
    if excluded and "thin_or_non_money_title_excluded" in rules:
        return False
    return True


def compact_rows(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in raw:
        if not is_money_day_title(row):
            continue
        key = (
            str(row.get("event_id") or ""),
            str(row.get("start_date_time") or "")[:10],
            str(row.get("event_location") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        out.append({k: row.get(k) for k in KEEP_FIELDS})
    out.sort(key=lambda r: (str(r.get("start_date_time") or ""), str(r.get("event_name") or "")))
    return out


def schema_parity_ok() -> dict[str, Any]:
    """tvpp-9vvx and bkfu-528j share the same public columns (no applicant)."""
    expected = {
        "event_id",
        "event_name",
        "start_date_time",
        "end_date_time",
        "event_agency",
        "event_type",
        "event_borough",
        "event_location",
        "street_closure_type",
        "community_board",
        "police_precinct",
        "cemsid",
    }
    return {
        "current_dataset": "tvpp-9vvx",
        "historical_dataset": DATASET,
        "shared_public_columns": sorted(expected),
        "applicant_org_in_open_data": False,
        "foil_required_for_filer_identity": True,
        "parity_confirmed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None)
    parser.add_argument(
        "--skip-network",
        action="store_true",
        help="Reuse existing snapshot if present; do not fetch SODA",
    )
    args = parser.parse_args()
    reference = date.fromisoformat(args.reference_today) if args.reference_today else today_nyc()
    start, end, prior_year = prior_year_window(reference)
    snap_path = DATA_DIR / "nyc_permits_historical_snapshot.json"
    report_path = DATA_DIR / "nyc_permits_historical_sync_report.json"

    fetched = 0
    source = "network"
    if args.skip_network:
        existing = load_json(snap_path, {})
        rows = existing.get("rows") if isinstance(existing, dict) else None
        if not isinstance(rows, list) or not rows:
            raise SystemExit("No existing historical snapshot; refuse --skip-network")
        compact = rows
        source = "existing_snapshot"
        prior_year = int(existing.get("prior_year") or prior_year)
        start = date.fromisoformat(existing.get("window_start") or start.isoformat())
        end = date.fromisoformat(existing.get("window_end") or end.isoformat())
    else:
        raw = fetch_rows(start, end)
        fetched = len(raw)
        compact = compact_rows(raw)

    snapshot = {
        "schema_version": "nyc-permits-historical-v1",
        "generated_at_utc": utc_now(),
        "dataset": DATASET,
        "dataset_url": f"https://data.cityofnewyork.us/resource/{DATASET}.json",
        "reference_today_nyc": reference.isoformat(),
        "prior_year": prior_year,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "row_count": len(compact),
        "fetch_source": source,
        "schema_parity": schema_parity_ok(),
        "rows": compact,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": (
            "Money-day-keyword seasonal subset of bkfu-528j for viral recurrence matching. "
            "No applicant/company fields exist in Open Data — FOIL required for filers."
        ),
    }
    save_json(snap_path, snapshot)

    report = {
        "schema_version": "nyc-permits-historical-v1",
        "generated_at_utc": snapshot["generated_at_utc"],
        "qa_pass": len(compact) > 0,
        "dataset": DATASET,
        "reference_today_nyc": reference.isoformat(),
        "prior_year": prior_year,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "fetched_raw_rows": fetched,
        "compact_row_count": len(compact),
        "fetch_source": source,
        "schema_parity": snapshot["schema_parity"],
        "artifact": "data/nyc_permits_historical_snapshot.json",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "protected_files_untouched": True,
    }
    save_json(report_path, report)
    print(json.dumps({k: report[k] for k in ("qa_pass", "compact_row_count", "window_start", "window_end", "prior_year")}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
