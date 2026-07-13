"""Tests for multi-source coverage audit helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_multi_source_coverage import (  # noqa: E402
    build_calendar_index,
    build_permit_index,
    date_key,
    title_key,
)
from scripts.sync_nyc_citywide_events_calendar import normalize_calendar_item  # noqa: E402


class MultiSourceCoverageTests(unittest.TestCase):
    def test_date_key(self) -> None:
        self.assertEqual(date_key("2026-07-13T10:00:00.000"), "2026-07-13")
        self.assertEqual(date_key(""), "")

    def test_title_key_normalizes(self) -> None:
        self.assertEqual(title_key("  Parade Day! "), title_key("parade day!"))

    def test_overlap_index(self) -> None:
        permits = [
            {"event_name": "Summer Jam", "start_date_time": "2026-07-13T09:00:00"},
            {"event_name": "Permit Only", "start_date_time": "2026-07-14T09:00:00"},
        ]
        calendar = [
            {"title": "Summer Jam", "start_date_time": "2026-07-13T10:00:00.000-04:00"},
            {"title": "Calendar Only", "start_date_time": "2026-07-15T10:00:00.000-04:00"},
        ]
        permit_index = build_permit_index(permits)
        calendar_index = build_calendar_index(calendar)
        overlap = set(permit_index) & set(calendar_index)
        self.assertEqual(overlap, {title_key("Summer Jam") + "|2026-07-13"})

    def test_normalize_calendar_item_safety_fields(self) -> None:
        row = normalize_calendar_item(
            {
                "id": 123,
                "guid": "abc",
                "name": "Test Event",
                "startDate": "2026-07-13T10:00:00.000-04:00",
                "categories": ["Parks & Recreation"],
                "boroughs": ["Manhattan"],
            }
        )
        self.assertEqual(row["source_dataset"], "nyc-citywide-events-calendar-api")
        self.assertFalse(row["promotion_allowed"])
        self.assertFalse(row["public_map_modified"])
        self.assertEqual(row["manual_review_status"], "pending")

    def test_audit_script_writes_report(self) -> None:
        from scripts import audit_multi_source_coverage as audit_mod

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            reports_dir = data_dir / "reports"
            data_dir.mkdir()
            reports_dir.mkdir()
            permit_path = data_dir / "raw_nyc_open_data_snapshot.json"
            calendar_path = data_dir / "nyc_citywide_events_calendar_snapshot.json"
            permit_path.write_text(
                json.dumps(
                    [
                        {
                            "source_dataset": "tvpp-9vvx",
                            "event_name": "Shared Event",
                            "start_date_time": "2099-01-01T09:00:00",
                            "event_agency": "Parks Department",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            calendar_path.write_text(
                json.dumps(
                    [
                        {
                            "source_dataset": "nyc-citywide-events-calendar-api",
                            "title": "Shared Event",
                            "start_date_time": "2099-01-01T10:00:00.000-04:00",
                            "categories": ["Parks & Recreation"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            original_permit = audit_mod.PERMIT_SNAPSHOT
            original_calendar = audit_mod.CALENDAR_SNAPSHOT
            original_report = audit_mod.REPORT_PATH
            original_disposition = audit_mod.ROW_DISPOSITION
            original_manifest = audit_mod.STAGED_MANIFEST
            try:
                audit_mod.PERMIT_SNAPSHOT = permit_path
                audit_mod.CALENDAR_SNAPSHOT = calendar_path
                audit_mod.ROW_DISPOSITION = data_dir / "missing_disposition.json"
                audit_mod.STAGED_MANIFEST = data_dir / "missing_manifest.json"
                audit_mod.REPORT_PATH = reports_dir / "multi_source_coverage_report.json"
                self.assertEqual(audit_mod.main(), 0)
                payload = json.loads(audit_mod.REPORT_PATH.read_text(encoding="utf-8"))
                self.assertTrue(payload["qa_pass"])
                self.assertEqual(payload["overlap_analysis"]["title_date_overlap_unique_keys"], 1)
            finally:
                audit_mod.PERMIT_SNAPSHOT = original_permit
                audit_mod.CALENDAR_SNAPSHOT = original_calendar
                audit_mod.REPORT_PATH = original_report
                audit_mod.ROW_DISPOSITION = original_disposition
                audit_mod.STAGED_MANIFEST = original_manifest


if __name__ == "__main__":
    unittest.main()
