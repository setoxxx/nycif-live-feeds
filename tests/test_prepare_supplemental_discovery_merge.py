#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_supplemental_discovery_merge import (  # noqa: E402
    analyze_export_events,
    build_readiness,
    identity_key,
)


class PrepareSupplementalDiscoveryMergeTests(unittest.TestCase):
    def test_identity_key_normalizes_dataset_and_date(self) -> None:
        key = identity_key(" NYC-Citywide-Events ", " 1047976 ", "2026-07-16T18:00:00")
        self.assertEqual(key, ("nyc-citywide-events", "1047976", "2026-07-16"))

    def test_analyze_export_events_splits_net_new_and_duplicates(self) -> None:
        approved = {
            identity_key("nyc-citywide-events-calendar-api", "1", "2026-07-16"),
        }
        events = [
            {
                "source_dataset": "nyc-citywide-events-calendar-api",
                "source_event_id": "1",
                "date": "2026-07-16",
                "lat": 40.75,
                "lng": -73.98,
                "title": "Already present",
            },
            {
                "source_dataset": "nyc-parks-bigapps-events",
                "source_event_id": "99",
                "date": "2026-07-17",
                "lat": 40.76,
                "lng": -73.97,
                "title": "Net new",
                "intake_type": "parks_only",
                "borough": "Mn",
            },
            {
                "source_dataset": "nyc-parks-bigapps-events",
                "source_event_id": "bad",
                "date": "2026-07-17",
                "lat": None,
                "lng": None,
                "title": "Missing coords",
            },
        ]
        analysis = analyze_export_events(events, approved)
        self.assertEqual(analysis["export_event_count"], 3)
        self.assertEqual(analysis["already_in_approved_discovery"], 1)
        self.assertEqual(analysis["net_new_to_merge"], 1)
        self.assertEqual(analysis["missing_coords"], 1)

    def test_committed_readiness_report_passes_qa(self) -> None:
        report_path = ROOT / "data/reports/supplemental_discovery_merge_readiness_report.json"
        if not report_path.exists():
            self.skipTest("readiness report snapshot missing")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report.get("qa_pass"))
        self.assertFalse(report.get("merge_authorized"))
        self.assertEqual(report.get("errors"), [])
        safety = report.get("safety") or {}
        self.assertFalse(safety.get("public_map_modified"))
        self.assertFalse(safety.get("schema_v1_discovery_modified"))

    def test_build_readiness_matches_committed_snapshot_when_gates_pass(self) -> None:
        export_path = ROOT / "data/supplemental_approved_export_feed.json"
        overlap_path = ROOT / "data/reports/supplemental_overlap_key_coord_conflict_audit_report.json"
        if not export_path.exists() or not overlap_path.exists():
            self.skipTest("supplemental export or overlap audit snapshot missing")
        overlap = json.loads(overlap_path.read_text(encoding="utf-8"))
        if not overlap.get("qa_pass"):
            self.skipTest("overlap audit snapshot not passing")
        report = build_readiness()
        self.assertTrue(report["qa_pass"])
        self.assertGreater(report["supplemental_export"]["net_new_to_merge"], 0)
        self.assertGreater(report["projected_after_merge"]["approved_discovery_total"], 30700)


if __name__ == "__main__":
    unittest.main()
