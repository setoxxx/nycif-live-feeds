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
        self.assertEqual(report["exact_reused_count"], 1)
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
        self.assertEqual(report["approximate_reused_count"], 1)

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
        self.assertEqual(report["exact_reused_count"], 1)


if __name__ == "__main__":
    unittest.main()
