from __future__ import annotations

import copy
import unittest

from scripts.audit_street_segment_lion_route_edges_v6 import audit


V5 = {
    "schema_version": "NYCIF_STREET_SEGMENT_GEOSUPPORT_3S_ROUTE_AUDIT_V5",
    "publication_authority_granted": False,
    "geometry_join_completed": False,
    "shortest_path_algorithm_used": False,
    "routes": [
        {
            "claim_key": "mn|route",
            "occurrence_count": 2,
            "route_topology_certified": True,
            "ordered_edge_node_pairs": [["0000001", "0000002"], ["0000002", "0000003"]],
        }
    ],
}


def feature(a, b, segment="1", coords=None, join="A"):
    if coords is None:
        coords = [[-74.0, 40.70], [-73.999, 40.701]]
    return {
        "type": "Feature",
        "properties": {
            "NodeIDFrom": a,
            "NodeIDTo": b,
            "SegmentID": segment,
            "Join_ID": join,
            "Street": "TEST STREET",
            "FeatureTyp": "0",
            "SegmentTyp": "U",
            "RB_Layer": "B",
            "PhysicalID": 100,
            "GenericID": 200,
        },
        "geometry": {"type": "LineString", "coordinates": coords},
    }


class RouteEdgeV6Tests(unittest.TestCase):
    def test_unique_edges_classify_without_route_promotion(self):
        source = {"type": "FeatureCollection", "features": [
            feature("0000001", "0000002", "10"),
            feature("0000003", "0000002", "11"),
        ]}
        result = audit(copy.deepcopy(V5), source)
        self.assertEqual(result["ordered_route_edge_count"], 2)
        self.assertEqual(result["accepted_edge_candidate_count"], 2)
        self.assertEqual(result["fully_source_resolved_route_count"], 1)
        self.assertFalse(result["route_geometry_join_completed"])
        self.assertTrue(all(value == 0 for value in result["hard_zero_gates"].values()))

    def test_equivalent_duplicate_rows_collapse(self):
        first = feature("0000001", "0000002", "10", join="A")
        second = copy.deepcopy(first)
        second["properties"]["Join_ID"] = "B"
        source = {"type": "FeatureCollection", "features": [first, second, feature("0000002", "0000003", "11")]}
        result = audit(copy.deepcopy(V5), source)
        edge = result["routes"][0]["edges"][0]
        self.assertEqual(edge["reason_code"], "LION_ROUTE_EDGE_EQUIVALENT_SOURCE_ROWS")
        self.assertTrue(edge["source_equivalence_collapsed"])

    def test_conflicting_duplicate_rows_block_with_bounded_diagnostics(self):
        first = feature("0000001", "0000002", "10", join="A")
        second = feature("0000001", "0000002", "12", coords=[[-74.0, 40.70], [-73.998, 40.702]], join="B")
        source = {"type": "FeatureCollection", "features": [first, second, feature("0000002", "0000003", "11")]}
        result = audit(copy.deepcopy(V5), source)
        edge = result["routes"][0]["edges"][0]
        self.assertEqual(result["blocked_edge_candidate_count"], 1)
        self.assertEqual(edge["reason_code"], "LION_ROUTE_EDGE_CONFLICTING_SOURCE_ROWS")
        self.assertFalse(edge["edge_geometry_candidate_accepted"])
        self.assertEqual(edge["blocked_source_candidate_diagnostic_count"], 2)
        self.assertFalse(edge["blocked_source_candidate_diagnostics_truncated"])
        diagnostics = edge["blocked_source_candidate_diagnostics"]
        self.assertEqual({row["source_segment_id"] for row in diagnostics}, {"10", "12"})
        self.assertEqual(len({row["geometry_sha256"] for row in diagnostics}), 2)
        self.assertNotIn("geometry", diagnostics[0])
        self.assertEqual(result["fully_source_resolved_route_count"], 0)

    def test_missing_edge_blocks(self):
        source = {"type": "FeatureCollection", "features": [feature("0000001", "0000002", "10")]}
        result = audit(copy.deepcopy(V5), source)
        self.assertEqual(result["blocked_edge_candidate_count"], 1)
        self.assertEqual(result["routes"][0]["edges"][1]["reason_code"], "LION_ROUTE_EDGE_NOT_FOUND")

    def test_duplicate_route_edge_pair_is_measured(self):
        v5 = copy.deepcopy(V5)
        second = copy.deepcopy(v5["routes"][0])
        second["claim_key"] = "mn|other"
        second["ordered_edge_node_pairs"] = [["0000002", "0000001"]]
        v5["routes"].append(second)
        source = {"type": "FeatureCollection", "features": [
            feature("0000001", "0000002", "10"),
            feature("0000002", "0000003", "11"),
        ]}
        result = audit(v5, source)
        self.assertEqual(result["duplicate_route_edge_pair_count"], 1)

    def test_blocked_diagnostics_are_capped(self):
        rows = []
        for index in range(10):
            rows.append(feature(
                "0000001",
                "0000002",
                str(10 + index),
                coords=[[-74.0, 40.70], [-73.999 + index * 0.00001, 40.701]],
                join=str(index),
            ))
        rows.append(feature("0000002", "0000003", "99"))
        result = audit(copy.deepcopy(V5), {"type": "FeatureCollection", "features": rows})
        edge = result["routes"][0]["edges"][0]
        self.assertEqual(edge["blocked_source_candidate_diagnostic_count"], 8)
        self.assertTrue(edge["blocked_source_candidate_diagnostics_truncated"])


if __name__ == "__main__":
    unittest.main()
