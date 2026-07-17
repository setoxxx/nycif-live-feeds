"""Tests for supplemental rejected-row re-review pass."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.apply_supplemental_rejected_pass import (
    is_ungeocodable_location,
    resolve_coordinates,
    supplemental_borough_for_geosearch,
)
from scripts.nyc_location_gazetteer import gazetteer_entry
from scripts.nyc_location_resolver import NYCLocationResolver, ResolveResult


class SupplementalRejectedPassHelperTests(unittest.TestCase):
    def test_supplemental_borough_for_geosearch(self) -> None:
        self.assertEqual(supplemental_borough_for_geosearch("Mn"), "Manhattan")
        self.assertIsNone(supplemental_borough_for_geosearch("Bx, Bk, Mn, Qn, SI"))

    def test_is_ungeocodable_location(self) -> None:
        self.assertTrue(is_ungeocodable_location("Poll Sites Citywide", "Mn"))
        self.assertFalse(is_ungeocodable_location("Astoria Pool in Astoria Park", "Qn"))


class SupplementalRejectedPassResolveTests(unittest.TestCase):
    def test_resolve_coordinates_uses_geosearch_after_gazetteer_miss(self) -> None:
        gazetteer_index = {}
        gazetteer = __import__("scripts.nyc_location_gazetteer", fromlist=["NYCLocationGazetteer"]).NYCLocationGazetteer(
            gazetteer_index
        )
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=False)
        fake_result = ResolveResult(
            resolved=True,
            tier="tier_2_geosearch_cache",
            lat=40.7,
            lng=-73.9,
            source="nyc_geosearch_planninglabs",
            confidence="high",
            confidence_reason="cached",
            label="Test Pool",
            query_used="Test Pool, Queens, NY",
        )
        row = {
            "overlap_key": "test|2026-07-17",
            "display_location": "Test Pool in Example Park",
            "borough": "Qn",
        }
        with patch.object(resolver, "resolve", return_value=fake_result):
            fill = resolve_coordinates(row, gazetteer, {}, resolver)
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "nyc_geosearch_cache")
        self.assertEqual(fill["geocoder_source"], "nyc_geosearch_planninglabs")

    def test_resolve_coordinates_skips_citywide(self) -> None:
        gazetteer = __import__("scripts.nyc_location_gazetteer", fromlist=["NYCLocationGazetteer"]).NYCLocationGazetteer({})
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=True)
        row = {
            "overlap_key": "election|2026-11-01",
            "display_location": "Poll Sites Citywide",
            "borough": "Mn",
        }
        fill = resolve_coordinates(row, gazetteer, {}, resolver)
        self.assertIsNone(fill)


if __name__ == "__main__":
    unittest.main()
