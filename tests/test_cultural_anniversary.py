"""Tests for cultural anniversary detection helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.supplemental.cultural_anniversary import detect_anniversary, anniversary_row_from_event


class CulturalAnniversaryTests(unittest.TestCase):
    def test_detects_ordinal_annual(self) -> None:
        detected = detect_anniversary("The 15th Annual Bronx Pride Festival")
        self.assertIsNotNone(detected)
        assert detected is not None
        self.assertEqual(detected["anniversary_number"], 15)
        self.assertEqual(detected["detection_pattern"], "ordinal_annual")

    def test_detects_ordinal_anniversary(self) -> None:
        detected = detect_anniversary("Tribute to the Doors 60th Anniversary")
        self.assertIsNotNone(detected)
        assert detected is not None
        self.assertEqual(detected["anniversary_number"], 60)

    def test_detects_unnumbered_annual(self) -> None:
        detected = detect_anniversary("Annual Into The Light Walk For Epilepsy")
        self.assertIsNotNone(detected)
        assert detected is not None
        self.assertIsNone(detected["anniversary_number"])
        self.assertEqual(detected["detection_pattern"], "annual_unnumbered")

    def test_anniversary_row_preserves_safety_fields(self) -> None:
        row = anniversary_row_from_event(
            {
                "overlap_key": "test|2026-07-18",
                "title": "9th Annual Community Day",
                "date": "2026-07-18",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertFalse(row["promotion_allowed"])
        self.assertFalse(row["production_feed"])
        self.assertEqual(row["manual_review_status"], "pending")


if __name__ == "__main__":
    unittest.main()
