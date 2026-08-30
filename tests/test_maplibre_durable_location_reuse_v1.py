import unittest

from scripts import build_maplibre_reader_safe_with_approx_v1 as wrapper


class MapLibreDurableLocationReuseTests(unittest.TestCase):
    def exact_event(self, authority="durable_location_registry_v1"):
        return {
            "id": "fixture",
            "title": "Fixture",
            "event_role": "public_event",
            "parent_event_id": None,
            "borough": "Brooklyn",
            "latitude": 40.65,
            "longitude": -73.95,
            "location": "Known Place",
            "source": {"dataset": "fixture", "source_event_id": "1"},
            "start_date_time": "2026-08-30T12:00:00-04:00",
            "location_evidence": {
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": "durable_registry:known",
            },
            "nycif": {
                "map_eligibility_state": "MAP_READY",
                "certified_pin": True,
                "location_authority": authority,
                "display_disposition": "standalone_public_event",
            },
        }

    def test_durable_exact_authority_passes_existing_marker_contract(self):
        eligible, reason = wrapper.reader.marker_eligibility(self.exact_event())
        self.assertTrue(eligible)
        self.assertEqual(reason, "marker_ready_durable_reuse")

    def test_durable_authority_does_not_bypass_evidence_gate(self):
        event = self.exact_event()
        event["location_evidence"]["exact_pin_eligible"] = False
        eligible, reason = wrapper.reader.marker_eligibility(event)
        self.assertFalse(eligible)
        self.assertEqual(reason, "location_evidence_not_validated")

    def test_feature_preserves_durable_authority(self):
        feature = wrapper.reader.feature(self.exact_event(), exact_marker=True)
        self.assertEqual(feature["properties"]["location_authority"], "durable_location_registry_v1")


if __name__ == "__main__":
    unittest.main()
