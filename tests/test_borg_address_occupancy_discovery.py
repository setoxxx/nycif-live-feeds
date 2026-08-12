from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs/contracts/BORG_ADDRESS_OCCUPANCY_DISCOVERY_V1.json"


class BorgAddressOccupancyDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_contract_identity_and_upstream_authority(self):
        c = self.contract
        self.assertEqual(c["contract"], "nycif.borg-address-occupancy-discovery.v1")
        self.assertEqual(c["principle"], "ADDRESS_IS_CLUSTER_NOT_IDENTITY")
        self.assertIn("nycif.address-occupancy-resolution.v1", c["upstream_authority"])

    def test_same_address_never_proves_duplicate_identity(self):
        rules = self.contract["same_address_rules"]
        self.assertFalse(rules["reject_second_business_because_address_already_seen"])
        self.assertFalse(rules["dedupe_by_address_only"])
        self.assertFalse(rules["dedupe_by_bbl_only"])
        self.assertFalse(rules["dedupe_by_bin_only"])
        self.assertFalse(rules["dedupe_by_owner_name"])
        self.assertTrue(rules["preserve_multiple_license_numbers"])
        self.assertTrue(rules["preserve_multiple_authoritative_entity_ids"])
        self.assertTrue(rules["preserve_historical_business_turnover"])

    def test_authoritative_identity_keys_and_relationship_states_are_preserved(self):
        resolution = self.contract["entity_resolution"]
        strong = set(resolution["strong_keys"])
        weak = set(resolution["weak_keys_never_sufficient_alone"])
        self.assertIn("authoritative business/entity identifier", strong)
        self.assertIn("license/permit identifier", strong)
        self.assertIn("CAMIS or equivalent permit identity", strong)
        self.assertIn("same address", weak)
        self.assertIn("similar DBA", weak)
        states = set(self.contract["terminal_states"])
        for expected in {
            "CANONICAL_MATCH",
            "NEW_ENTITY_CANDIDATE",
            "SAME_ENTITY_ALIAS_CANDIDATE",
            "SUCCESSOR_PREDECESSOR_REVIEW",
            "UNRELATED_COLOCATED",
            "SUBPREMISE_REVIEW_REQUIRED",
            "HISTORICAL_OR_CLOSED",
            "SOURCE_CONFLICT_REVIEW_REQUIRED",
            "OUT_OF_SCOPE",
        }:
            self.assertIn(expected, states)

    def test_zero_silent_loss_and_privacy_boundaries(self):
        self.assertTrue(self.contract["accounting"]["every_input_record_gets_terminal_state"])
        self.assertFalse(self.contract["accounting"]["silent_loss_allowed"])
        privacy = self.contract["privacy"]
        self.assertFalse(privacy["build_private_household_or_resident_profiles"])
        self.assertFalse(privacy["track_people_at_residential_units"])
        self.assertFalse(privacy["track_help_seeker_or_immigration_status"])
        owner = self.contract["property_owner_rules"]
        self.assertFalse(owner["mappluto_owner_name_is_business_owner"])
        self.assertFalse(owner["mappluto_owner_name_is_resident"])
        self.assertFalse(owner["owner_name_may_create_culture_identity"])


if __name__ == "__main__":
    unittest.main()
