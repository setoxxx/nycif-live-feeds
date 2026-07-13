#!/usr/bin/env python3
"""Audit NYCIF feed files for duplicate/date anomalies before production promotion.

Outputs:
- data/feed_anomaly_report.json

This is report-only. It does not modify production feeds.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT = DATA_DIR / "feed_anomaly_report.json"

FILES = {
    "major": ROOT / "nycif_major_radar_map_events.json",
    "full": ROOT / "nycif_all_radar_map_events.json",
    "test_enriched": DATA_DIR / "nycif_live_test_enriched_events.json",
    "staged": DATA_DIR / "nycif_staged_live_events.json",
}


def load_json(path: Path) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def title(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("name") or row.get("event_name") or "").strip()


def location(row: dict[str, Any]) -> str:
    return str(row.get("display_location") or row.get("location") or row.get("address") or "").strip()


def borough(row: dict[str, Any]) -> str:
    return str(row.get("borough") or row.get("event_borough") or "").strip()


def event_type(row: dict[str, Any]) -> str:
    return str(row.get("event_type") or row.get("type") or row.get("street_closure_type") or "").strip()


def source_id(row: dict[str, Any]) -> str:
    for key in ("source_event_id", "event_id", "permit_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    raw_id = str(row.get("id") or "").strip()
    if raw_id.startswith("nyc_open_data:tvpp-9vvx:"):
        return raw_id.rsplit(":", 1)[-1]
    return ""


def date_key(row: dict[str, Any]) -> str:
    for key in ("start_date_time", "start", "date"):
        raw = str(row.get(key) or "")
        match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
        if match:
            return match.group(0)
    return ""


def end_date_key(row: dict[str, Any]) -> str:
    raw = str(row.get("end_date_time") or row.get("end") or "")
    match = re.match(r"^\d{4}-\d{2}-\d{2}", raw)
    return match.group(0) if match else ""


def latlng(row: dict[str, Any]) -> str:
    try:
        return f"{float(row.get('lat')):.5f},{float(row.get('lng')):.5f}"
    except Exception:
        return ""


def one_day_street_like(row: dict[str, Any]) -> bool:
    text = normalize_text_legacy(" ".join([title(row), location(row), event_type(row), str(row.get("major_reason") or ""), str(row.get("source_file") or "")]))
    return bool(re.search(r"block party|street event|street activity|street fair|permit", text))


def sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": title(row),
        "date": date_key(row),
        "end_date": end_date_key(row),
        "borough": borough(row),
        "location": location(row),
        "event_type": event_type(row),
        "source_event_id": source_id(row),
        "latlng": latlng(row),
    }


def add_issue(issues: list[dict[str, Any]], kind: str, severity: str, feed: str, key: str, rows: list[dict[str, Any]], note: str) -> None:
    issues.append({
        "kind": kind,
        "severity": severity,
        "feed": feed,
        "key": key,
        "count": len(rows),
        "dates": sorted({date_key(row) for row in rows if date_key(row)}),
        "note": note,
        "samples": [sample(row) for row in rows[:8]],
    })


def audit_feed(feed_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_content: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_exact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    date_mismatch: list[dict[str, Any]] = []
    long_one_day_street_like: list[dict[str, Any]] = []

    for row in rows:
        sid = source_id(row)
        if sid:
            by_source[sid].append(row)
        content_key = "|".join([normalize_text_legacy(title(row)), normalize_text_legacy(borough(row)), normalize_text_legacy(location(row)), latlng(row)])
        if content_key.strip("|"):
            by_content[content_key].append(row)
        exact_key = "|".join([sid, content_key, date_key(row)])
        by_exact[exact_key].append(row)
        if row.get("date") and row.get("start_date_time"):
            if str(row.get("date"))[:10] != str(row.get("start_date_time"))[:10]:
                date_mismatch.append(row)
        if one_day_street_like(row) and date_key(row) and end_date_key(row) and date_key(row) != end_date_key(row):
            long_one_day_street_like.append(row)

    for key, group in by_source.items():
        dates = {date_key(row) for row in group if date_key(row)}
        if len(dates) > 1:
            add_issue(issues, "same_source_event_id_multiple_dates", "high", feed_name, key, group, "Same source event ID appears on more than one date.")

    for key, group in by_content.items():
        if len(group) < 2:
            continue
        dates = {date_key(row) for row in group if date_key(row)}
        if len(dates) > 1 and any(one_day_street_like(row) for row in group):
            add_issue(issues, "same_street_event_content_multiple_dates", "high", feed_name, key, group, "Same title/location/coordinate street-style event appears on more than one date.")

    for key, group in by_exact.items():
        if len(group) > 1:
            add_issue(issues, "exact_duplicate_rows", "medium", feed_name, key, group, "Same source/content/date appears more than once.")

    if date_mismatch:
        add_issue(issues, "date_field_start_date_mismatch", "medium", feed_name, "date_vs_start_date_time", date_mismatch, "date field does not match start_date_time date.")

    if long_one_day_street_like:
        add_issue(issues, "one_day_street_event_crosses_dates", "medium", feed_name, "start_end_cross_date", long_one_day_street_like, "Block-party/street-style event has start and end on different dates.")

    high = sum(1 for issue in issues if issue["severity"] == "high")
    medium = sum(1 for issue in issues if issue["severity"] == "medium")
    return {
        "feed": feed_name,
        "rows_loaded": len(rows),
        "issues_total": len(issues),
        "high_issues": high,
        "medium_issues": medium,
        "issues": sorted(issues, key=lambda item: (item["severity"] != "high", item["kind"], item["key"]))[:100],
    }


def main() -> int:
    reports = []
    for name, path in FILES.items():
        payload = load_json(path)
        rows = rows_from_payload(payload)
        reports.append(audit_feed(name, rows))

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_feeds_modified": False,
        "checks": [
            "same_source_event_id_multiple_dates",
            "same_street_event_content_multiple_dates",
            "exact_duplicate_rows",
            "date_field_start_date_mismatch",
            "one_day_street_event_crosses_dates",
        ],
        "feeds": reports,
        "summary": {
            "feeds_checked": len(reports),
            "rows_checked": sum(report["rows_loaded"] for report in reports),
            "issues_total": sum(report["issues_total"] for report in reports),
            "high_issues": sum(report["high_issues"] for report in reports),
            "medium_issues": sum(report["medium_issues"] for report in reports),
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
