import unittest

from scripts.sync_supabase_location_registry_v1 import build_payload


def event(state, certified, location, event_id, *, cemsid=None):
    source = {"dataset": "fixture", "source_event_id": event_id}
    if cemsid:
        source["source_cemsid"] = cemsid
    return {
        "title": f"Event {event_id}",
        "start_date_time": "2026-08-30T18:00:00-04:00",
        "event_location": location,
        "borough": "Brooklyn",
        "latitude": 40.65,
        "longitude": -73.95,
        "source": source,
        "nycif": {
            "map_eligibility_state": state,
            "certified_pin": certified,
            "location_authority": "fixture-authority",
        },
    }


class LocationRegistrySyncTests(unittest.TestCase):
    def test_exact_and_approximate_remain_separate_precision(self):
        payload, report = build_payload([
            event("MAP_READY", True, "Exact Place", "1", cemsid="100"),
            event("GENERAL_AREA", False, "Approx Place", "2", cemsid="200"),
        ])
        by_id = {row["location_id"]: row for row in payload["locations"]}
        self.assertEqual(by_id["cems:100"]["precision"], "exact")
        self.assertFalse(by_id["cems:100"]["review_required"])
        self.assertEqual(by_id["cems:200"]["precision"], "approximate")
        self.assertTrue(by_id["cems:200"]["review_required"])
        self.assertEqual(report["approximate_certified_count"], 0)
        self.assertTrue(report["qa_pass"])

    def test_approximate_certification_contradiction_is_skipped(self):
        payload, report = build_payload([event("GENERAL_AREA", True, "Bad Approx", "3")])
        self.assertEqual(payload["locations"], [])
        self.assertEqual(report["skipped_counts"]["approximate_certification_contradiction"], 1)

    def test_list_only_does_not_enter_registry(self):
        payload, report = build_payload([event("LIST_ONLY", False, "Unknown", "4")])
        self.assertEqual(payload["locations"], [])
        self.assertEqual(report["skipped_counts"]["not_geography_assigned"], 1)

    def test_deterministic_signature_is_stable(self):
        first, _ = build_payload([event("GENERAL_AREA", False, "Named Place", "5")])
        second, _ = build_payload([event("GENERAL_AREA", False, "Named Place", "5")])
        self.assertEqual(first["locations"][0]["location_id"], second["locations"][0]["location_id"])

    def test_aliases_are_dataset_scoped(self):
        payload, _ = build_payload([
            event("MAP_READY", True, "Same Place", "6", cemsid="300"),
            event("MAP_READY", True, "Same Place", "7", cemsid="300"),
        ])
        self.assertEqual(len(payload["aliases"]), 1)
        self.assertEqual(payload["aliases"][0]["occurrence_count"], 2)

    def test_reused_location_preserves_original_authority(self):
        row = event("MAP_READY", True, "Known Place", "8", cemsid="400")
        row["location_id"] = "cems:400"
        row["nycif"].update({
            "location_id": "cems:400",
            "location_authority": "durable_location_registry_v1",
            "location_reuse_source_authority": "nyc_parks_official_facility_geometry",
        })
        payload, report = build_payload([row])
        stored = payload["locations"][0]
        self.assertEqual(stored["location_authority"], "nyc_parks_official_facility_geometry")
        self.assertEqual(stored["metadata"]["observed_location_authority"], "durable_location_registry_v1")
        self.assertTrue(stored["metadata"]["reused_from_registry"])
        self.assertEqual(report["circular_reuse_authority_count"], 0)
        self.assertFalse(report["event_rows_modified"])
        self.assertTrue(report["qa_pass"])

    def test_reused_location_without_original_authority_is_skipped(self):
        provenanced = event("MAP_READY", True, "Known Place", "8", cemsid="400")
        provenanced["location_id"] = "cems:400"
        provenanced["nycif"].update({
            "location_id": "cems:400",
            "location_authority": "durable_location_registry_v1",
            "location_reuse_source_authority": "nyc_parks_official_facility_geometry",
        })
        unprovenanced = event("MAP_READY", True, "Unknown Place", "9", cemsid="500")
        unprovenanced["location_id"] = "cems:500"
        unprovenanced["nycif"].update({
            "location_id": "cems:500",
            "location_authority": "durable_location_registry_v1",
        })
        circular = event("GENERAL_AREA", False, "Circular Place", "10", cemsid="600")
        circular["location_id"] = "cems:600"
        circular["nycif"].update({
            "location_id": "cems:600",
            "location_authority": "durable_location_registry_v1",
            "location_reuse_source_authority": "durable_location_registry_v1",
        })
        payload, report = build_payload([provenanced, unprovenanced, circular])
        self.assertEqual([row["location_id"] for row in payload["locations"]], ["cems:400"])
        self.assertEqual(payload["locations"][0]["location_authority"], "nyc_parks_official_facility_geometry")
        self.assertEqual(report["skipped_counts"]["reused_location_missing_source_authority"], 2)
        self.assertEqual(report["circular_reuse_authority_count"], 0)
        self.assertFalse(report["event_rows_modified"])
        self.assertTrue(report["qa_pass"])


if __name__ == "__main__":
    unittest.main()
