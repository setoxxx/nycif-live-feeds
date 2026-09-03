import json
import tempfile
import unittest
from pathlib import Path

from scripts.apply_durable_location_reuse_v1 import apply


def event(location: str, *, dataset: str = "fixture", borough: str = "Brooklyn"):
    return {
        "title": "Fixture Event",
        "event_role": "public_event",
        "parent_event_id": None,
        "location": location,
        "borough": borough,
        "latitude": None,
        "longitude": None,
        "source": {"dataset": dataset, "source_event_id": "evt-1"},
        "nycif": {
            "source_location_text": location,
            "display_disposition": "list_only",
            "map_eligibility_state": "LIST_ONLY",
            "certified_pin": False,
            "location_authority": "projector_v3_semantic_map_decision",
        },
    }


def registry(locations, aliases):
    return {
        "schema_version": "NYCIF_LOCATION_REGISTRY_RUNTIME_V1",
        "location_count": len(locations),
        "alias_count": len(aliases),
        "locations": locations,
        "aliases": aliases,
    }


def location(location_id: str, precision: str, *, borough: str = "Brooklyn"):
    return {
        "location_id": location_id,
        "borough": borough,
        "canonical_name": "Fixture Place",
        "canonical_full_name": "Fixture Place",
        "latitude": 40.65,
        "longitude": -73.95,
        "precision": precision,
        "location_authority": "fixture_authority",
        "confidence": 1,
        "review_required": precision != "exact",
    }


def alias(location_id: str, raw: str, *, dataset: str = "fixture"):
    return {
        "location_id": location_id,
        "raw_alias": raw,
        "normalized_alias": raw.lower(),
        "source_dataset": dataset,
        "occurrence_count": 1,
    }


