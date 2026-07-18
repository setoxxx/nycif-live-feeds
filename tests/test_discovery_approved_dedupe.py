#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_approved_dedupe import dedupe_approved_events, supplemental_fold_eligible  # noqa: E402


class DiscoveryApprovedDedupeTests(unittest.TestCase):
    def test_supplemental_fold_blocks_pending(self) -> None:
        event = {
            "latitude": None,
            "longitude": None,
            "nycif": {"manual_review_status": "pending", "coordinate_status": "list_only"},
        }
        self.assertFalse(supplemental_fold_eligible(event))

    def test_supplemental_fold_allows_approved(self) -> None:
        event = {
            "latitude": 40.75,
            "longitude": -73.98,
            "nycif": {"manual_review_status": "approved", "coordinate_status": "map_ready"},
        }
        self.assertTrue(supplemental_fold_eligible(event))

    def test_dedupe_keeps_map_ready_duplicate(self) -> None:
        events = [
            {
                "id": "review_supplemental:calendar:1@2026-07-16",
                "title": "Access Benefits Fair",
                "location": "123 Main St",
                "latitude": None,
                "longitude": None,
                "source": {"dataset": "nyc-citywide-events-calendar-api", "source_event_id": "1"},
                "nycif": {
                    "event_date": "2026-07-16",
                    "coordinate_status": "list_only",
                    "manual_review_status": "pending",
                    "public_supplemental": True,
                },
            },
            {
                "id": "nyc-parks-bigapps-events:2@2026-07-16",
                "title": "Access Benefits Fair",
                "location": "123 Main St",
                "latitude": 40.75,
                "longitude": -73.98,
                "source": {"dataset": "nyc-parks-bigapps-events", "source_event_id": "2"},
                "nycif": {"event_date": "2026-07-16", "coordinate_status": "map_ready", "manual_review_status": "approved"},
            },
        ]
        kept, stats = dedupe_approved_events(events)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["id"], "nyc-parks-bigapps-events:2@2026-07-16")
        self.assertEqual(stats["removed_duplicate_count"], 1)


if __name__ == "__main__":
    unittest.main()
