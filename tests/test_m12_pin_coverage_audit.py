#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_full_season_pin_coverage_audit import (  # noqa: E402
    CIVIC_FOCUS,
    build_report,
    prioritize_gaps,
)
from scripts.coverage_gap_utils import parse_intersection  # noqa: E402
from scripts.geocode_list_only_civic_events import (  # noqa: E402
    fill_from_location_cache_memory,
)


class M12PinCoverageAuditTests(unittest.TestCase):
    def test_parse_between_intersection(self) -> None:
        parsed = parse_intersection("41 AVENUE between 80 STREET and 81 STREET  Queens")
        self.assertEqual(parsed, ("41 AVENUE", "80 STREET"))

    def test_build_report_has_civic_totals(self) -> None:
        report = build_report()
        self.assertEqual(report["artifact_type"], "full_season_pin_coverage_audit")
        self.assertGreater(report["approved_feed"]["total"], 30000)
        self.assertEqual(len(report["category_totals"]), len(CIVIC_FOCUS))
        self.assertGreaterEqual(len(report["top_10_pin_gaps"]), 1)

    def test_top_gap_prioritizes_market(self) -> None:
        report = build_report()
        self.assertEqual(report["top_10_pin_gaps"][0]["category"], "market")

    def test_location_cache_memory_fill(self) -> None:
        fill = fill_from_location_cache_memory(
            "Elmhurst Greenmarket Tuesday",
            {
                "elmhurst greenmarket tuesday": {
                    "example_title": "Elmhurst Greenmarket Tuesday",
                    "lat": 40.757795,
                    "lng": -73.829374,
                }
            },
        )
        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertEqual(fill["geocoder_source"], "location_cache_readonly_memory")
        self.assertTrue(fill["proposed_lat"])

    def test_prioritize_gaps_limits(self) -> None:
        gaps = prioritize_gaps(
            [
                {
                    "current_classification": "market",
                    "date": "2026-07-14",
                    "title": "Sample",
                    "source_identity": {"source_event_id": "1"},
                }
            ],
            focus_categories=CIVIC_FOCUS,
            limit=3,
        )
        self.assertEqual(len(gaps), 1)


if __name__ == "__main__":
    unittest.main()
