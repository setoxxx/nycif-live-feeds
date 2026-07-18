#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.geocode_unlinked_access_benefits_services import (  # noqa: E402
    TARGET_SOURCE_EVENT_IDS,
    calendar_to_queue_row,
    geocode_targets,
)


class AccessBenefitsGeocodeTests(unittest.TestCase):
    def test_target_ids_are_unique_canonical_cluster(self) -> None:
        self.assertEqual(len(TARGET_SOURCE_EVENT_IDS), len(set(TARGET_SOURCE_EVENT_IDS)))
        self.assertEqual(len(TARGET_SOURCE_EVENT_IDS), 8)

    def test_calendar_to_queue_row_sets_pending(self) -> None:
        row = calendar_to_queue_row(
            {
                "address": "44 Washington Square S",
                "boroughs": ["Mn"],
                "title": "Access Benefits at Fair Fares Promotion - Manhattan",
                "start_date_time": "2026-07-14T14:00:00.000-04:00",
                "source_event_id": "1116816",
            }
        )
        self.assertEqual(row["manual_review_status"], "pending")
        self.assertFalse(row["promotion_allowed"])
        self.assertEqual(row["source_event_id"], "1116816")

    def test_geocode_targets_dry_run_uses_snapshot(self) -> None:
        with patch(
            "scripts.geocode_unlinked_access_benefits_services.resolve_supplemental_coordinates",
            return_value={
                "proposed_lat": 40.75,
                "proposed_lng": -73.98,
                "geocoder_source": "test",
                "geocoder_confidence": "high",
                "confidence_reason": "test fill",
            },
        ):
            report = geocode_targets(allow_live_geosearch=False, write_queue=False)
        self.assertEqual(report["target_count"], 8)
        self.assertEqual(report["filled_count"], 8)
        self.assertTrue(report["qa_pass"])


if __name__ == "__main__":
    unittest.main()
