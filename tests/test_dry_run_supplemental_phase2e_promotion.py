"""Tests for supplemental Phase 2E promotion dry-run."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.dry_run_supplemental_phase2e_promotion import classify_row, row_issues


class SupplementalPhase2eDryRunTests(unittest.TestCase):
    def test_ready_row_blocked_only_by_promotion_allowed(self) -> None:
        row = {
            "overlap_key": "test|2026-07-01",
            "title": "Test",
            "display_location": "Test Park",
            "borough": "Bk",
            "proposed_lat": 40.7,
            "proposed_lng": -73.95,
            "geocoder_source": "nyc_parks_bigapps_events_snapshot",
            "geocoder_confidence": "high",
            "confidence_reason": "test",
            "manual_review_status": "approved",
            "manual_reviewer": "Howard Weiss",
            "manual_reviewed_at_utc": "2026-07-17T00:00:00+00:00",
            "approval_decision_reason": "approved",
            "promotion_allowed": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "production_feed": False,
        }
        self.assertEqual(classify_row(row), "would_pass_if_promotion_authorized")

    def test_missing_reviewer_blocks(self) -> None:
        row = {
            "overlap_key": "test|2026-07-01",
            "title": "Test",
            "display_location": "Test Park",
            "borough": "Bk",
            "proposed_lat": 40.7,
            "proposed_lng": -73.95,
            "geocoder_source": "src",
            "geocoder_confidence": "high",
            "confidence_reason": "test",
            "manual_review_status": "approved",
            "promotion_allowed": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
        }
        issues = row_issues(row)
        self.assertIn("missing_required_field:manual_reviewer", issues)
        self.assertEqual(classify_row(row), "blocked")


if __name__ == "__main__":
    unittest.main()
