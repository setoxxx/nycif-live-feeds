#!/usr/bin/env python3
"""Deterministic regressions for the current NYC Parks Open Data intake."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from scripts import sync_nyc_parks_bigapps_events as parks


class ParksOpenDataSyncTests(unittest.TestCase):
    def test_current_dataset_contract_is_exact(self) -> None:
        self.assertEqual(parks.DATASET_ID, "w3wp-dpdi")
        self.assertEqual(parks.SOURCE_CONTRACT_VERSION, "NYCIF_PARKS_UPCOMING_OPEN_DATA_V3")
        self.assertIn(parks.DATASET_ID, parks.EVENTS_URL)
        self.assertFalse("events_300_rss.json" in parks.EVENTS_URL)

    def test_official_coordinate_becomes_explicit_exact_evidence(self) -> None:
        row = parks.normalize_event_item(
            {
                "guid": "parks-1",
                "title": "Test Parks Event",
                "startdate": "2026-08-10",
                "starttime": "10:00:00",
                "enddate": "2026-08-10",
                "endtime": "11:00:00",
                "coordinates": "40.7829,-73.9654",
                "location": "Central Park",
            }
        )
        self.assertEqual(row["lat"], 40.7829)
        self.assertEqual(row["lng"], -73.9654)
        evidence = row["location_evidence"]
        self.assertEqual(evidence["tier"], "exact_source_coordinate")
        self.assertEqual(evidence["validation_state"], "validated")
        self.assertTrue(evidence["exact_pin_eligible"])
        self.assertEqual(evidence["source_dataset_id"], "w3wp-dpdi")
        self.assertFalse(row["promotion_allowed"])
        self.assertFalse(row["public_map_modified"])

    def test_invalid_or_missing_coordinate_never_invents_evidence(self) -> None:
        for coordinate in (None, "", "not-a-coordinate", "0,0", "91,181"):
            row = parks.normalize_event_item(
                {
                    "guid": "parks-2",
                    "title": "Unlocated Parks Event",
                    "startdate": "2026-08-10",
                    "coordinates": coordinate,
                    "location": "A park",
                }
            )
            self.assertIsNone(row["lat"])
            self.assertIsNone(row["lng"])
            self.assertIsNone(row["location_evidence"])

    def test_legacy_logical_identity_namespace_is_preserved(self) -> None:
        row = parks.normalize_event_item(
            {
                "guid": "parks-42",
                "title": "Identity",
                "startdate": "2026-08-10",
                "location": "Demo Park",
            }
        )
        self.assertEqual(row["source_dataset"], "nyc-parks-bigapps-events")
        self.assertEqual(row["source_event_id"], "parks-42")
        self.assertEqual(row["source_authority_dataset"], "w3wp-dpdi")

    def test_live_fetch_failure_is_fail_closed_and_not_mislabeled_live(self) -> None:
        with patch.object(parks, "fetch_events", side_effect=RuntimeError("boom")), patch.object(
            parks, "save_json"
        ), patch("builtins.print") as mocked_print:
            rc = parks.main()
        self.assertEqual(rc, 1)
        report = json.loads(mocked_print.call_args.args[0])
        self.assertEqual(report["fetch_mode"], "live_fetch_failed")
        self.assertFalse(report["qa_pass"])
        self.assertEqual(report["snapshot_rows"], 0)
        self.assertIn("boom", report["live_fetch_error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)