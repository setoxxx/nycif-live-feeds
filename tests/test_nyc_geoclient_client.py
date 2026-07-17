"""Tests for NYC Geoclient client cache behavior."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.nyc_geoclient_client import (  # noqa: E402
    NYCGeoclientClient,
    extract_intersection_lat_lng,
    geoclient_borough_name,
    intersection_cache_key,
)


class GeoclientBoroughTests(unittest.TestCase):
    def test_borough_normalization(self) -> None:
        self.assertEqual(geoclient_borough_name("Bk"), "Brooklyn")
        self.assertEqual(geoclient_borough_name("SI"), "Staten Island")


class GeoclientExtractTests(unittest.TestCase):
    def test_extract_lat_lng(self) -> None:
        payload = {"intersection": {"latitude": 40.59, "longitude": -73.92}}
        self.assertEqual(extract_intersection_lat_lng(payload), (40.59, -73.92))


class GeoclientClientTests(unittest.TestCase):
    def test_cache_hit_without_live(self) -> None:
        key = intersection_cache_key("Sand Lane", "Father Capadanno Boulevard", "Brooklyn")
        cache = {
            key: {
                "lat": 40.587,
                "lng": -74.065,
                "geocoder_source": "nyc_geoclient_intersection",
                "confidence": "high",
                "confidence_reason": "test",
            }
        }
        client = NYCGeoclientClient(cache, allow_live=False)
        hit = client.resolve_intersection("Sand Lane", "Father Capadanno Boulevard", "Bk")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["lat"], 40.587)
        self.assertEqual(client.live_calls, 0)

    def test_live_blocked_without_cache(self) -> None:
        client = NYCGeoclientClient({}, allow_live=False)
        self.assertIsNone(client.resolve_intersection("Main St", "Broadway", "Manhattan"))

    @patch.object(NYCGeoclientClient, "_live_intersection")
    def test_live_populates_cache(self, mock_live) -> None:
        mock_live.return_value = {
            "lat": 40.7,
            "lng": -73.9,
            "geocoder_source": "nyc_geoclient_intersection",
            "confidence": "high",
            "confidence_reason": "live test",
        }
        client = NYCGeoclientClient({}, allow_live=True)
        hit = client.resolve_intersection("Ave A", "E 10 St", "Manhattan")
        self.assertIsNotNone(hit)
        self.assertEqual(len(client.cache), 1)


if __name__ == "__main__":
    unittest.main()
