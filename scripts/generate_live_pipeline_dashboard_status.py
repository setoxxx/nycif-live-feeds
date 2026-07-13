#!/usr/bin/env python3
"""Build public-safe live pipeline dashboard status for NYCIF admin UIs.

Reads existing QA/report artifacts only. Does not modify protected feeds.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = DATA / "reports"
STATUS_PATH = ROOT / "status" / "nycif-live-pipeline-dashboard.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(100.0 * numerator / denominator, 3)


def main() -> int:
    disposition = load_json(DATA / "row_disposition_report.json", {})
    staged_manifest = load_json(DATA / "staged_live_manifest.json", {})
    live_sync = load_json(DATA / "live_sync_report.json", {})
    live_delta = load_json(DATA / "live_delta_report.json", {})
    coverage = load_json(REPORTS / "multi_source_coverage_report.json", {})
    coverage_roadmap = load_json(ROOT / "status" / "nycif-coverage-roadmap.json", {})
    calendar_sync = load_json(DATA / "nyc_citywide_events_calendar_sync_report.json", {})
    backend_gate = load_json(DATA / "backend_reliability_gate_report.json", {})

    staged_valid = int(disposition.get("disposition_counts", {}).get("staged_with_valid_gps") or 0)
    gps_review = int(disposition.get("disposition_counts", {}).get("gps_review_queue") or 0)
    classified = int(disposition.get("classified_rows") or 0)
    staged_events = int(staged_manifest.get("staged_feed_events") or 0)

    overlap = coverage.get("overlap_analysis") or {}
    pipeline = coverage.get("pipeline_status") or {}

    payload = {
        "artifact_type": "nycif_live_pipeline_dashboard",
        "schema_version": "1.0.0",
        "project": "nycif-live-feeds",
        "repository": "setoxxx/nycif-live-feeds",
        "visibility": "public",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "admin_dashboard_live_visibility",
        "headline": "Live pipeline snapshot for NYCIF admin dashboards (read-only).",
        "current_counts": {
            "staged_feed_events": staged_events or int(pipeline.get("staged_feed_events") or 0),
            "staged_with_valid_gps": staged_valid or int(pipeline.get("staged_with_valid_gps") or 0),
            "gps_review_queue": gps_review or int(pipeline.get("gps_review_queue") or 0),
            "classified_permit_rows": classified or int(pipeline.get("permit_ingestion_accounted_rows") or 0),
            "raw_rows_loaded": int(live_sync.get("raw_rows_loaded") or 0),
            "current_future_raw_rows": int(live_sync.get("current_future_rows") or 0),
            "citywide_calendar_rows": int(calendar_sync.get("snapshot_rows") or 0),
            "newly_added_events": int(live_delta.get("added_count") or 0),
            "removed_events": int(live_delta.get("removed_count") or 0),
            "changed_events": int(live_delta.get("changed_count") or 0),
            "net_change": int(live_delta.get("net_change") or 0),
        },
        "progress_bars": {
            "permit_ingestion_pct": pct(classified, classified) if classified else 0.0,
            "auto_gps_match_pct": pct(staged_valid, classified) if classified else float(pipeline.get("auto_gps_match_pct") or 0),
            "gps_review_tail_pct": pct(gps_review, classified) if classified else float(pipeline.get("gps_review_tail_pct") or 0),
            "multi_source_coverage_pct": float(
                (coverage.get("coverage_assessment") or {}).get("multi_source_city_events_pct_estimate")
                or (coverage_roadmap.get("progress_bars") or {}).get("multi_source_city_events", {}).get("percent")
                or 0
            ),
            "backend_gate_pass": bool(backend_gate.get("gate_pass")),
        },
        "multi_source": {
            "permit_dataset_id": "tvpp-9vvx",
            "citywide_calendar_dataset_id": "nyc-citywide-events-calendar-api",
            "title_date_overlap_unique_keys": int(overlap.get("title_date_overlap_unique_keys") or 0),
            "permit_only_unique_keys": int(overlap.get("permit_only_unique_keys") or 0),
            "calendar_only_unique_keys": int(overlap.get("calendar_only_unique_keys") or 0),
            "calendar_sync_qa_pass": bool(calendar_sync.get("qa_pass")),
        },
        "freshness": {
            "live_sync_generated_at_utc": live_sync.get("generated_at_utc"),
            "staged_manifest_generated_at_utc": staged_manifest.get("generated_at_utc"),
            "live_delta_generated_at_utc": live_delta.get("generated_at_utc"),
            "coverage_report_generated_at_utc": coverage.get("generated_at_utc"),
            "calendar_sync_generated_at_utc": calendar_sync.get("generated_at_utc"),
            "disposition_generated_at_utc": disposition.get("generated_at_utc"),
        },
        "artifact_urls": {
            "live_pipeline_dashboard": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-live-pipeline-dashboard.json",
            "multi_source_coverage_report": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/reports/multi_source_coverage_report.json",
            "coverage_roadmap": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/status/nycif-coverage-roadmap.json",
            "live_delta_report": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/live_delta_report.json",
            "row_disposition_report": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/row_disposition_report.json",
            "staged_live_manifest": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/staged_live_manifest.json",
            "staged_live_events": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json",
            "citywide_calendar_snapshot": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nyc_citywide_events_calendar_snapshot.json",
        },
        "samples": {
            "newly_added_events": (live_delta.get("added_events") or [])[:5],
            "calendar_only_events": (coverage.get("samples") or {}).get("calendar_only") or [],
        },
        "safety": {
            "safe_for_public_dashboard": True,
            "contains_secrets": False,
            "contains_private_repo_internals": False,
            "contains_credentials": False,
            "contains_tokens": False,
            "browser_side_github_api_polling": False,
            "write_controls": False,
            "deploy_controls": False,
            "public_map_modified": False,
            "production_feed_mutation": False,
            "wordpress_change": False,
            "promotion_allowed": False,
            "manual_review_status": "pending",
        },
    }

    save_json(STATUS_PATH, payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
