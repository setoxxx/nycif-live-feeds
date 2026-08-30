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


if __name__ == "__main__":
    unittest.main()
