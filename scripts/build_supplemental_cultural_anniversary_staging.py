#!/usr/bin/env python3
"""Build cultural anniversary staging rows from supplemental approved export feed."""

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

from tools.supplemental.cultural_anniversary import anniversary_row_from_event

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
STAGING_PATH = DATA_DIR / "supplemental_cultural_anniversary_staging.json"
REPORT_PATH = DATA_DIR / "reports" / "supplemental_cultural_anniversary_report.json"


def build_anniversary_staging() -> dict[str, Any]:
    export_payload = load_json_file(EXPORT_PATH, {})
    if export_payload.get("artifact_type") != "supplemental_approved_export_feed":
        raise ValueError("missing supplemental approved export feed")
    events = export_payload.get("events") or []
    if not isinstance(events, list):
        raise ValueError("export feed events must be a list")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        row = anniversary_row_from_event(event)
        if not row:
            continue
        key = str(row["overlap_key"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    rows.sort(key=lambda row: (row.get("date") or "", row.get("title") or ""))
    numbered = sum(1 for row in rows if row.get("anniversary_number") is not None)
    payload = {
        "artifact_type": "supplemental_cultural_anniversary_staging",
        "phase": "phase_3a_cultural_anniversary",
        "generated_at_utc": utc_now_iso(),
        "source_export_path": repo_relative(EXPORT_PATH),
        "export_event_count": len(events),
        "anniversary_row_count": len(rows),
        "numbered_anniversary_count": numbered,
        "unnumbered_annual_count": len(rows) - numbered,
        "production_feed": False,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "rows": rows,
    }
    report = {
        "artifact_type": "supplemental_cultural_anniversary_report",
        "generated_at_utc": payload["generated_at_utc"],
        "qa_pass": True,
        "staging_path": repo_relative(STAGING_PATH),
        "export_event_count": len(events),
        "anniversary_row_count": len(rows),
        "numbered_anniversary_count": numbered,
        "unnumbered_annual_count": len(rows) - numbered,
        "sample_overlap_keys": [row["overlap_key"] for row in rows[:8]],
        "safety": {
            "production_feed": False,
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
        },
        "next_required_step": (
            "Preview map only. Human may fill edition_year and story text before any promotion."
        ),
    }
    save_json_file(STAGING_PATH, payload)
    save_json_file(REPORT_PATH, report)
    return report


def main() -> int:
    try:
        report = build_anniversary_staging()
    except (FileNotFoundError, ValueError) as exc:
        report = {
            "artifact_type": "supplemental_cultural_anniversary_report",
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
