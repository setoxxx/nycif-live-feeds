from __future__ import annotations

import copy
import unittest

from scripts.build_street_segment_route_occurrence_registry_v9 import audit


CLAIM = "brooklyn|test street between first avenue and second avenue"


def reports():
    v2 = {
        "schema_version": "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2",
        "publication_authority_granted": False,
        "projector_consumed": False,
        "today_nyc": "2026-08-14",
        "claims": [{
            "claim_key": CLAIM,
            "strict_nonpublic_segment_evidence": True,
            "occurrence_count": 2,
            "source_event_ids": ["100", "100"],
        }],
    }
    v5 = {
        "schema_version": "NYCIF_STREET_SEGMENT_GEOSUPPORT_3S_ROUTE_AUDIT_V5",
        "publication_authority_granted": False,
        "projector_consumed": False,
        "routes": [{
            "claim_key": CLAIM,
            "route_topology_certified": True,
            "occurrence_count": 2,
            "source_event_ids": ["100", "100"],
        }],
    }
    v7 = {
        "schema_version": "NYCIF_STREET_SEGMENT_ROUTE_GEOMETRY_BUNDLE_AUDIT_V7",
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "routes": [{
            "claim_key": CLAIM,
            "route_geometry_bundle_certified": True,
            "occurrence_count": 2,
            "route_bundle_sha256": "a" * 64,
        }],
    }
    v8 = {
        "schema_version": "NYCIF_STREET_SEGMENT_ROUTE_EVIDENCE_CONTRACT_AUDIT_V8",
        "contract_conformance_pass": True,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "promotion_allowed": False,
        "routes": [{"claim_key": CLAIM, "contract_conformant": True}],
    }
    return v2, v5, v7, v8


def raw(start: str, event_id: str = "100"):
    return {
        "source_dataset": "nyc-open-data-permitted-events",
        "event_id": event_id,
        "start_date_time": start,
        "event_borough": "Brooklyn",
        "event_location": "TEST STREET between FIRST AVENUE and SECOND AVENUE",
    }


class RouteOccurrenceRegistryV9Tests(unittest.TestCase):
    def test_recurring_source_id_with_distinct_exact_starts_is_valid(self):
        v2, v5, v7, v8 = reports()
        result = audit(
            v2=v2, v5=v5, v7=v7, v8=v8,
            raw_rows=[raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00")],
        )
        self.assertTrue(result["registry_conformance_pass"])
        self.assertEqual(result["registry_occurrence_count"], 2)
        self.assertEqual(result["unique_occurrence_key_v2_count"], 2)
        self.assertEqual(result["unique_source_event_id_count"], 1)
        self.assertEqual(result["recurring_source_event_id_count"], 1)
        self.assertEqual(result["exact_start_occurrence_count"], 2)
        self.assertTrue(all(value == 0 for value in result["hard_zero_gates"].values()))

    def test_missing_dataset_restores_tvpp_provenance(self):
        v2, v5, v7, v8 = reports()
        rows = [raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00")]
        for row in rows:
            row.pop("source_dataset")
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertTrue(result["registry_conformance_pass"])
        self.assertEqual(result["source_dataset_authority"], "tvpp-9vvx")
        self.assertEqual({entry["source_dataset"] for entry in result["registry"]}, {"tvpp-9vvx"})

    def test_explicit_dataset_is_not_rewritten(self):
        v2, v5, v7, v8 = reports()
        result = audit(
            v2=v2, v5=v5, v7=v7, v8=v8,
            raw_rows=[raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00")],
        )
        self.assertEqual(
            {entry["source_dataset"] for entry in result["registry"]},
            {"nyc-open-data-permitted-events"},
        )

    def test_duplicate_same_start_occurrence_blocks(self):
        v2, v5, v7, v8 = reports()
        rows = [raw("2026-09-01T10:00:00"), raw("2026-09-01T10:00:00")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertFalse(result["registry_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["duplicate_occurrence_key_count"], 1)

    def test_unparseable_start_fails_at_same_current_future_filter_as_v2(self):
        v2, v5, v7, v8 = reports()
        rows = [raw("2026-09-01T10:00:00"), raw("not-a-date")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertFalse(result["registry_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["raw_claim_occurrence_count_mismatch_count"], 1)
        self.assertEqual(result["hard_zero_gates"]["ambiguous_occurrence_identity_count"], 0)
        self.assertEqual(result["hard_zero_gates"]["silent_occurrence_identity_loss_count"], 2)

    def test_date_only_occurrences_retain_day_precision_without_invention(self):
        v2, v5, v7, v8 = reports()
        rows = [raw("2026-09-01"), raw("2026-09-08")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertTrue(result["registry_conformance_pass"])
        self.assertEqual(result["exact_start_occurrence_count"], 0)
        self.assertEqual(result["day_precision_occurrence_count"], 2)
        self.assertEqual(result["unique_occurrence_key_v2_count"], 2)

    def test_raw_source_id_multiset_drift_blocks(self):
        v2, v5, v7, v8 = reports()
        rows = [raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00", event_id="999")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertFalse(result["registry_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["raw_source_event_id_multiset_mismatch_count"], 1)

    def test_v2_v5_source_id_multiset_drift_blocks(self):
        v2, v5, v7, v8 = reports()
        v5["routes"][0]["source_event_ids"] = ["100", "999"]
        rows = [raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertFalse(result["registry_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["source_event_id_multiset_mismatch_count"], 1)

    def test_route_bundle_hash_missing_blocks(self):
        v2, v5, v7, v8 = reports()
        v7["routes"][0]["route_bundle_sha256"] = ""
        rows = [raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertFalse(result["registry_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["route_bundle_hash_missing_count"], 1)

    def test_duplicate_v7_claim_handoff_blocks(self):
        v2, v5, v7, v8 = reports()
        v7["routes"].append(copy.deepcopy(v7["routes"][0]))
        rows = [raw("2026-09-01T10:00:00"), raw("2026-09-08T10:00:00")]
        result = audit(v2=v2, v5=v5, v7=v7, v8=v8, raw_rows=rows)
        self.assertFalse(result["registry_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["v7_claim_handoff_not_unique_count"], 1)


if __name__ == "__main__":
    unittest.main()
