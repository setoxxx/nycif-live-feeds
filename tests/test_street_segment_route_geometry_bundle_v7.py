from __future__ import annotations

import copy
import unittest

from scripts.audit_street_segment_route_geometry_bundle_v7 import _hash, audit


def edge(index: int, a: str, b: str, x: float = 0.0):
    geometry = {"type": "LineString", "coordinates": [[x, 40.0], [x + 0.001, 40.001]]}
    return {
        "edge_index": index,
        "ordered_node_pair": [a, b],
        "edge_geometry_candidate_accepted": True,
        "geometry_type": "LineString",
        "geometry_sha256": _hash(geometry),
        "geometry": geometry,
        "source_segment_id": str(index + 1),
        "source_physical_id": index + 10,
        "source_generic_id": index + 20,
        "source_street": "TEST STREET",
        "source_feature_type": "0",
        "source_segment_type": "U",
        "source_rb_layer": "B",
    }


def v6_report():
    return {
        "schema_version": "NYCIF_STREET_SEGMENT_LION_ROUTE_EDGE_AUDIT_V6",
        "publication_authority_granted": False,
        "projector_consumed": False,
        "route_geometry_join_completed": False,
        "shortest_path_algorithm_used": False,
        "routes": [{
            "claim_key": "mn|test",
            "occurrence_count": 3,
            "route_edge_count": 2,
            "accepted_edge_count": 2,
            "blocked_edge_count": 0,
            "all_route_edges_source_resolved": True,
            "route_geometry_joined": False,
            "edges": [edge(0, "0000001", "0000002"), edge(1, "0000002", "0000003", 1.0)],
        }],
    }


class RouteGeometryBundleV7Tests(unittest.TestCase):
    def test_certifies_ordered_source_bundle_without_synthesis(self):
        result = audit(v6_report())
        self.assertEqual(result["route_geometry_bundle_certified_count"], 1)
        self.assertEqual(result["route_geometry_bundle_certified_occurrence_count"], 3)
        self.assertEqual(result["certified_component_edge_count"], 2)
        route = result["routes"][0]
        self.assertTrue(route["route_geometry_bundle_certified"])
        self.assertEqual([edge["ordered_node_pair"] for edge in route["ordered_source_edges"]], [["0000001", "0000002"], ["0000002", "0000003"]])
        self.assertFalse(route["dissolved_geometry_created"])
        self.assertFalse(route["concatenated_geometry_created"])
        self.assertFalse(route["endpoint_snapping_used"])
        self.assertEqual(route["synthetic_coordinate_count"], 0)
        self.assertTrue(all(value == 0 for value in result["hard_zero_gates"].values()))

    def test_bundle_hash_is_deterministic_and_order_sensitive(self):
        first = audit(v6_report())["routes"][0]["route_bundle_sha256"]
        second = audit(v6_report())["routes"][0]["route_bundle_sha256"]
        self.assertEqual(first, second)
        changed = v6_report()
        changed["routes"][0]["edges"].reverse()
        altered = audit(changed)["routes"][0]
        self.assertNotEqual(first, altered["route_bundle_sha256"])

    def test_blocked_v6_route_withheld_as_unit(self):
        report = v6_report()
        route = report["routes"][0]
        route["all_route_edges_source_resolved"] = False
        route["accepted_edge_count"] = 1
        route["blocked_edge_count"] = 1
        route["edges"][1]["edge_geometry_candidate_accepted"] = False
        result = audit(report)
        self.assertEqual(result["route_geometry_bundle_certified_count"], 0)
        self.assertEqual(result["routes"][0]["reason_code"], "V6_ROUTE_HAS_BLOCKED_EDGE")

    def test_hash_mismatch_blocks_entire_route(self):
        report = v6_report()
        report["routes"][0]["edges"][0]["geometry_sha256"] = "0" * 64
        result = audit(report)
        self.assertEqual(result["route_geometry_bundle_certified_count"], 0)
        self.assertEqual(result["routes"][0]["reason_code"], "V6_ACCEPTED_EDGE_EVIDENCE_INVALID")

    def test_edge_count_contradiction_blocks(self):
        report = v6_report()
        report["routes"][0]["route_edge_count"] = 3
        result = audit(report)
        self.assertEqual(result["routes"][0]["reason_code"], "V6_ROUTE_EDGE_COUNT_CONTRADICTION")

    def test_v6_safety_boundary_violation_raises(self):
        report = v6_report()
        report["publication_authority_granted"] = True
        with self.assertRaises(ValueError):
            audit(report)


if __name__ == "__main__":
    unittest.main()
