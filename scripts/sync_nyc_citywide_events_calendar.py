#!/usr/bin/env python3
"""Fetch NYC Citywide Events Calendar API snapshot (staging only).

This script does NOT modify protected feeds or publish to the public map.
It writes an active-listing snapshot plus a sync report for multi-source
coverage QA. Source-canceled listings are explicitly counted and excluded.

Source: https://api.nyc.gov/calendar/* (same API as nyc.gov/main/events)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "nyc_citywide_events_calendar_snapshot.json"
REPORT_PATH = DATA_DIR / "nyc_citywide_events_calendar_sync_report.json"

API_GATEWAY = os.environ.get("NYC_EVENT_CAL_API_GATEWAY", "https://api.nyc.gov/")
API_KEY_ENV = "NYC_EVENT_CAL_API_KEY"
PUBLIC_KEY_URL = "https://www.nyc.gov/bin/nyc/sc.ec.json"
PUBLIC_KEY_FALLBACK_URLS = (
    "https://web.archive.org/web/20240601000000/https://www.nyc.gov/bin/nyc/sc.ec.json",
    "https://web.archive.org/web/2024/https://www.nyc.gov/bin/nyc/sc.ec.json",
)
SEARCH_PATH = "calendar/search"
CATEGORIES_PATH = "calendar/categories"
DEFAULT_WINDOW_DAYS = int(os.environ.get("NYC_EVENT_CAL_WINDOW_DAYS", "183"))
PAGE_SIZE = 12


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def fetch_public_key(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "NYCIF-live-feed-QA/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    key = str(payload.get("API_KEY_EVENT_CAL") or "").strip()
    if not key:
        raise RuntimeError(f"Public key endpoint did not return API_KEY_EVENT_CAL: {url}")
    return key


def resolve_api_key() -> tuple[str, str]:
    env_key = os.environ.get(API_KEY_ENV, "").strip()
    if env_key:
        return env_key, "environment"
    errors: list[str] = []
    for url in (PUBLIC_KEY_URL, *PUBLIC_KEY_FALLBACK_URLS):
        try:
            return fetch_public_key(url), f"public_config:{url}"
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError(
        f"Could not resolve Event Calendar API key. Set {API_KEY_ENV} or ensure a public "
        f"config URL is reachable. Attempts: {'; '.join(errors)}"
    )


def api_get(path: str, params: dict[str, str], api_key: str) -> Any:
    gateway = API_GATEWAY if API_GATEWAY.endswith("/") else f"{API_GATEWAY}/"
    query = urlencode(params)
    url = f"{gateway}{path}?{query}" if query else f"{gateway}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Ocp-Apim-Subscription-Key": api_key,
            "User-Agent": "NYCIF-live-feed-QA/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, (dict, list)):
        raise RuntimeError(f"Unexpected response type from {url}")
    return payload


def mmddyyyy(value: date) -> str:
    return value.strftime("%m/%d/%Y")


def bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def normalize_calendar_item(item: dict[str, Any]) -> dict[str, Any]:
    boroughs = item.get("boroughs")
    if isinstance(boroughs, list):
        borough_list = [str(b).strip() for b in boroughs if str(b).strip()]
    else:
        borough_list = [str(boroughs).strip()] if boroughs else []
    categories = item.get("categories")
    if isinstance(categories, list):
        category_list = [str(c).strip() for c in categories if str(c).strip()]
    else:
        category_list = [str(categories).strip()] if categories else []
    return {
        "source_dataset": "nyc-citywide-events-calendar-api",
        "source_event_id": str(item.get("id") or "").strip(),
        "source_guid": str(item.get("guid") or "").strip(),
        "source_sequence": item.get("sequence"),
        "title": item.get("name"),
        "start_date_time": item.get("startDate"),
        "end_date_time": item.get("endDate"),
        "date_part": item.get("datePart"),
        "time_part": item.get("timePart"),
        "all_day": item.get("allDay"),
        "canceled": bool_flag(item.get("canceled")),
        "permalink": item.get("permalink"),
        "description_html": item.get("desc"),
        "short_description": item.get("shortDesc"),
        "website": item.get("website"),
        "contact_name": item.get("contactName"),
        "address_type": item.get("addressType"),
        "address": item.get("address"),
        "boroughs": borough_list,
        "categories": category_list,
        "agency_name": item.get("agencyName"),
        "agency_acronym": item.get("agencyAcronym"),
        "map_type": item.get("mapType"),
        "city_pick": item.get("cityPick"),
        "image_url": item.get("imageUrl"),
        "manual_review_status": "pending",
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def fetch_search_window(api_key: str, start: date, end: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    params = {
        "startDate": mmddyyyy(start),
        "endDate": mmddyyyy(end),
        "pageNumber": "1",
    }
    first = api_get(SEARCH_PATH, params, api_key)
    items = [row for row in first.get("items", []) if isinstance(row, dict)]
    pagination = first.get("pagination") if isinstance(first.get("pagination"), dict) else {}
    num_pages = int(pagination.get("numPages") or 1)
    total_items = int(pagination.get("totalItems") or len(items))

    for page_number in range(2, num_pages + 1):
        params["pageNumber"] = str(page_number)
        page = api_get(SEARCH_PATH, params, api_key)
        page_items = [row for row in page.get("items", []) if isinstance(row, dict)]
        items.extend(page_items)

    meta = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "num_pages_fetched": num_pages,
        "reported_total_items": total_items,
        "items_returned": len(items),
    }
    return items, meta


def main() -> int:
    today = datetime.now(timezone.utc).date()
    end = today + timedelta(days=DEFAULT_WINDOW_DAYS)
    try:
        api_key, key_source = resolve_api_key()
        categories_payload = api_get(CATEGORIES_PATH, {}, api_key)
        categories = categories_payload if isinstance(categories_payload, list) else categories_payload.get("items", [])
        raw_items, window_meta = fetch_search_window(api_key, today, end)
    except urllib.error.HTTPError as exc:
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "qa_pass": False,
            "error": f"HTTP {exc.code}: {exc.reason}",
            "production_feeds_modified": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        }
        save_json(REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    except Exception as exc:
        report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "qa_pass": False,
            "error": str(exc),
            "production_feeds_modified": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        }
        save_json(REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1

    normalized_all = [normalize_calendar_item(item) for item in raw_items]
    canceled_rows = [row for row in normalized_all if row.get("canceled")]
    normalized = [row for row in normalized_all if not row.get("canceled")]

    deduped: dict[str, dict[str, Any]] = {}
    for row in normalized:
        dedupe_key = "|".join(
            [
                row.get("source_event_id") or "",
                str(row.get("source_sequence") or ""),
                row.get("start_date_time") or "",
            ]
        )
        deduped[dedupe_key] = row
    rows = list(deduped.values())

    category_counts: dict[str, int] = {}
    borough_counts: dict[str, int] = {}
    for row in rows:
        for category in row.get("categories") or []:
            category_counts[category] = category_counts.get(category, 0) + 1
        for borough in row.get("boroughs") or ["Unknown"]:
            borough_counts[borough] = borough_counts.get(borough, 0) + 1

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "qa_pass": bool(rows),
        "fetch_mode": "live",
        "api_gateway": API_GATEWAY,
        "api_key_source": key_source,
        "search_path": SEARCH_PATH,
        "window_days": DEFAULT_WINDOW_DAYS,
        "window": window_meta,
        "categories_available": categories,
        "source_rows_received": len(normalized_all),
        "canceled_excluded": len(canceled_rows),
        "duplicate_exact_occurrences_collapsed": len(normalized) - len(rows),
        "snapshot_rows": len(rows),
        "category_counts": dict(sorted(category_counts.items())),
        "borough_counts": dict(sorted(borough_counts.items())),
        "production_feeds_modified": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
    }

    save_json(SNAPSHOT_PATH, rows)
    save_json(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
