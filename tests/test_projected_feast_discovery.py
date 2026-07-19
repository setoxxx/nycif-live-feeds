#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class ProjectedFeastDiscoveryTests(unittest.TestCase):
    def test_projected_feast_intake_artifact_exists(self) -> None:
        path = ROOT / "data/staging/projected_feast_events_map_intake.json"
        self.assertTrue(path.exists())
        payload = json.loads(path.read_text(encoding="utf-8"))
        events = payload.get("events") if isinstance(payload, dict) else []
        self.assertGreaterEqual(len(events), 200)

    def test_projected_feast_intake_has_zero_list_only(self) -> None:
        report = json.loads(
            (ROOT / "data/reports/projected_feast_events_map_intake_report.json").read_text(encoding="utf-8")
        )
        self.assertTrue(report["qa_pass"])
        self.assertEqual(report["list_only_count"], 0)
        self.assertGreaterEqual(report["map_ready_count"], 200)

    def test_projected_feast_bulk_coverage_in_approved(self) -> None:
        approved = json.loads((ROOT / "data/events_discovery_v02_approved.json").read_text(encoding="utf-8"))
        projected = [
            e
            for e in approved.get("events", [])
            if e.get("nycif", {}).get("projected_feast_reference")
        ]
        self.assertGreaterEqual(len(projected), 200)

    def test_san_gennaro_in_approved_discovery(self) -> None:
        approved = json.loads((ROOT / "data/events_discovery_v02_approved.json").read_text(encoding="utf-8"))
        hits = [
            e
            for e in approved.get("events", [])
            if (e.get("source") or {}).get("source_event_id") == "feast-of-san-gennaro"
        ]
        self.assertEqual(len(hits), 1)
        event = hits[0]
        self.assertEqual(event["title"], "Feast of San Gennaro")
        self.assertEqual(str(event.get("end_date_time") or "")[:10], "2026-09-20")
        self.assertEqual(event["nycif"]["coordinate_status"], "map_ready")
        self.assertTrue(event["nycif"]["is_major"])

    def test_st_bernard_bergen_beach_in_approved_discovery(self) -> None:
        approved = json.loads((ROOT / "data/events_discovery_v02_approved.json").read_text(encoding="utf-8"))
        hits = [
            e
            for e in approved.get("events", [])
            if (e.get("source") or {}).get("source_event_id") == "st-bernard-madonna-del-carmine-bergen-beach"
        ]
        self.assertEqual(len(hits), 1)
        event = hits[0]
        self.assertIn("St. Bernard", event["title"])
        self.assertEqual(event["nycif"]["coordinate_status"], "map_ready")
        self.assertTrue(event["nycif"]["projected_feast_reference"])


    def test_map_readiness_report_exists_and_passes(self) -> None:
        path = ROOT / "data/reports/projected_feast_map_readiness_report.json"
        self.assertTrue(path.exists())
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(report.get("qa_pass"))
        self.assertEqual(report.get("list_only_count"), 0)
        self.assertGreaterEqual(report.get("projected_discovery_count", 0), 200)
        self.assertGreaterEqual(report.get("religious_feast_discovery_count", 0), 50)

    def test_pr_merge_readiness_report_exists_and_passes(self) -> None:
        path = ROOT / "data/reports/projected_feast_pr_merge_readiness_report.json"
        self.assertTrue(path.exists())
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(report.get("qa_pass"))
        self.assertEqual(report.get("list_only_count"), 0)
        self.assertTrue(report.get("protected_files_unchanged"))
        self.assertTrue(report.get("promotion_allowed_all_false"))
        self.assertEqual(report.get("pr_number"), None)
        self.assertIn("gap_wave4", report.get("waves_merged", []))
        self.assertIn("gap_wave5", report.get("waves_merged", []))
        self.assertGreaterEqual(len(report.get("wave5_added_keys", [])), 12)

    def test_field_desk_verification_checklist_exists(self) -> None:
        path = ROOT / "data/reports/projected_feast_field_desk_verification_checklist.json"
        self.assertTrue(path.exists())
        checklist = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(checklist.get("target_repo"), "setoxxx/nycif-field-desk")
        self.assertGreaterEqual(len(checklist.get("verification_items", [])), 5)


if __name__ == "__main__":
    unittest.main()