class DurableLocationReuseTests(unittest.TestCase):
    def run_apply(self, events, registry_payload):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            canonical = root / "canonical.json"
            registry_path = root / "registry.json"
            report = root / "report.json"
            canonical.write_text(json.dumps(events), encoding="utf-8")
            registry_path.write_text(json.dumps(registry_payload), encoding="utf-8")
            result = apply(canonical, registry_path, report)
            output = json.loads(canonical.read_text(encoding="utf-8"))
            return output, result

    def test_exact_registry_location_reuses_certified_pin(self):
        output, report = self.run_apply(
            [event("Marine Park: Cricket-03")],
            registry(
                [location("parks:marine:cricket-03", "exact")],
                [alias("parks:marine:cricket-03", "Marine Park: Cricket-03")],
            ),
        )
        row = output[0]
        self.assertEqual(row["location_id"], "parks:marine:cricket-03")
        self.assertEqual(row["nycif"]["map_eligibility_state"], "MAP_READY")
        self.assertTrue(row["nycif"]["certified_pin"])
        self.assertTrue(row["location_evidence"]["exact_pin_eligible"])
        self.assertEqual(row["nycif"]["location_reuse_source_authority"], "fixture_authority")
        self.assertEqual(report["exact_reused_count"], 1)
        self.assertEqual(report["missing_source_authority_reused_count"], 0)
        self.assertTrue(report["qa_pass"])

    def test_approximate_registry_location_never_promotes_exact(self):
        output, report = self.run_apply(
            [event("Claremont Park: Picnic / BBQ #1")],
            registry(
                [location("parks:claremont:bbq-1", "approximate")],
                [alias("parks:claremont:bbq-1", "Claremont Park: Picnic / BBQ #1")],
            ),
        )
        row = output[0]
        self.assertEqual(row["nycif"]["map_eligibility_state"], "GENERAL_AREA")
        self.assertFalse(row["nycif"]["certified_pin"])
        self.assertFalse(row["location_evidence"]["exact_pin_eligible"])
        self.assertEqual(row["nycif"]["location_reuse_source_authority"], "fixture_authority")
        self.assertEqual(report["approximate_reused_count"], 1)
        self.assertEqual(report["missing_source_authority_reused_count"], 0)

    def test_ambiguous_alias_fails_closed(self):
        output, report = self.run_apply(
            [event("Same Park: Field 1")],
            registry(
                [location("a", "exact"), location("b", "exact")],
                [alias("a", "Same Park: Field 1"), alias("b", "Same Park: Field 1")],
            ),
        )
        row = output[0]
        self.assertIsNone(row["latitude"])
        self.assertIsNone(row["longitude"])
        self.assertEqual(row["nycif"]["map_eligibility_state"], "LIST_ONLY")
        self.assertEqual(report["total_reused_count"], 0)
        self.assertEqual(report["ambiguous_promotions"], 0)

    def test_street_route_claim_is_never_reused_as_point(self):
        output, report = self.run_apply(
            [event("Main Street between First Avenue and Second Avenue")],
            registry(
                [location("route-like-point", "exact")],
                [alias("route-like-point", "Main Street between First Avenue and Second Avenue")],
            ),
        )
        self.assertIsNone(output[0]["latitude"])
        self.assertEqual(report["total_reused_count"], 0)
        self.assertEqual(report["skipped_counts"]["street_route_claim"], 1)

    def test_unique_borough_alias_can_bridge_source_dataset(self):
        output, report = self.run_apply(
            [event("Known Place", dataset="new-feed")],
            registry(
                [location("known", "exact")],
                [alias("known", "Known Place", dataset="old-feed")],
            ),
        )
        self.assertEqual(output[0]["location_id"], "known")
        self.assertEqual(output[0]["nycif"]["location_reuse_match_basis"], "borough_alias")
        self.assertEqual(output[0]["nycif"]["location_reuse_source_authority"], "fixture_authority")
        self.assertEqual(report["exact_reused_count"], 1)

    def test_circular_stored_authority_is_not_stamped_on_exact_or_approximate_reuse(self):
        exact_loc = location("exact-circular", "exact")
        exact_loc["location_authority"] = "durable_location_registry_v1"
        approx_loc = location("approx-circular", "approximate")
        approx_loc["location_authority"] = "durable_location_registry_v1"
        missing_loc = location("exact-missing", "exact")
        missing_loc["location_authority"] = None
        output, report = self.run_apply(
            [
                event("Exact Circular Place"),
                event("Approx Circular Place"),
                event("Exact Missing Place"),
            ],
            registry(
                [exact_loc, approx_loc, missing_loc],
                [
                    alias("exact-circular", "Exact Circular Place"),
                    alias("approx-circular", "Approx Circular Place"),
                    alias("exact-missing", "Exact Missing Place"),
                ],
            ),
        )
        exact_row, approx_row, missing_row = output
        self.assertEqual(exact_row["nycif"]["map_eligibility_state"], "MAP_READY")
        self.assertTrue(exact_row["nycif"]["certified_pin"])
        self.assertNotIn("location_reuse_source_authority", exact_row["nycif"])
        self.assertEqual(approx_row["nycif"]["map_eligibility_state"], "GENERAL_AREA")
        self.assertFalse(approx_row["nycif"]["certified_pin"])
        self.assertNotIn("location_reuse_source_authority", approx_row["nycif"])
        self.assertEqual(missing_row["nycif"]["map_eligibility_state"], "MAP_READY")
        self.assertNotIn("location_reuse_source_authority", missing_row["nycif"])
        self.assertEqual(report["exact_reused_count"], 2)
        self.assertEqual(report["approximate_reused_count"], 1)
        self.assertEqual(report["missing_source_authority_reused_count"], 3)
        self.assertTrue(report["qa_pass"])

    def test_unwraps_original_authority_from_stored_metadata_when_column_is_circular(self):
        stored = location("known", "exact")
        stored["location_authority"] = "durable_location_registry_v1"
        stored["metadata"] = {"original_location_authority": "nyc_parks_official_facility_geometry"}
        output, report = self.run_apply(
            [event("Known Place")],
            registry([stored], [alias("known", "Known Place")]),
        )
        self.assertEqual(
            output[0]["nycif"]["location_reuse_source_authority"],
            "nyc_parks_official_facility_geometry",
        )
        self.assertEqual(report["missing_source_authority_reused_count"], 0)
        self.assertEqual(report["exact_reused_count"], 1)


if __name__ == "__main__":
    unittest.main()
