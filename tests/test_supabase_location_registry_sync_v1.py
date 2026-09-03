import copy
import unittest

from scripts.sync_supabase_location_registry_v1 import (
    REUSE_AUTHORITY,
    build_payload,
    duplicate_conflict_keys,
    prefer_location,
    registry_qa_pass,
    unique_registry_payload,
)


def event(state, certified, location, event_id, *, cemsid=None, dataset="fixture"):
    source = {"dataset": dataset, "source_event_id": event_id}
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


def dirty_conflict_payload():
    """Payload shaped like a single INSERT that Postgres ON CONFLICT would reject."""
    return {
        "schema_version": "NYCIF_LOCATION_REGISTRY_SYNC_V1",
        "locations": [
            {
                "location_id": "locv1:shared",
                "canonical_name": "Approx Place",
                "precision": "approximate",
                "location_authority": "projector_v3_approximate_recovery_v1",
                "review_required": True,
                "metadata": {"exact_pin_eligible": False},
            },
            {
                "location_id": "locv1:shared",
                "canonical_name": "Exact Place",
                "precision": "exact",
                "location_authority": "nyc_parks_official_facility_geometry",
                "review_required": False,
                "metadata": {"exact_pin_eligible": True},
            },
        ],
        "aliases": [
            {
                "location_id": "locv1:7d3fdba239d6a1c90a8d981a",
                "normalized_alias": "walter gladwin park walter gladwin park",
                "raw_alias": "Walter Gladwin Park, Walter Gladwin Park",
                "source_dataset": "nyc-citywide-events-calendar-api",
                "occurrence_count": 1,
            },
            {
                "location_id": "locv1:7d3fdba239d6a1c90a8d981a",
                "normalized_alias": "walter gladwin park walter gladwin park",
                "raw_alias": "Walter Gladwin Park: Walter Gladwin Park",
                "source_dataset": "tvpp-9vvx",
                "occurrence_count": 7,
            },
        ],
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

    def test_duplicate_conflict_keys_would_fail_on_conflict(self):
        dirty = dirty_conflict_payload()
        conflicts = duplicate_conflict_keys(dirty)
        self.assertTrue(conflicts["would_fail_on_conflict"])
        self.assertFalse(registry_qa_pass(dirty["locations"], dirty))
        self.assertEqual(conflicts["duplicate_location_ids"], ["locv1:shared"])
        self.assertEqual(conflicts["duplicate_location_id_extra_rows"], 1)
        self.assertEqual(conflicts["duplicate_alias_key_extra_rows"], 1)
        self.assertEqual(
            conflicts["duplicate_alias_keys"],
            [{
                "location_id": "locv1:7d3fdba239d6a1c90a8d981a",
                "normalized_alias": "walter gladwin park walter gladwin park",
                "count": 2,
            }],
        )

    def test_unique_payload_collapses_location_and_alias_conflict_keys(self):
        unique, stats = unique_registry_payload(dirty_conflict_payload())
        conflicts = duplicate_conflict_keys(unique)
        self.assertFalse(conflicts["would_fail_on_conflict"])
        self.assertEqual(stats["duplicate_location_id_rows_merged"], 1)
        self.assertEqual(stats["duplicate_alias_key_rows_merged"], 1)
        self.assertEqual([row["location_id"] for row in unique["locations"]], ["locv1:shared"])
        self.assertEqual(unique["locations"][0]["precision"], "exact")
        self.assertEqual(
            unique["locations"][0]["location_authority"],
            "nyc_parks_official_facility_geometry",
        )
        self.assertEqual(len(unique["aliases"]), 1)
        alias = unique["aliases"][0]
        self.assertEqual(alias["location_id"], "locv1:7d3fdba239d6a1c90a8d981a")
        self.assertEqual(alias["normalized_alias"], "walter gladwin park walter gladwin park")
        self.assertEqual(alias["occurrence_count"], 8)
        self.assertEqual(
            set(alias["metadata"]["merged_source_datasets"]),
            {"nyc-citywide-events-calendar-api", "tvpp-9vvx"},
        )
        loc_ids = [row["location_id"] for row in unique["locations"]]
        alias_keys = [(row["location_id"], row["normalized_alias"]) for row in unique["aliases"]]
        self.assertEqual(len(loc_ids), len(set(loc_ids)))
        self.assertEqual(len(alias_keys), len(set(alias_keys)))

    def test_build_payload_merges_cross_dataset_alias_conflict_keys(self):
        calendar = event(
            "GENERAL_AREA",
            False,
            "Walter Gladwin Park, Walter Gladwin Park",
            "1194376",
            dataset="nyc-citywide-events-calendar-api",
        )
        permit = event(
            "GENERAL_AREA",
            False,
            "Walter Gladwin Park: Walter Gladwin Park",
            "893398",
            dataset="tvpp-9vvx",
        )
        calendar["location_id"] = "locv1:7d3fdba239d6a1c90a8d981a"
        permit["location_id"] = "locv1:7d3fdba239d6a1c90a8d981a"
        calendar["nycif"]["location_id"] = "locv1:7d3fdba239d6a1c90a8d981a"
        permit["nycif"]["location_id"] = "locv1:7d3fdba239d6a1c90a8d981a"
        payload, report = build_payload([calendar, permit])
        conflicts = duplicate_conflict_keys(payload)
        self.assertFalse(conflicts["would_fail_on_conflict"])
        self.assertEqual(len(payload["locations"]), 1)
        self.assertEqual(len(payload["aliases"]), 1)
        self.assertEqual(payload["aliases"][0]["occurrence_count"], 2)
        self.assertEqual(report["duplicate_alias_key_rows_merged"], 1)
        self.assertEqual(report["duplicate_location_id_rows_merged"], 0)
        self.assertTrue(report["locations_unique_on_location_id"])
        self.assertTrue(report["aliases_unique_on_location_id_normalized_alias"])
        self.assertFalse(report["event_rows_modified"])
        self.assertTrue(report["qa_pass"])

    def test_prefer_location_keeps_real_authority_over_circular_reuse(self):
        existing = {
            "location_id": "locv1:shared",
            "precision": "exact",
            "location_authority": "nyc_parks_official_facility_geometry",
        }
        reused = {
            "location_id": "locv1:shared",
            "precision": "exact",
            "location_authority": REUSE_AUTHORITY,
        }
        kept = prefer_location(existing, reused)
        self.assertEqual(kept["location_authority"], "nyc_parks_official_facility_geometry")
        self.assertNotEqual(kept["location_authority"], REUSE_AUTHORITY)

    def test_qa_pass_fails_if_circular_reuse_authority_remains(self):
        row = event("MAP_READY", True, "Known Place", "11", cemsid="700")
        payload, report = build_payload([row])
        self.assertTrue(report["qa_pass"])
        tainted = copy.deepcopy(payload)
        tainted["locations"][0]["location_authority"] = REUSE_AUTHORITY
        self.assertFalse(registry_qa_pass(tainted["locations"], tainted))
        self.assertEqual(
            sum(1 for item in tainted["locations"] if item["location_authority"] == REUSE_AUTHORITY),
            1,
        )


if __name__ == "__main__":
    unittest.main()
