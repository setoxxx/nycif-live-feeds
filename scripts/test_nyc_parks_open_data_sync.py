#!/usr/bin/env python3
"""Deterministic regressions for the NYC Parks official Open Data intake."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import sync_nyc_parks_bigapps_events as parks


class ParksOpenDataSyncTests(unittest.TestCase):
    def test_official_dataset_contract_is_exact(self) -> None:
        self.assertEqual(parks.EVENTS_DATASET_ID, "fudw-fgrp")
        self.assertEqual(parks.LOCATIONS_DATASET_ID, "cpcm-i88g")
        self.assertEqual(parks.CATEGORIES_DATASET_ID, "xtsw-fqvh")
        self.assertEqual(parks.SOURCE_CONTRACT_VERSION, "NYCIF_PARKS_EVENTS_OPEN_DATA_V2")

    def test_related_tables_join_only_on_exact_event_id(self) -> None:
        rows = [
            {"event_id": "100", "name": "Exact"},
            {"event_id": "101", "name": "Other"},
            {"event_id": "", "name": "No key"},
        ]
        index = parks.related_index(rows)
        self.assertEqual([row["name"] for row in index["100"]], ["Exact"])
        self.assertEqual([row["name"] for row in index["101"]], ["Other"])
        self.assertNotIn("", index)

    def test_single_authoritative_source_point_is_retained(self) -> None:
        event = {"event_id": "42", "title": "Park event", "date": "2026-08-10", "start_time": "10:00 AM"}
        locations = [
            {"event_id": "42", "name": "Demo Park", "lat": "40.7001", "long": "-73.9001", "borough": "Brooklyn"}
        ]
        result = parks.normalize_event_item(event, locations, [])
        self.assertEqual(result["lat"], 40.7001)
        self.assertEqual(result["lng"], -73.9001)
        self.assertEqual(result["source_coordinate_state"], "single_source_location_point")
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["public_map_modified"])

    def test_multiple_authoritative_points_do_not_guess_one_pin(self) -> None:
        event = {"event_id": "42", "title": "Multi-location event", "date": "2026-08-10"}
        locations = [
            {"event_id": "42", "name": "A", "lat": "40.7001", "long": "-73.9001"},
            {"event_id": "42", "name": "B", "lat": "40.7101", "long": "-73.9101"},
        ]
        result = parks.normalize_event_item(event, locations, [])
        self.assertIsNone(result["lat"])
        self.assertIsNone(result["lng"])
        self.assertEqual(result["source_coordinate_count"], 2)
        self.assertEqual(result["source_coordinate_state"], "multiple_source_location_points")

    def test_invalid_or_missing_point_remains_unmapped(self) -> None:
        event = {"event_id": "42", "title": "No point", "date": "2026-08-10"}
        locations = [{"event_id": "42", "lat": "0", "long": "0"}]
        result = parks.normalize_event_item(event, locations, [])
        self.assertIsNone(result["lat"])
        self.assertIsNone(result["lng"])
        self.assertEqual(result["source_coordinate_state"], "no_source_location_point")

    def test_legacy_identity_namespace_is_preserved_with_new_provenance(self) -> None:
        event = {"event_id": "42", "title": "Identity", "date": "2026-08-10"}
        result = parks.normalize_event_item(event, [], [])
        self.assertEqual(result["source_dataset"], "nyc-parks-bigapps-events")
        self.assertEqual(result["source_event_id"], "42")
        self.assertEqual(result["source_authority_dataset"], "fudw-fgrp")
        self.assertEqual(result["provenance"]["join_key"], "event_id")
        self.assertEqual(result["provenance"]["locations_dataset_id"], "cpcm-i88g")

    def test_live_fetch_failure_cannot_be_mislabeled_live(self) -> None:
        committed = [{"source_event_id": "saved", "start_date": "2099-01-01", "end_date": "2099-01-01"}]
        with patch.object(parks, "fetch_official_tables", side_effect=RuntimeError("boom")), patch.object(
            parks, "load_committed_snapshot_events", return_value=committed
        ), patch.object(parks, "save_json"):
            # Capture printed report and prove fallback returns success only as a
            # non-live staging result. build_daily_data_health still requires
            # fetch_mode == live, so this can never clear production freshness.
            with patch("builtins.print") as mocked_print:
                rc = parks.main()
        self.assertEqual(rc, 0)
        report_text = mocked_print.call_args.args[0]
        self.assertIn('"fetch_mode": "committed_snapshot_fallback"', report_text)
        self.assertNotIn('"fetch_mode": "live"', report_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
