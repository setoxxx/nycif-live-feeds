"""Tests for net-new live sync supplemental review batch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_supplemental_manual_approval_decisions import apply_decision
from scripts.apply_supplemental_net_new_live_sync_review import classify_row, is_canceled_row


class NetNewLiveSyncReviewTests(unittest.TestCase):
    def test_apply_decision_patches_coordinates_from_decision(self) -> None:
        row = {
            "overlap_key": "test|2026-07-18",
            "manual_review_status": "pending",
            "proposed_lat": None,
            "proposed_lng": None,
        }
        decision = {
            "manual_review_status": "approved",
            "proposed_lat": 40.75,
            "proposed_lng": -73.98,
            "geocoder_source": "nyc_geosearch_planninglabs",
            "geocoder_confidence": "high",
            "confidence_reason": "test fill",
            "approval_decision_reason": "approved for test",
        }
        out = apply_decision(row, decision, "Howard Weiss", "2026-07-17T00:00:00+00:00")
        self.assertEqual(out["manual_review_status"], "approved")
        self.assertEqual(out["proposed_lat"], 40.75)
        self.assertTrue(out["has_coordinates"])

    def test_classify_rejects_canceled_title(self) -> None:
        row = {"title": "CANCELED: Yoga", "overlap_key": "x|2026-07-17", "review_rank": 1}
        decision = classify_row(
            row,
            gazetteer=object(),
            resolver=object(),
            geoclient=None,
            parks_overlap={},
            parks_properties={},
        )
        self.assertEqual(decision["manual_review_status"], "rejected")
        self.assertTrue(is_canceled_row(row))


if __name__ == "__main__":
    unittest.main()
