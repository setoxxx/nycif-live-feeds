"""Tests for incremental supplemental intake disposition preservation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_supplemental_approved_export_feed import build_export_payload
from scripts.incremental_supplemental_intake import merge_incremental_queue


class IncrementalSupplementalIntakeTests(unittest.TestCase):
    def test_merge_preserves_existing_disposition_and_appends_net_new(self) -> None:
        existing = [
            {
                "review_rank": 1,
                "overlap_key": "alpha|2026-07-01",
                "manual_review_status": "approved",
                "proposed_lat": 40.7,
                "proposed_lng": -74.0,
                "title": "Alpha",
                "intake_type": "parks_only",
                "has_coordinates": True,
            },
            {
                "review_rank": 2,
                "overlap_key": "alpha|2026-07-01",
                "manual_review_status": "approved",
                "proposed_lat": 40.7,
                "proposed_lng": -74.0,
                "title": "Alpha duplicate",
                "intake_type": "parks_only",
                "has_coordinates": True,
            },
            {
                "review_rank": 3,
                "overlap_key": "beta|2026-07-02",
                "manual_review_status": "rejected",
                "title": "Beta",
                "intake_type": "calendar_only",
            },
        ]
        staging = [
            {
                "overlap_key": "alpha|2026-07-01",
                "title": "Alpha refreshed",
                "proposed_lat": 40.8,
                "proposed_lng": -73.9,
                "intake_type": "parks_only",
            },
            {
                "overlap_key": "gamma|2026-07-03",
                "title": "Gamma",
                "display_location": "Gamma Park",
                "borough": "Bk",
                "proposed_lat": 40.65,
                "proposed_lng": -73.95,
                "intake_type": "calendar_only",
                "auto_resolved": True,
                "fill_method": "supplemental_location_memory",
            },
        ]
        merged, stats = merge_incremental_queue(existing, staging)
        by_rank = {row["review_rank"]: row for row in merged}
        self.assertEqual(by_rank[1]["manual_review_status"], "approved")
        self.assertEqual(by_rank[2]["manual_review_status"], "approved")
        self.assertEqual(by_rank[3]["manual_review_status"], "rejected")
        self.assertEqual(by_rank[4]["manual_review_status"], "pending")
        self.assertTrue(by_rank[4]["auto_resolved"])
        self.assertEqual(stats["net_new_row_count"], 1)
        self.assertEqual(stats["preserved_row_count"], 3)
        self.assertTrue(stats["disposition_preserved"])

    def test_export_feed_includes_approved_rows_only(self) -> None:
        queue = [
            {
                "manual_review_status": "approved",
                "overlap_key": "x|2026-07-01",
                "title": "X",
                "proposed_lat": 40.7,
                "proposed_lng": -74.0,
                "intake_type": "parks_only",
            },
            {
                "manual_review_status": "rejected",
                "overlap_key": "y|2026-07-02",
                "title": "Y",
            },
        ]
        payload, report = build_export_payload(queue)
        self.assertEqual(report["export_event_count"], 1)
        self.assertEqual(len(payload["events"]), 1)
        self.assertFalse(payload["production_feed"])
        self.assertFalse(payload["promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
