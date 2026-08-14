from __future__ import annotations

import unittest

from scripts.audit_street_segment_geosupport_evidence_contract_v3 import audit


CONTRACT = {
    "artifact_type": "nycif_exact_event_street_segment_evidence_contract_v1",
    "status": "recovery_evidence_only",
    "scope": {
        "publication_authority_granted": False,
        "projector_consumption_enabled": False,
        "official_centerline_geometry_join_completed": False,
    },
    "required_strict_entry_fields": [
        "claim_key", "borough", "event_location", "occurrence_count", "source_event_ids",
        "strict_nonpublic_segment_evidence", "reason_code", "evidence_class",
        "publication_state", "publication_allowed", "exact_pin_eligible",
        "projector_consumed", "endpoint_1", "endpoint_2", "function_3_from_node",
        "function_3_to_node", "function_3_segment_identifier", "distance_m",
        "candidate_midpoint",
    ],
    "required_endpoint_fields": ["node", "latitude", "longitude", "main_street", "cross_street"],
    "required_strict_values": {
        "strict_nonpublic_segment_evidence": True,
        "reason_code": "GEOSUPPORT_ENDPOINTS_SEGMENT_IDENTITY_AGREE",
        "evidence_class": "NYC_PLANNING_GEOSUPPORT_STREET_SEGMENT_NONPUBLIC",
        "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
        "publication_allowed": False,
        "exact_pin_eligible": False,
        "projector_consumed": False,
    },
}


def strict_entry(segment_id: str = "1234567"):
    return {
        "claim_key": "bk|main between a and b",
        "borough": "Brooklyn",
        "event_location": "MAIN STREET between A STREET and B STREET",
        "occurrence_count": 2,
        "source_event_ids": ["1", "2"],
        "strict_nonpublic_segment_evidence": True,
        "reason_code": "GEOSUPPORT_ENDPOINTS_SEGMENT_IDENTITY_AGREE",
        "evidence_class": "NYC_PLANNING_GEOSUPPORT_STREET_SEGMENT_NONPUBLIC",
        "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
        "publication_allowed": False,
        "exact_pin_eligible": False,
        "projector_consumed": False,
        "endpoint_1": {"node": "0000001", "latitude": 40.6, "longitude": -73.9, "main_street": "MAIN STREET", "cross_street": "A STREET"},
        "endpoint_2": {"node": "0000002", "latitude": 40.601, "longitude": -73.899, "main_street": "MAIN STREET", "cross_street": "B STREET"},
        "function_3_from_node": "0000001",
        "function_3_to_node": "0000002",
        "function_3_segment_identifier": segment_id,
        "distance_m": 120.0,
        "candidate_midpoint": {"latitude": 40.6005, "longitude": -73.8995, "generated_for_nonpublic_audit_only": True, "must_not_be_used_as_public_exact_point": True},
    }


def report(entries):
    return {
        "schema_version": "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2",
        "geometry_join_status": "SEGMENT_IDENTIFIER_ONLY_GEOMETRY_NOT_YET_JOINED",
        "read_only": True,
        "promotion_allowed": False,
        "publication_authority_granted": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "projector_consumed": False,
        "hard_zero_gates": {
            "publication_count": 0,
            "exact_pin_eligible_count": 0,
            "public_map_write_count": 0,
            "location_cache_write_count": 0,
            "projector_consumed_count": 0,
            "midpoint_publication_count": 0,
        },
        "strict_nonpublic_segment_evidence_count": len(entries),
        "claims": entries,
    }


class StreetSegmentEvidenceContractTests(unittest.TestCase):
    def test_valid_identity_evidence_conforms(self):
        result = audit(CONTRACT, report([strict_entry()]))
        self.assertTrue(result["conforms"])
        self.assertEqual(result["unique_segment_identifier_count"], 1)
        self.assertFalse(result["geometry_join_completed"])
        self.assertFalse(result["publication_authority_granted"])

    def test_duplicate_segment_identifier_fails(self):
        a = strict_entry("7654321")
        b = strict_entry("7654321")
        b["claim_key"] = "bk|other between c and d"
        b["endpoint_1"] = {**b["endpoint_1"], "node": "0000011"}
        b["endpoint_2"] = {**b["endpoint_2"], "node": "0000012"}
        b["function_3_from_node"] = "0000011"
        b["function_3_to_node"] = "0000012"
        result = audit(CONTRACT, report([a, b]))
        self.assertFalse(result["conforms"])
        self.assertEqual(result["duplicate_segment_identifier_count"], 1)

    def test_midpoint_publication_prohibition_is_required(self):
        entry = strict_entry()
        entry["candidate_midpoint"].pop("must_not_be_used_as_public_exact_point")
        result = audit(CONTRACT, report([entry]))
        self.assertFalse(result["conforms"])
        self.assertEqual(result["invalid_reason_counts"]["MIDPOINT_PUBLICATION_PROHIBITION_MISSING"], 1)


if __name__ == "__main__":
    unittest.main()
