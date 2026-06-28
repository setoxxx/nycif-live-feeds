#!/usr/bin/env python3
"""Audit remainder-of-year event coverage for NYCIF live map feeds.

Outputs:
- data/remainder_year_coverage_report.json

The goal is to catch bottlenecks between:
1. raw NYC Open Data rows
2. test/enriched feed rows
3. staged public map rows

This report is intentionally diagnostic. It does not change production feeds.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_SNAPSHOT_PATH = DATA_DIR / "raw_nyc_open_data_snapshot.json"
TEST_FEED_PATH = DATA_DIR / "nycif_live_test_enriched_events.json"
STAGED_FEED_PATH = DATA_DIR / "nycif_staged_live_events.json"
REPORT_PATH = DATA_DIR / "remainder_year_coverage_report.json"
TODAY = datetime.now(timezone.utc).date()
YEAR_END = date(TODAY.year, 12, 31)


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def date_key(value: Any) -> str:
    text = str(value or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else ""


def raw_date(row: dict[str, Any]) -> str:
    return date_key(row.get("start_date_time") or row.get("date"))


def feed_date(row: dict[str, Any]) -> str:
    return date_key(row.get("date") or row.get("start_date_time") or row.get("start"))


def in_window(key: str) -> bool:
    if not key:
        return False
    try:
        d = date.fromisoformat(key)
    except ValueError:
        return False
    return TODAY <= d <= YEAR_END


def date_range() -> list[str]:
    days: list[str] = []
    cursor = TODAY
    while cursor <= YEAR_END:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return days


def count_by_date(rows: list[dict[str, Any]], getter) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        key = getter(row)
        if in_window(key):
            counts[key] += 1
    return counts


def pct(part: int, whole: int) -> float | None:
    if whole <= 0:
        return None
    return round((part / whole) * 100, 2)


def main() -> int:
    raw_rows = rows_from_payload(load_json_file(RAW_SNAPSHOT_PATH, []))
    test_rows = rows_from_payload(load_json_file(TEST_FEED_PATH, {}))
    staged_rows = rows_from_payload(load_json_file(STAGED_FEED_PATH, {}))

    raw_counts = count_by_date(raw_rows, raw_date)
    test_counts = count_by_date(test_rows, feed_date)
    staged_counts = count_by_date(staged_rows, feed_date)

    daily = []
    for key in date_range():
        raw = raw_counts.get(key, 0)
        test = test_counts.get(key, 0)
        staged = staged_counts.get(key, 0)
        daily.append({
            "date": key,
            "raw_rows": raw,
            "test_feed_rows": test,
            "staged_rows": staged,
            "test_vs_raw_pct": pct(test, raw),
            "staged_vs_raw_pct": pct(staged, raw),
            "staged_vs_test_pct": pct(staged, test),
            "has_raw": raw > 0,
            "has_staged": staged > 0,
        })

    missing_raw_days = [row["date"] for row in daily if row["raw_rows"] == 0]
    raw_with_zero_staged = [row for row in daily if row["raw_rows"] > 0 and row["staged_rows"] == 0]
    low_staged_days = [row for row in daily if row["raw_rows"] >= 10 and row["staged_vs_raw_pct"] is not None and row["staged_vs_raw_pct"] < 60]

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start": TODAY.isoformat(),
        "window_end": YEAR_END.isoformat(),
        "days_in_window": len(daily),
        "totals": {
            "raw_rows": sum(raw_counts.values()),
            "test_feed_rows": sum(test_counts.values()),
            "staged_rows": sum(staged_counts.values()),
            "test_vs_raw_pct": pct(sum(test_counts.values()), sum(raw_counts.values())),
            "staged_vs_raw_pct": pct(sum(staged_counts.values()), sum(raw_counts.values())),
            "staged_vs_test_pct": pct(sum(staged_counts.values()), sum(test_counts.values())),
        },
        "days_with_raw_events": sum(1 for row in daily if row["raw_rows"] > 0),
        "days_with_staged_events": sum(1 for row in daily if row["staged_rows"] > 0),
        "missing_raw_days_sample": missing_raw_days[:20],
        "raw_days_with_zero_staged_sample": raw_with_zero_staged[:20],
        "low_staged_coverage_days_sample": low_staged_days[:20],
        "july_4": next((row for row in daily if row["date"] == f"{TODAY.year}-07-04"), None),
        "daily_counts": daily,
    }

    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
