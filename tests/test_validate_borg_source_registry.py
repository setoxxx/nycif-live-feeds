from __future__ import annotations

import copy
import unittest

from scripts.validate_borg_source_registry import validate_registry


def active_source():
    return {
        "source_id": "nyc-official-test",
        "provider": "NYC Test Agency",
        "source_tier": "A",
        "authority_class": "OFFICIAL_OBSERVATION",
        "jurisdiction": "NYC",
        "source_type": "API",
        "canonical_url": "https://example.nyc.gov/api",
        "authentication_mode": "NONE",
        "cadence": "hourly",
        "freshness_sla_hours": 2,
        "native_id_strategy": "source_event_id",
        "schema_fingerprint": "abc123",
        "parser_version": "v1",
        "rights": {
            "retrieval_allowed": True,
            "retention_allowed": True,
            "transformation_allowed": True,
            "public_projection_allowed": True,
            "attribution_required": True,
            "review_state": "APPROVED",
        },
        "network_scope": "PUBLIC",
        "pagination": {
            "mode": "OFFSET_LIMIT",
            "deterministic_ordering": True,
            "exhaustion_or_total_parity_required": True,
        },
        "retry_policy": {
            "max_attempts": 4,
            "backoff": "BOUNDED_EXPONENTIAL",
            "retryable_status_classes": ["429", "5XX"],
        },
        "health": "HEALTHY",
        "provenance": {"registered_by": "test"},
        "registration_state": "ACTIVE",
    }


class BorgSourceRegistryValidatorTests(unittest.TestCase):
    def test_valid_active_source_passes_and_accounts(self):
        result = validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [active_source()]})
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["active_count"], 1)
        self.assertTrue(result["zero_silent_loss"])

    def test_duplicate_source_id_fails(self):
        source = active_source()
        with self.assertRaises(ValueError):
            validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source, copy.deepcopy(source)]})

    def test_active_unknown_rights_or_network_fails(self):
        source = active_source()
        source["rights"]["review_state"] = "REVIEW_REQUIRED"
        with self.assertRaises(ValueError):
            validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})
        source = active_source()
        source["network_scope"] = "LOOPBACK"
        with self.assertRaises(ValueError):
            validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})

    def test_active_paginated_source_requires_deterministic_exhaustion(self):
        source = active_source()
        source["pagination"]["deterministic_ordering"] = False
        with self.assertRaises(ValueError):
            validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})
        source = active_source()
        source["pagination"]["exhaustion_or_total_parity_required"] = False
        with self.assertRaises(ValueError):
            validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})

    def test_tier_d_cannot_independently_enable_public_projection(self):
        source = active_source()
        source["source_tier"] = "D"
        source["authority_class"] = "DISCOVERY_ONLY"
        with self.assertRaises(ValueError):
            validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})
        source["rights"]["public_projection_allowed"] = False
        result = validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})
        self.assertEqual(result["active_count"], 1)

    def test_non_active_review_record_may_preserve_unknown_semantics(self):
        source = active_source()
        source["registration_state"] = "REVIEW_REQUIRED"
        source["authentication_mode"] = "UNKNOWN"
        source["network_scope"] = "UNKNOWN"
        source["health"] = "UNKNOWN"
        source["pagination"]["mode"] = "UNKNOWN"
        source["pagination"]["deterministic_ordering"] = False
        source["pagination"]["exhaustion_or_total_parity_required"] = False
        source["rights"]["retrieval_allowed"] = False
        source["rights"]["review_state"] = "REVIEW_REQUIRED"
        result = validate_registry({"contract": "nycif.borg-source-registry.v1", "records": [source]})
        self.assertEqual(result["registration_state_accounting"]["REVIEW_REQUIRED"], 1)


if __name__ == "__main__":
    unittest.main()
