"""Tests for GeoJSON polygon helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.geojson_polygon_utils import (  # noqa: E402
    point_in_polygon_geometry,
    ring_centroid,
    snap_to_park_interior,
)


SQUARE_PARK = {
    "type": "Polygon",
    "coordinates": [
        [
            [-74.0, 40.7],
            [-73.99, 40.7],
            [-73.99, 40.71],
            [-74.0, 40.71],
            [-74.0, 40.7],
        ]
    ],
}


class PolygonUtilsTests(unittest.TestCase):
    def test_point_inside_square(self) -> None:
        self.assertTrue(point_in_polygon_geometry(-73.995, 40.705, SQUARE_PARK))

    def test_point_outside_square(self) -> None:
        self.assertFalse(point_in_polygon_geometry(-73.98, 40.705, SQUARE_PARK))

    def test_ring_centroid(self) -> None:
        lat, lng = ring_centroid(SQUARE_PARK["coordinates"][0])
        self.assertAlmostEqual(lat, 40.705, places=2)
        self.assertAlmostEqual(lng, -73.995, places=2)

    def test_snap_to_park_interior(self) -> None:
        index = {
            "test park": [
                {
                    "signname": "Test Park",
                    "borough_label": "Brooklyn",
                    "geometry": SQUARE_PARK,
                    "centroid_lat": 40.705,
                    "centroid_lng": -73.995,
                }
            ]
        }
        snapped = snap_to_park_interior(40.705, -73.98, "Test Park", "Bk", index)
        self.assertIsNotNone(snapped)
        self.assertAlmostEqual(snapped[0], 40.705, places=2)
        self.assertAlmostEqual(snapped[1], -73.995, places=2)


if __name__ == "__main__":
    unittest.main()
