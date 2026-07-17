"""Tests for supplemental borough backfill."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.backfill_supplemental_missing_borough import (
    apply_backfill,
    queue_borough_from_source,
    resolve_borough,
)
from scripts.nyc_location_gazetteer import NYCLocationGazetteer


class SupplementalBoroughBackfillTests(unittest.TestCase):
    def test_queue_borough_from_source_maps_full_labels(self) -> None:
        self.assertEqual(queue_borough_from_source("Brooklyn"), "Bk")
        self.assertEqual(queue_borough_from_source("Mn"), "Mn")
        self.assertIsNone(queue_borough_from_source(""))

    def test_apply_backfill_uses_parks_properties(self) -> None:
        queue = [
            {
                "manual_review_status": "approved",
                "display_location": "Prospect Park",
                "borough": "",
                "promotion_allowed": False,
            }
        ]
        updated, report = apply_backfill(queue)
        self.assertEqual(updated[0]["borough"], "Bk")
        self.assertEqual(updated[0]["borough_backfill_source"], "nyc_parks_properties_reference")
        self.assertEqual(report["backfilled_count"], 1)
        self.assertFalse(updated[0]["promotion_allowed"])

    def test_apply_backfill_uses_sibling_approved_row(self) -> None:
        queue = [
            {
                "manual_review_status": "approved",
                "display_location": "Custom Venue XYZ",
                "borough": "Qn",
            },
            {
                "manual_review_status": "approved",
                "display_location": "Custom Venue XYZ",
                "borough": "",
            },
        ]
        updated, report = apply_backfill(queue)
        self.assertEqual(updated[1]["borough"], "Qn")
        self.assertEqual(updated[1]["borough_backfill_source"], "sibling_approved_row")
        self.assertEqual(report["source_counts"]["sibling_approved_row"], 1)

    def test_resolve_borough_leaves_unknown_display_unfilled(self) -> None:
        row = {
            "manual_review_status": "approved",
            "display_location": "Totally Unknown Non-Park Venue 99999",
            "borough": "",
        }
        borough, source = resolve_borough(
            row,
            parks_index={},
            memory_display_index={},
            gazetteer=NYCLocationGazetteer({}),
            sibling_index={},
        )
        self.assertIsNone(borough)
        self.assertIsNone(source)


if __name__ == "__main__":
    unittest.main()
