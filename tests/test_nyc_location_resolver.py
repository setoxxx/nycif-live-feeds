"""Tests for tiered NYC location resolver."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.nyc_location_gazetteer import NYCLocationGazetteer, build_gazetteer_index, gazetteer_entry
from scripts.nyc_location_resolver import NYCLocationResolver


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
        resolver = NYCLocationResolver(NYCLocationGazetteer(index), {}, allow_live_geosearch=False)
        result = resolver.resolve(display_location="Test Park: Lawn", borough="Brooklyn")
        self.assertTrue(result.resolved)
        self.assertEqual(result.tier, "tier_1_gazetteer_display")


if __name__ == "__main__":
    unittest.main()
