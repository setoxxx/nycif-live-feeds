from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.borg_adaptive_dataset_topology import interpret_dataset


REGISTRY_PATH = Path("docs/contracts/BORG_DATASET_RECIPE_REGISTRY_V1.json")


class BorgAdaptiveDatasetTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY_PATH.read_text())
        cls.provenance = {"source": "test"}

    def test_unknown_schema_isolated_for_review(self):
        payload = {"contract": "unknown.v1", "records": [{"foo": 1, "bar": 2}]}
        result = interpret_dataset(
            payload=payload,
            registry=self.registry,
            source_id="unknown-source",
            snapshot_id="snap-1",
            authority_class="UNKNOWN",
            sensitivity_class="UNKNOWN",
            provenance=self.provenance,
        )
        self.assertEqual(result["interpretation_state"], "REVIEW_REQUIRED")
        self.assertEqual(result["topology"]["nodes"], [])
        self.assertEqual(result["learning_observation"]["candidate_recipe_action"], "REVIEW_NEW_SCHEMA")

    def test_base_geography_projects_stable_topology_node(self):
        payload = {
            "contract": "nycif.culture-base-geography.v1",
            "records": [{"nta2020": "BK1802", "nta_name": "Marine Park-Mill Basin-Bergen Beach", "geometry": {"type": "Polygon", "coordinates": []}}],
        }
        result = interpret_dataset(
            payload=payload,
            registry=self.registry,
            source_id="dcp-nta",
            snapshot_id="26B",
            authority_class="AUTHORITATIVE_GEOGRAPHY",
            sensitivity_class="PUBLIC_RECORD",
            provenance=self.provenance,
        )
        self.assertEqual(result["interpretation_state"], "RECOGNIZED")
        self.assertEqual(result["topology"]["nodes"][0]["node_id"], "BASE_GEOGRAPHY:BK1802")
        self.assertEqual(result["topology"]["edges"], [])

    def test_demographic_profile_links_to_base_without_culture_power(self):
        payload = {
            "contract": "nycif.community-demographic-profile.v1",
            "records": [{"nta2020": "BK1802", "profile_state": "READY", "culture_classification_power": "NONE", "metrics": []}],
        }
        result = interpret_dataset(
            payload=payload,
            registry=self.registry,
            source_id="acs-2024",
            snapshot_id="2024-5yr",
            authority_class="AUTHORITATIVE_AGGREGATE_STATISTICS",
            sensitivity_class="PUBLIC_AGGREGATE",
            provenance=self.provenance,
        )
        node = result["topology"]["nodes"][0]
        edge = result["topology"]["edges"][0]
        self.assertEqual(node["node_type"], "COMMUNITY_PROFILE")
        self.assertEqual(edge["edge_type"], "PROFILE_OF")
        self.assertEqual(edge["target_node_id"], "BASE_GEOGRAPHY:BK1802")
        self.assertEqual(result["learning_observation"]["candidate_recipe_action"], "REUSE_EXISTING")

    def test_authority_mismatch_warns_instead_of_self_promoting(self):
        payload = {"contract": "nycif.community-language-profile.v1", "records": [{"nta2020": "BK1802", "metrics": []}]}
        result = interpret_dataset(
            payload=payload,
            registry=self.registry,
            source_id="bad-authority",
            snapshot_id="snap",
            authority_class="SUPPORTING_ASSERTION",
            sensitivity_class="PUBLIC_RECORD",
            provenance=self.provenance,
        )
        self.assertEqual(result["interpretation_state"], "RECOGNIZED_WITH_WARNINGS")
        self.assertIn("AUTHORITY_CLASS_MISMATCH", result["learning_observation"]["warnings"])
        self.assertEqual(result["learning_observation"]["candidate_recipe_action"], "REVIEW_RECIPE_UPDATE")


if __name__ == "__main__":
    unittest.main()
