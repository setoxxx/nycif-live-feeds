"""Tests for tiered NYC location resolver."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import MethodType

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.nyc_location_gazetteer import NYCLocationGazetteer, build_gazetteer_index, gazetteer_entry
from scripts.nyc_location_resolver import NYCLocationResolver, ResolveResult


class FakeGeoclient:
    def __init__(self, hits=None):
        self.hits = hits or {}
        self.calls = []

    def resolve_intersection(self, street1, street2, borough):
        self.calls.append((street1, street2, borough))
        return self.hits.get((street1, street2, borough))


class GazetteerTests(unittest.TestCase):
    def test_build_gazetteer_index_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            (data / "location_cache.json").write_text(
                json.dumps(
                    {
                        "entries": {
                            "event_id:1": {
                                "lat": 40.7,
                                "lng": -74.0,
                                "display_location": "Test Park",
                                "borough": "Brooklyn",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (data / "nyc_parks_facility_reference.json").write_text(json.dumps({"facilities": []}), encoding="utf-8")
            (data / "nyc_parks_bigapps_events_snapshot.json").write_text(json.dumps({"events": []}), encoding="utf-8")
            (data / "manual_gps_reference.json").write_text(json.dumps({"references": []}), encoding="utf-8")

            import scripts.nyc_location_gazetteer as gaz_mod

            originals = {
                "LOCATION_CACHE_PATH": gaz_mod.LOCATION_CACHE_PATH,
                "PARKS_FACILITY_PATH": gaz_mod.PARKS_FACILITY_PATH,
                "PARKS_EVENTS_PATH": gaz_mod.PARKS_EVENTS_PATH,
                "MANUAL_REFERENCE_PATH": gaz_mod.MANUAL_REFERENCE_PATH,
                "GEOSEARCH_CACHE_PATH": gaz_mod.GEOSEARCH_CACHE_PATH,
            }
            try:
                gaz_mod.LOCATION_CACHE_PATH = data / "location_cache.json"
                gaz_mod.PARKS_FACILITY_PATH = data / "nyc_parks_facility_reference.json"
                gaz_mod.PARKS_EVENTS_PATH = data / "nyc_parks_bigapps_events_snapshot.json"
                gaz_mod.MANUAL_REFERENCE_PATH = data / "manual_gps_reference.json"
                gaz_mod.GEOSEARCH_CACHE_PATH = data / "nyc_geosearch_gazetteer_cache.json"
                built = build_gazetteer_index()
                self.assertGreaterEqual(built["index_key_count"], 1)
            finally:
                for name, value in originals.items():
                    setattr(gaz_mod, name, value)

    def test_resolver_gazetteer_hit(self) -> None:
        index = {
            "brooklyn|test park": gazetteer_entry(
                lat=40.7,
                lng=-74.0,
                source="test",
                confidence="high",
                confidence_reason="test",
                label="Test Park",
                borough="Brooklyn",
            )
        }
        resolver = NYCLocationResolver(
            NYCLocationGazetteer(index), {}, allow_live_geosearch=False, geoclient=FakeGeoclient()
        )
        result = resolver.resolve(display_location="Test Park: Lawn", borough="Brooklyn")
        self.assertTrue(result.resolved)
        self.assertEqual(result.tier, "tier_1_gazetteer_display")

    def test_uncertified_street_segment_abstains_without_generic_fallback(self) -> None:
        resolver = NYCLocationResolver(
            NYCLocationGazetteer({}), {}, allow_live_geosearch=False, geoclient=FakeGeoclient()
        )
        queries: list[str] = []

        def fake_geosearch(self, query: str, borough: str | None = None):
            queries.append(query)
            return None

        resolver._resolve_geosearch = MethodType(fake_geosearch, resolver)
        result = resolver.resolve(
            display_location="Mystery Street between First Avenue and Second Avenue",
            borough="Brooklyn",
        )

        self.assertFalse(result.resolved)
        self.assertFalse(result.exact_pin_eligible)
        self.assertEqual(result.reason_code, "SEGMENT_UNCERTIFIED")
        self.assertEqual(queries, [])

    def test_event_923896_segment_uses_certified_brooklyn_reference(self) -> None:
        geoclient = FakeGeoclient()
        resolver = NYCLocationResolver(
            NYCLocationGazetteer({}), {}, allow_live_geosearch=False, geoclient=geoclient
        )
        result = resolver.resolve(
            display_location="East 74 Street between Avenue U and Avenue T",
            borough="Brooklyn",
        )

        self.assertTrue(result.resolved)
        self.assertTrue(result.exact_pin_eligible)
        self.assertEqual(result.validation_state, "validated")
        self.assertEqual(result.tier, "certified_street_segment")
        self.assertAlmostEqual(result.lat or 0.0, 40.618, places=3)
        self.assertAlmostEqual(result.lng or 0.0, -73.905, places=3)
        self.assertEqual(result.reason_code, "SEGMENT_CERTIFIED_REFERENCE")
        self.assertEqual(geoclient.calls, [])

    def test_segment_midpoint_requires_two_geoclient_endpoints(self) -> None:
        hits = {
            ("Main Street", "First Avenue", "Brooklyn"): {
                "lat": 40.6500,
                "lng": -73.9500,
                "geocoder_source": "nyc_geoclient_intersection",
                "geoclient_label": "Main Street and First Avenue",
            },
            ("Main Street", "Second Avenue", "Brooklyn"): {
                "lat": 40.6520,
                "lng": -73.9480,
                "geocoder_source": "nyc_geoclient_intersection",
                "geoclient_label": "Main Street and Second Avenue",
            },
        }
        resolver = NYCLocationResolver(
            NYCLocationGazetteer({}), {}, allow_live_geosearch=False, geoclient=FakeGeoclient(hits)
        )
        result = resolver.resolve(
            display_location="Main Street between First Avenue and Second Avenue",
            borough="Brooklyn",
        )

        self.assertTrue(result.resolved)
        self.assertTrue(result.exact_pin_eligible)
        self.assertEqual(result.tier, "certified_street_segment")
        self.assertEqual(result.source, "nyc_geoclient_segment_midpoint")
        self.assertEqual(result.reason_code, "SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED")
        self.assertEqual(result.validation_state, "validated")

    def test_one_geoclient_endpoint_is_not_enough(self) -> None:
        hits = {
            ("Main Street", "First Avenue", "Brooklyn"): {
                "lat": 40.6500,
                "lng": -73.9500,
                "geocoder_source": "nyc_geoclient_intersection",
            }
        }
        resolver = NYCLocationResolver(
            NYCLocationGazetteer({}), {}, allow_live_geosearch=False, geoclient=FakeGeoclient(hits)
        )
        result = resolver.resolve(
            display_location="Main Street between First Avenue and Second Avenue",
            borough="Brooklyn",
        )
        self.assertFalse(result.resolved)
        self.assertFalse(result.exact_pin_eligible)
        self.assertEqual(result.reason_code, "SEGMENT_UNCERTIFIED")

    def test_geoclient_wrong_borough_endpoint_is_rejected(self) -> None:
        hits = {
            ("Main Street", "First Avenue", "Brooklyn"): {
                "lat": 40.85,
                "lng": -73.92,
                "geocoder_source": "nyc_geoclient_intersection",
            },
            ("Main Street", "Second Avenue", "Brooklyn"): {
                "lat": 40.6520,
                "lng": -73.9480,
                "geocoder_source": "nyc_geoclient_intersection",
            },
        }
        resolver = NYCLocationResolver(
            NYCLocationGazetteer({}), {}, allow_live_geosearch=False, geoclient=FakeGeoclient(hits)
        )
        result = resolver.resolve(
            display_location="Main Street between First Avenue and Second Avenue",
            borough="Brooklyn",
        )
        self.assertFalse(result.resolved)
        self.assertEqual(result.reason_code, "SEGMENT_UNCERTIFIED")

    def test_geosearch_endpoints_cannot_self_certify_segment(self) -> None:
        resolver = NYCLocationResolver(
            NYCLocationGazetteer({}), {}, allow_live_geosearch=False, geoclient=FakeGeoclient()
        )
        calls = []

        def fake_geosearch(self, query: str, borough: str | None = None):
            calls.append(query)
            return ResolveResult(
                True,
                "tier_2_geosearch_cache",
                40.65,
                -73.95,
                "nyc_geosearch_planninglabs",
                "high",
                "candidate only",
                label=query,
            )

        resolver._resolve_geosearch = MethodType(fake_geosearch, resolver)
        result = resolver.resolve(
            display_location="Main Street between First Avenue and Second Avenue",
            borough="Brooklyn",
        )
        self.assertFalse(result.resolved)
        self.assertFalse(result.exact_pin_eligible)
        self.assertEqual(result.reason_code, "SEGMENT_UNCERTIFIED")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
