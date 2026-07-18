#!/usr/bin/env python3
"""Build press/precinct geofence staging rows from supplemental approved export feed."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, repo_relative, save_json_file, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, repo_relative, save_json_file, utc_now_iso

from tools.supplemental.precinct_geofence import geofence_row_from_event

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
PRECINCT_PATH = DATA_DIR / "nypd_precinct_boundaries_reference.json"
STAGING_PATH = DATA_DIR / "supplemental_press_geofence_staging.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_press_geofence_report.json"


def precinct_rows(reference_payload: dict[str, Any]) -> list[dict[str, Any]]:
    precincts = reference_payload.get("precincts")
    if not isinstance(precincts, list):
        raise ValueError("precinct reference missing precincts array")
    return [row for row in precincts if isinstance(row, dict)]


def build_press_geofence_staging() -> dict[str, Any]:
    export_payload = load_json_file(EXPORT_PATH, {})
    if export_payload.get("artifact_type") != "supplemental_approved_export_feed":
        raise ValueError("missing supplemental approved export feed")
    reference_payload = load_json_file(PRECINCT_PATH, {})
    if reference_payload.get("artifact_type") != "nypd_precinct_boundaries_reference":
        raise ValueError("missing NYPD precinct boundaries reference")

    events = export_payload.get("events") or []
    if not isinstance(events, list):
        raise ValueError("export feed events must be a list")
    precincts = precinct_rows(reference_payload)

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    press_candidates = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        row = geofence_row_from_event(event, precincts)
        if not row:
            continue
        key = str(row["overlap_key"])
        if key in seen:
            continue
        seen.add(key)
        if row.get("press_release_candidate"):
            press_candidates += 1
        rows.append(row)

    rows.sort(key=lambda row: (row.get("assigned_precinct") or "", row.get("date") or "", row.get("title") or ""))
    payload = {
        "artifact_type": "supplemental_press_geofence_staging",
        "phase": "phase_3b_press_geofence",
        "generated_at_utc": utc_now_iso(),
        "source_export_path": repo_relative(EXPORT_PATH),
        "precinct_reference_path": repo_relative(PRECINCT_PATH),
        "export_event_count": len(events),
        "geofence_row_count": len(rows),
        "press_release_candidate_count": press_candidates,
        "production_feed": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "rows": rows,
    }
    report = {
        "artifact_type": "supplemental_press_geofence_report",
        "generated_at_utc": payload["generated_at_utc"],
        "qa_pass": True,
        "staging_path": repo_relative(STAGING_PATH),
        "export_event_count": len(events),
        "geofence_row_count": len(rows),
        "press_release_candidate_count": press_candidates,
        "precinct_reference_count": len(precincts),
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Preview map draws precinct polygons on pin click. No email ingestion yet."
        ),
    }
    save_json_file(STAGING_PATH, payload)
    save_json_file(REPORT_PATH, report)
    return report


def main() -> int:
    try:
        report = build_press_geofence_staging()
    except (FileNotFoundError, ValueError) as exc:
        report = {
            "artifact_type": "supplemental_press_geofence_report",
            "generated_at_utc": utc_now_iso(),
            "qa_pass": False,
            "error": str(exc),
            "staging_path": repo_relative(STAGING_PATH),
        }
        save_json_file(REPORT_PATH, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
