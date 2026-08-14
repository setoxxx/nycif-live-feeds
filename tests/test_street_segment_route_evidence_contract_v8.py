from __future__ import annotations

import copy
import unittest

from scripts.audit_street_segment_route_evidence_contract_v8 import audit, digest


CONTRACT = {
    "artifact_type": "nycif_exact_event_route_evidence_contract_v1",
    "release_status": "NONPUBLIC_EVIDENCE_ONLY",
    "scope": {
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumption_enabled": False,
    },
    "allowed_geometry_types": ["LineString", "MultiLineString"],
    "required_route_fields": [
        "claim_key", "occurrence_count", "route_geometry_bundle_certified", "reason_code",
        "publication_state", "publication_allowed", "projector_consumed", "public_renderer_enabled",
        "route_edge_count", "route_bundle_sha256", "ordered_source_edges", "dissolved_geometry_created",
        "concatenated_geometry_created", "endpoint_snapping_used", "synthetic_coordinate_count",
    ],
    "required_component_fields": [
        "edge_index", "ordered_node_pair", "geometry_type", "geometry_sha256", "geometry",
        "source_segment_id", "source_street",
    ],
    "contract_audit_gates": {
        "invalid_route_entry_count_required": 0,
        "invalid_component_entry_count_required": 0,
        "component_geometry_hash_mismatch_count_required": 0,
        "route_bundle_hash_mismatch_count_required": 0,
        "route_topology_discontinuity_count_required": 0,
        "duplicate_claim_key_count_required": 0,
        "point_generated_count_required": 0,
        "midpoint_publication_count_required": 0,
        "dissolved_route_geometry_count_required": 0,
        "concatenated_route_geometry_count_required": 0,
        "synthetic_coordinate_count_required": 0,
        "publication_eligible_count_required": 0,
        "exact_pin_candidate_count_required": 0,
        "public_renderer_enabled_required": False,
        "projector_consumed_required": False,
    },
}


def report():
    geometry_1 = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
    geometry_2 = {"type": "LineString", "coordinates": [[1, 1], [2, 2]]}
    edges = [
        {
            "edge_index": 0,
            "ordered_node_pair": ["1", "2"],
            "geometry_type": "LineString",
            "geometry_sha256": digest(geometry_1),
            "geometry": geometry_1,
            "source_segment_id": "a",
            "source_street": "X",
        },
        {
            "edge_index": 1,
            "ordered_node_pair": ["2", "3"],
            "geometry_type": "LineString",
            "geometry_sha256": digest(geometry_2),
            "geometry": geometry_2,
            "source_segment_id": "b",
            "source_street": "X",
        },
    ]
    bundle_hash = digest([
        {"edge_index": edge["edge_index"], "ordered_node_pair": edge["ordered_node_pair"], "geometry_sha256": edge["geometry_sha256"]}
        for edge in edges
    ])
    return {
        "schema_version": "NYCIF_STREET_SEGMENT_ROUTE_GEOMETRY_BUNDLE_AUDIT_V7",
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "dissolved_geometry_created": False,
        "concatenated_geometry_created": False,
        "endpoint_snapping_used": False,
        "synthetic_coordinate_count": 0,
        "routes": [{
            "claim_key": "x",
            "occurrence_count": 1,
            "route_geometry_bundle_certified": True,
            "reason_code": "ORDERED_SOURCE_GEOMETRY_BUNDLE_CERTIFIED",
            "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
            "publication_allowed": False,
            "projector_consumed": False,
            "public_renderer_enabled": False,
            "route_edge_count": 2,
            "route_bundle_sha256": bundle_hash,
            "ordered_source_edges": edges,
            "dissolved_geometry_created": False,
            "concatenated_geometry_created": False,
            "endpoint_snapping_used": False,
            "synthetic_coordinate_count": 0,
        }],
    }


class RouteEvidenceContractV8Tests(unittest.TestCase):
    def test_valid_contract_corpus_passes(self):
        result = audit(CONTRACT, report())
        self.assertTrue(result["contract_conformance_pass"])
        self.assertEqual(result["validated_route_count"], 1)

    def test_component_hash_mismatch_fails(self):
        value = report()
        value["routes"][0]["ordered_source_edges"][0]["geometry_sha256"] = "0" * 64
        result = audit(CONTRACT, value)
        self.assertFalse(result["contract_conformance_pass"])
        self.assertEqual(result["audit_gates"]["component_geometry_hash_mismatch_count"], 1)

    def test_bundle_hash_mismatch_fails(self):
        value = report()
        value["routes"][0]["route_bundle_sha256"] = "0" * 64
        result = audit(CONTRACT, value)
        self.assertFalse(result["contract_conformance_pass"])
        self.assertEqual(result["audit_gates"]["route_bundle_hash_mismatch_count"], 1)

    def test_route_topology_discontinuity_fails(self):
        value = report()
        value["routes"][0]["ordered_source_edges"][1]["ordered_node_pair"] = ["9", "3"]
        value["routes"][0]["route_bundle_sha256"] = digest([
            {"edge_index": edge["edge_index"], "ordered_node_pair": edge["ordered_node_pair"], "geometry_sha256": edge["geometry_sha256"]}
            for edge in value["routes"][0]["ordered_source_edges"]
        ])
        result = audit(CONTRACT, value)
        self.assertFalse(result["contract_conformance_pass"])
        self.assertEqual(result["audit_gates"]["route_topology_discontinuity_count"], 1)

    def test_duplicate_claim_key_fails(self):
        value = report()
        value["routes"].append(copy.deepcopy(value["routes"][0]))
        result = audit(CONTRACT, value)
        self.assertFalse(result["contract_conformance_pass"])
        self.assertEqual(result["audit_gates"]["duplicate_claim_key_count"], 1)

    def test_contract_publication_authority_violation_raises(self):
        contract = copy.deepcopy(CONTRACT)
        contract["scope"]["publication_authority_granted"] = True
        with self.assertRaises(ValueError):
            audit(contract, report())


if __name__ == "__main__":
    unittest.main()
