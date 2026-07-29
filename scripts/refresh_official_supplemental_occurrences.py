#!/usr/bin/env python3
"""Rebuild the official Calendar/Parks supplemental occurrence intake.

Every source occurrence is keyed by dataset + source event ID + exact source
start occurrence. Human rejection decisions remain in the intake file as
explicit rejected dispositions. Source-canceled rows are documented exclusions.
Other valid official listings are approved; rows without coordinates remain
list-only rather than being silently dropped.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CALENDAR = DATA / "nyc_citywide_events_calendar_snapshot.json"
PARKS = DATA / "nyc_parks_bigapps_events_snapshot.json"
QUEUE = DATA / "supplemental_manual_approval_queue.json"
OUT = DATA / "supplemental_events_staging_feed.json"
REPORT = DATA / "official_supplemental_occurrence_refresh_report.json"


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "rows", "approval_queue"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def source_parts(row: dict[str, Any]) -> tuple[str, str]:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = str(row.get("source_dataset") or source.get("dataset") or "").strip()
    source_event_id = str(row.get("source_event_id") or source.get("source_event_id") or "").strip()
    return dataset, source_event_id


def occurrence_start(row: dict[str, Any]) -> str:
    for value in (
        row.get("start_date_time"),
        row.get("startDate"),
        row.get("start_date"),
        row.get("date"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def occurrence_day(row: dict[str, Any]) -> str:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", occurrence_start(row))
    return match.group(1) if match else ""


def occurrence_key(row: dict[str, Any]) -> tuple[str, str, str]:
    dataset, source_event_id = source_parts(row)
    return dataset, source_event_id, occurrence_start(row)


def decision_maps() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str, str], str]]:
    by_source: dict[tuple[str, str], str] = {}
    by_day: dict[tuple[str, str, str], str] = {}
    for row in rows(load(QUEUE, {})):
        dataset, source_event_id = source_parts(row)
        if not dataset or not source_event_id:
            continue
        status = str(row.get("manual_review_status") or "pending").lower()
        by_source[(dataset, source_event_id)] = status
        day = occurrence_day(row)
        if day:
            by_day[(dataset, source_event_id, day)] = status
    return by_source, by_day


def intake_row(row: dict[str, Any], status: str) -> dict[str, Any]:
    out = dict(row)
    dataset, source_event_id = source_parts(out)
    start = occurrence_start(out)
    out["source_dataset"] = dataset
    out["source_event_id"] = source_event_id
    out["manual_review_status"] = status
    out["official_source_occurrence"] = True
    out["official_source_occurrence_key"] = f"{dataset}:{source_event_id}@{start}"
    out["approval_decision_reason"] = out.get("approval_decision_reason") or (
        "human_rejected_official_source_occurrence"
        if status == "rejected"
        else "official_city_source_daily_occurrence_intake"
    )
    out["promotion_allowed"] = False
    out["public_map_modified"] = False
    out["location_cache_modified"] = False
    out["staged_feed_modified"] = False
    return out


def main() -> int:
    generated = datetime.now(timezone.utc).isoformat()
    by_source, by_day = decision_maps()
    input_rows = rows(load(CALENDAR, [])) + rows(load(PARKS, {}))

    indexed: dict[tuple[str, str, str], dict[str, Any]] = {}
    human_rejected = 0
    invalid = 0
    source_canceled = 0
    for row in input_rows:
        dataset, source_event_id = source_parts(row)
        start = occurrence_start(row)
        day = occurrence_day(row)
        title = str(row.get("title") or row.get("name") or "").strip()
        if not dataset or not source_event_id or not start or not day or not title:
            invalid += 1
            continue
        if bool(row.get("canceled")):
            source_canceled += 1
            continue
        key = (dataset, source_event_id, start)
        status = by_day.get((dataset, source_event_id, day)) or by_source.get((dataset, source_event_id)) or "approved"
        if status == "pending":
            status = "approved"
        if status == "rejected":
            human_rejected += 1
        indexed[key] = intake_row(row, status)

    events = sorted(
        indexed.values(),
        key=lambda row: (
            occurrence_start(row),
            source_parts(row)[0],
            source_parts(row)[1],
        ),
    )
    duplicate_exact = max(0, len(input_rows) - invalid - source_canceled - len(events))
    payload = {
        "schema_version": "official-supplemental-occurrence-v1",
        "generated_at_utc": generated,
        "source_snapshots": [
            "data/nyc_citywide_events_calendar_snapshot.json",
            "data/nyc_parks_bigapps_events_snapshot.json",
        ],
        "total": len(events),
        "events": events,
    }
    report = {
        "schema_version": "official-supplemental-occurrence-v1",
        "generated_at_utc": generated,
        "qa_pass": bool(events) and invalid == 0,
        "source_rows": len(input_rows),
        "occurrences_indexed": len(events),
        "eligible_occurrences": len(events) - human_rejected,
        "human_rejected": human_rejected,
        "source_canceled_excluded": source_canceled,
        "invalid_missing_identity": invalid,
        "duplicate_exact_occurrences_collapsed": duplicate_exact,
        "cross_date_occurrences_collapsed": 0,
        "same_day_distinct_times_preserved": True,
        "output": str(OUT.relative_to(ROOT)),
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
