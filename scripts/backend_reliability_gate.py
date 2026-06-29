#!/usr/bin/env python3
"""Phase 1 backend reliability gate for NYCIF live feeds.

This script is intentionally strict about pipeline integrity and intentionally tolerant
about legitimate review queues. A row needing GPS review is not a pipeline failure;
a row silently disappearing is a failure.

Outputs:
- data/backend_reliability_gate_report.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_PATH = DATA_DIR / "backend_reliability_gate_report.json"

REQUIRED_FILES = {
    "raw_snapshot": DATA_DIR / "raw_nyc_open_data_snapshot.json",
    "live_sync_report": DATA_DIR / "live_sync_report.json",
    "test_feed": DATA_DIR / "nycif_live_test_enriched_events.json",
    "test_manifest": DATA_DIR / "test_enriched_feed_manifest.json",
    "staged_feed": DATA_DIR / "nycif_staged_live_events.json",
    "staged_manifest": DATA_DIR / "staged_live_manifest.json",
    "location_cache": DATA_DIR / "location_cache.json",
    "gps_repository_report": DATA_DIR / "gps_repository_report.json",
    "gps_needs_review_events": DATA_DIR / "gps_needs_review_events.json",
    "live_delta_report": DATA_DIR / "live_delta_report.json",
    "remainder_year_coverage_report": DATA_DIR / "remainder_year_coverage_report.json",
    "row_disposition_report": DATA_DIR / "row_disposition_report.json",
    "row_disposition_events": DATA_DIR / "row_disposition_events.json",
    "feed_anomaly_report": DATA_DIR / "feed_anomaly_report.json",
}


def load_json_file(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception as exc:
        return {"__load_error__": str(exc)}


def rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def save_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def issue(severity: str, code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "details": details,
    }


def main() -> int:
    issues: list[dict[str, Any]] = []
    files: dict[str, dict[str, Any]] = {}

    for name, path in REQUIRED_FILES.items():
        exists = path.exists() and path.stat().st_size > 0
        files[name] = {"path": str(path.relative_to(ROOT)), "exists": exists, "size_bytes": path.stat().st_size if path.exists() else 0}
        if not exists:
            issues.append(issue("fail", "missing_required_file", f"Required QA artifact is missing or empty: {name}", files[name]))

    raw_rows = rows_from_payload(load_json_file(REQUIRED_FILES["raw_snapshot"], []))
    test_payload = load_json_file(REQUIRED_FILES["test_feed"], {})
    test_rows = rows_from_payload(test_payload)
    staged_payload = load_json_file(REQUIRED_FILES["staged_feed"], {})
    staged_rows = rows_from_payload(staged_payload)
    row_disposition = load_json_file(REQUIRED_FILES["row_disposition_report"], {})
    gps_report = load_json_file(REQUIRED_FILES["gps_repository_report"], {})
    gps_review = load_json_file(REQUIRED_FILES["gps_needs_review_events"], {})
    staged_manifest = load_json_file(REQUIRED_FILES["staged_manifest"], {})

    if not raw_rows:
        issues.append(issue("fail", "raw_snapshot_empty", "Raw NYC Open Data snapshot loaded zero rows."))
    if not test_rows:
        issues.append(issue("fail", "test_feed_empty", "Test enriched feed loaded zero events."))
    if not staged_rows:
        issues.append(issue("fail", "staged_feed_empty", "Staged feed loaded zero events."))

    if isinstance(row_disposition, dict):
        if row_disposition.get("__load_error__"):
            issues.append(issue("fail", "row_disposition_unreadable", "Row disposition report is unreadable.", row_disposition.get("__load_error__")))
        if row_disposition.get("unclassified_rows") not in (0, None):
            issues.append(issue("fail", "unclassified_rows", "One or more incoming rows are not classified into the QA contract.", row_disposition.get("unclassified_rows")))
        if row_disposition.get("qa_pass") is not True:
            issues.append(issue("fail", "row_disposition_qa_not_passed", "Row disposition QA did not pass.", row_disposition.get("disposition_counts")))
        if row_disposition.get("current_future_raw_rows") and row_disposition.get("classified_rows") != row_disposition.get("current_future_raw_rows"):
            issues.append(issue("fail", "classification_count_mismatch", "Classified row count does not match current/future raw row count.", {
                "current_future_raw_rows": row_disposition.get("current_future_raw_rows"),
                "classified_rows": row_disposition.get("classified_rows"),
            }))
    else:
        issues.append(issue("fail", "row_disposition_missing", "Row disposition report is missing or malformed."))

    if isinstance(gps_report, dict):
        needs_review_count = int(gps_report.get("needs_review_count") or 0)
        if needs_review_count > 0:
            issues.append(issue("warn", "gps_review_queue_not_empty", "Some events still require GPS review; this is expected and not a pipeline failure.", needs_review_count))
        if int(gps_report.get("cache_entry_count") or 0) <= 0:
            issues.append(issue("fail", "gps_cache_empty", "GPS repository/cache has no entries."))
    else:
        issues.append(issue("fail", "gps_report_missing", "GPS repository report is missing or malformed."))

    review_rows = rows_from_payload(gps_review)
    if isinstance(gps_report, dict) and int(gps_report.get("needs_review_count") or 0) != len(review_rows):
        issues.append(issue("warn", "gps_review_count_mismatch", "GPS review count and review queue event count differ.", {
            "report_needs_review_count": gps_report.get("needs_review_count"),
            "review_queue_events": len(review_rows),
        }))

    if isinstance(staged_manifest, dict):
        if staged_manifest.get("staged_feed_events") != len(staged_rows):
            issues.append(issue("warn", "staged_manifest_count_mismatch", "Staged manifest count differs from staged feed event count.", {
                "manifest_staged_feed_events": staged_manifest.get("staged_feed_events"),
                "actual_staged_feed_events": len(staged_rows),
            }))
        if int(staged_manifest.get("skipped_needs_review_or_bad_gps") or 0) < 0:
            issues.append(issue("fail", "invalid_skipped_count", "Staged manifest has invalid skipped count."))

    fail_count = sum(1 for item in issues if item["severity"] == "fail")
    warn_count = sum(1 for item in issues if item["severity"] == "warn")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "phase_1_backend_reliability",
        "gate_pass": fail_count == 0,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "summary": {
            "raw_rows_loaded": len(raw_rows),
            "test_feed_events": len(test_rows),
            "staged_feed_events": len(staged_rows),
            "row_disposition_qa_pass": row_disposition.get("qa_pass") if isinstance(row_disposition, dict) else None,
            "unclassified_rows": row_disposition.get("unclassified_rows") if isinstance(row_disposition, dict) else None,
            "gps_cache_entry_count": gps_report.get("cache_entry_count") if isinstance(gps_report, dict) else None,
            "gps_needs_review_count": gps_report.get("needs_review_count") if isinstance(gps_report, dict) else None,
        },
        "files": files,
        "issues": issues,
    }
    save_json_file(REPORT_PATH, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
