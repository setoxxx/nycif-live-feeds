import unittest

from scripts.build_semantic_live_intake import authoritative_match_for_raw


class FakeSegmentResult:
    resolved = True
    tier = "certified_street_segment"

    def as_match_dict(self):
        return {
            "lat": 40.651,
            "lng": -73.949,
            "display_location": "Main Street between First Avenue and Second Avenue",
            "geocoder_source": "nyc_geoclient_segment_midpoint",
            "geocoder_confidence": "high",
            "resolver_tier": "certified_street_segment",
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "reason_code": "SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED",
        }


class FakeResolver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def _resolve_street_segment(self, display, borough):
        self.calls.append((display, borough))
        return self.result


class SemanticIntakeSegmentAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "event_id": "123",
            "event_borough": "Brooklyn",
            "event_location": "Main Street between First Avenue and Second Avenue",
        }
        self.indexes = {"event_id": {}, "cemsid": {}, "text": {}}
        self.bad_legacy_cache = {
            "event_id:123": {
                "lat": 40.70,
                "lng": -73.90,
                "borough": "Brooklyn",
                "display_location": self.raw["event_location"],
                "source": "existing_enriched_feed_gps",
            }
        }

    def test_segment_bypasses_legacy_cache_and_uses_authority(self):
        resolver = FakeResolver(FakeSegmentResult())
        match_type, match, route = authoritative_match_for_raw(
            self.raw,
            self.indexes,
            self.bad_legacy_cache,
            resolver,
        )
        self.assertEqual(route, "street_segment_authority")
        self.assertEqual(match_type, "certified_street_segment")
        self.assertEqual(match["geocoder_source"], "nyc_geoclient_segment_midpoint")
        self.assertEqual(match["lat"], 40.651)
        self.assertNotEqual(match["lat"], self.bad_legacy_cache["event_id:123"]["lat"])
        self.assertEqual(len(resolver.calls), 1)

    def test_unresolved_segment_does_not_fall_back_to_legacy_coordinate(self):
        resolver = FakeResolver(None)
        match_type, match, route = authoritative_match_for_raw(
            self.raw,
            self.indexes,
            self.bad_legacy_cache,
            resolver,
        )
        self.assertEqual(route, "street_segment_authority")
        self.assertEqual(match_type, "street_segment_unresolved")
        self.assertIsNone(match)
        self.assertEqual(len(resolver.calls), 1)


if __name__ == "__main__":
    unittest.main()
