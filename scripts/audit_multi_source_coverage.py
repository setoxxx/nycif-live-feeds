#!/usr/bin/env python3
"""Compare NYC permit Open Data vs Citywide Events Calendar (staging QA only).

Outputs a report artifact describing overlap and gaps between:
- tvpp-9vvx (NYC Permitted Event Information / CECM Open Data / CSV family)
- nyc-citywide-events-calendar-api (nyc.gov/main/events / api.nyc.gov/calendar/*)

Does NOT publish, promote, or modify protected feeds.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_identity import normalize_text_legacy

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_PATH = DATA_DIR / "reports" / "multi_source_coverage_report.json"

PERMIT_SNAPSHOT = DATA_DIR / "raw_nyc_open_data_snapshot.json"
CALENDAR_SNAPSHOT = DATA_DIR / "nyc_citywide_events_calendar_snapshot.json"
ROW_DISPOSITION = DATA_DIR / "row_disposition_report.json"
STAGED_MANIFEST = DATA_DIR / "staged_live_manifest.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def date_key(value: Any) -> str:
    text = str(value or "")
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", text) else ""


def title_key(value: Any) -> str:
    return normalize_text_legacy(str(value or ""))


def permit_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def calendar_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def build_permit_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = "|".join(
            [
                title_key(row.get("event_name")),
                date_key(row.get("start_date_time")),
            ]
        )
        if not key.replace("|", ""):
            continue
        index.setdefault(key, []).append(row)
    return index


def build_calendar_index(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = "|".join(
            [
                title_key(row.get("title")),
                date_key(row.get("start_date_time")),
            ]
        )
        if not key.replace("|", ""):
            continue
        index.setdefault(key, []).append(row)
    return index


def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 3)


def sample_rows(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    samples = []
    for row in rows[:limit]:
        samples.append(
            {
                "title": row.get("title") or row.get("event_name"),
                "start_date_time": row.get("start_date_time"),
                "source_dataset": row.get("source_dataset"),
                "source_event_id": row.get("source_event_id"),
                "categories": row.get("categories") or row.get("event_type"),
                "borough": row.get("borough") or row.get("event_borough") or row.get("boroughs"),
            }
        )
    return samples


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    permits = permit_rows(load_json(PERMIT_SNAPSHOT, []))
    calendar = calendar_rows(load_json(CALENDAR_SNAPSHOT, []))
    disposition = load_json(ROW_DISPOSITION, {})
    staged_manifest = load_json(STAGED_MANIFEST, {})

    current_future_permits = [
        row for row in permits if date_key(row.get("start_date_time")) >= today
    ]
    current_future_calendar = [
        row for row in calendar if date_key(row.get("start_date_time")) >= today
    ]

    permit_index = build_permit_index(current_future_permits)
    calendar_index = build_calendar_index(current_future_calendar)

    permit_keys = set(permit_index)
    calendar_keys = set(calendar_index)
    overlap_keys = permit_keys & calendar_keys
    permit_only_keys = permit_keys - calendar_keys
    calendar_only_keys = calendar_keys - permit_keys

    calendar_category_counter = Counter()
    for row in current_future_calendar:
        for category in row.get("categories") or []:
            calendar_category_counter[str(category)] += 1

    permit_agency_counter = Counter()
    for row in current_future_permits:
        permit_agency_counter[str(row.get("event_agency") or "Unknown")] += 1

    staged_events = int(staged_manifest.get("staged_feed_events") or 0)
    gps_review = int(disposition.get("disposition_counts", {}).get("gps_review_queue") or 0)
    staged_valid = int(disposition.get("disposition_counts", {}).get("staged_with_valid_gps") or 0)
    classified = int(disposition.get("classified_rows") or len(current_future_permits))

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "qa_pass": bool(permits),
        "sources_compared": {
            "permit_open_data": {
                "dataset_id": "tvpp-9vvx",
                "snapshot_path": repo_relative(PERMIT_SNAPSHOT),
                "human_sources": [
                    "NYC Open Data CSV/JSON export",
                    "CECM permitted-event registry (same dataset family as E-Apply)",
                ],
                "current_future_rows": len(current_future_permits),
            },
            "citywide_calendar_api": {
                "dataset_id": "nyc-citywide-events-calendar-api",
                "snapshot_path": repo_relative(CALENDAR_SNAPSHOT),
                "human_sources": [
                    "https://www.nyc.gov/main/events",
                    "https://api.nyc.gov/calendar/*",
                ],
                "current_future_rows": len(current_future_calendar),
                "snapshot_present": bool(calendar),
            },
        },
        "overlap_analysis": {
            "title_date_overlap_rows": sum(len(calendar_index[k]) for k in overlap_keys),
            "title_date_overlap_unique_keys": len(overlap_keys),
            "permit_only_unique_keys": len(permit_only_keys),
            "calendar_only_unique_keys": len(calendar_only_keys),
            "permit_overlap_pct_of_permits": pct(len(overlap_keys), len(permit_keys)),
            "calendar_overlap_pct_of_calendar": pct(len(overlap_keys), len(calendar_keys)),
        },
        "pipeline_status": {
            "permit_ingestion_accounted_rows": classified,
            "staged_with_valid_gps": staged_valid,
            "gps_review_queue": gps_review,
            "staged_feed_events": staged_events,
            "auto_gps_match_pct": pct(staged_valid, classified),
            "gps_review_tail_pct": pct(gps_review, classified),
        },
        "coverage_assessment": {
            "permit_pipeline_ingestion_pct_estimate": 100.0 if classified else 0.0,
            "permit_pipeline_map_ready_pct_estimate": pct(staged_valid, classified),
            "multi_source_city_events_pct_estimate": pct(
                len(overlap_keys) + len(permit_only_keys) + len(calendar_only_keys),
                len(permit_keys | calendar_keys),
            )
            if (permit_keys or calendar_keys)
            else 0.0,
            "citywide_calendar_ingested_in_repo": bool(calendar),
            "notes": [
                "tvpp-9vvx is the authoritative permit registry export; E-Apply is the same CECM family via a different UI/API.",
                "Citywide calendar is a separate curated multi-agency feed; overlap with permits is partial, not 1:1.",
                "Full 'all city events' requires merging supplemental calendar-only rows through manual review, not auto-promotion.",
            ],
        },
        "distribution": {
            "calendar_category_counts": dict(calendar_category_counter.most_common()),
            "permit_agency_counts": dict(permit_agency_counter.most_common(10)),
        },
        "samples": {
            "calendar_only": sample_rows(
                [calendar_index[k][0] for k in sorted(calendar_only_keys)[:10]]
            ),
            "permit_only": sample_rows(
                [permit_index[k][0] for k in sorted(permit_only_keys)[:10]]
            ),
            "overlap": sample_rows(
                [permit_index[k][0] for k in sorted(overlap_keys)[:10]]
            ),
        },
        "safety": {
            "production_feeds_modified": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
        },
    }

    if not calendar:
        report["qa_pass"] = False
        report["warnings"] = [
            "Citywide calendar snapshot missing. Run scripts/sync_nyc_citywide_events_calendar.py first."
        ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
