"""Tests for precinct geofence helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.supplemental.precinct_geofence import (
    find_precinct_for_point,
    geofence_row_from_event,
    is_press_release_candidate,
    normalize_precinct_features,
)


class PrecinctGeofenceTests(unittest.TestCase):
    def test_press_heuristic(self) -> None:
        self.assertTrue(is_press_release_candidate({"title": "NYPD seeking individual"}))
        self.assertFalse(is_press_release_candidate({"title": "Pool Lap Swim"}))

    def test_normalize_precinct_features(self) -> None:
        rows = normalize_precinct_features(
            [
                {
                    "properties": {"precinct": "1"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71], [-74.01, 40.71], [-74.01, 40.70]]],
                    },
                }
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["precinct"], "1")

    def test_find_precinct_for_point(self) -> None:
        precincts = [
            {
                "precinct": "99",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71], [-74.01, 40.71], [-74.01, 40.70]]],
                },
            }
        ]
        self.assertEqual(find_precinct_for_point(40.705, -74.005, precincts), "99")
        self.assertIsNone(find_precinct_for_point(40.60, -73.90, precincts))

    def test_geofence_row_safety_fields(self) -> None:
        row = geofence_row_from_event(
            {
                "overlap_key": "test|2026-07-18",
                "title": "Pool day",
                "lat": 40.705,
                "lng": -74.005,
            },
            [
                {
                    "precinct": "99",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71], [-74.01, 40.71], [-74.01, 40.70]]],
                    },
                }
            ],
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["assigned_precinct"], "99")
        self.assertFalse(row["promotion_allowed"])


if __name__ == "__main__":
    unittest.main()
