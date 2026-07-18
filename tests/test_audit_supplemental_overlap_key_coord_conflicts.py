#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from scripts.audit_supplemental_overlap_key_coord_conflicts import (  # noqa: E402
    build_audit,
    classify_conflict,
)


class SupplementalOverlapKeyConflictAuditTests(unittest.TestCase):
    def test_classify_nearby_same_venue_as_merge(self) -> None:
        row_a = {
            "lat": 40.75,
            "lng": -73.98,
            "display_location": "Lower Highland Playground (in Highland Park)",
        }
        row_b = {
            "lat": 40.751,
            "lng": -73.981,
            "display_location": "Lower Highland Playground in Highland Park",
        }
        recommendation, _ = classify_conflict(row_a, row_b)
        self.assertEqual(recommendation, "merge_dedupe_keep_better_geocode")

    def test_classify_far_apart_different_venues_as_split(self) -> None:
        row_a = {
            "lat": 40.75,
            "lng": -73.98,
            "display_location": "Gymnasium in Al Oerter Recreation Center",
        }
        row_b = {
            "lat": 40.57,
            "lng": -74.09,
            "display_location": "Midland Beach Splash Plaza",
        }
        recommendation, _ = classify_conflict(row_a, row_b)
        self.assertEqual(recommendation, "split_overlap_key_keep_both_pins")

    def test_build_audit_finds_78_conflicts_on_live_export(self) -> None:
        export_path = ROOT / "data/supplemental_approved_export_feed.json"
        if not export_path.exists():
            self.skipTest("export feed snapshot missing")
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        report = build_audit(payload["events"])
        self.assertEqual(report["summary"]["conflict_pair_count"], 78)
        self.assertEqual(
            report["summary"]["projected_export_event_count_after_dedupe_actions"],
            3496,
        )


if __name__ == "__main__":
    unittest.main()
