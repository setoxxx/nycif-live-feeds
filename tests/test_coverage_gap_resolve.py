"""Tests for shared supplemental GPS-fill resolver."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.coverage_gap_utils import (  # noqa: E402
    parse_facility_in_parent,
    resolve_supplemental_coordinates,
)
from scripts.nyc_geoclient_client import NYCGeoclientClient  # noqa: E402
from scripts.nyc_location_gazetteer import NYCLocationGazetteer, gazetteer_entry  # noqa: E402
from scripts.nyc_location_resolver import NYCLocationResolver, ResolveResult  # noqa: E402


def _gazetteer(entries: dict[str, dict]) -> NYCLocationGazetteer:
    return NYCLocationGazetteer(entries)


class ResolveSupplementalCoordinatesTests(unittest.TestCase):
    def test_child_gazetteer_hit(self) -> None:
        child_entry = gazetteer_entry(
            lat=40.731,
            lng=-73.997,
            source="nyc_parks_facility_reference",
            confidence="high",
            confidence_reason="facility",
            label="Handball Court",
        )
        gazetteer = _gazetteer({"mn|handball court": child_entry})
        row = {"display_location": "Handball Court in Washington Square Park", "borough": "Mn"}
        fill = resolve_supplemental_coordinates(row, gazetteer, {}, None)
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "location_gazetteer")

    def test_geoclient_intersection_in_parent(self) -> None:
        gazetteer = _gazetteer({})
        cache_key = "brooklyn|sand lane|father capadanno boulevard"
        geoclient = NYCGeoclientClient(
            {
                cache_key: {
                    "lat": 40.587,
                    "lng": -74.065,
                    "geocoder_source": "nyc_geoclient_intersection",
                    "confidence": "high",
                    "confidence_reason": "cached intersection",
                }
            },
            allow_live=False,
        )
        row = {
            "display_location": "Sand Lane and Father Capadanno Boulevard in Franklin D. Roosevelt Boardwalk",
            "borough": "Bk",
        }
        fill = resolve_supplemental_coordinates(row, gazetteer, {}, None, geoclient=geoclient)
        self.assertIsNotNone(fill)
        self.assertEqual(fill["fill_method"], "nyc_geoclient_intersection")

    def test_resolver_last_resort(self) -> None:
        gazetteer = _gazetteer({})
        resolver = NYCLocationResolver(gazetteer, {}, allow_live_geosearch=False)
        fake = ResolveResult(
            resolved=True,
            tier="tier_2_geosearch_cache",
            lat=40.7,
            lng=-73.9,
            source="nyc_geosearch_planninglabs",
            confidence="high",
            confidence_reason="cached",
        )
        row = {"display_location": "Bryant Park", "borough": "Mn"}
        with patch.object(resolver, "resolve", return_value=fake):
            fill = resolve_supplemental_coordinates(row, gazetteer, {}, resolver)
        self.assertIsNotNone(fill)


class ParseFacilityInParentTests(unittest.TestCase):
    def test_splits_child_parent(self) -> None:
        self.assertEqual(
            parse_facility_in_parent("Pétanque Court in Washington Square Park"),
            ("Pétanque Court", "Washington Square Park"),
        )


if __name__ == "__main__":
    unittest.main()
