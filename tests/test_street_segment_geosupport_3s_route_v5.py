from __future__ import annotations

import copy
import unittest

from scripts.audit_street_segment_geosupport_3s_route_v5 import audit


V4 = {
    "schema_version": "NYCIF_STREET_SEGMENT_LION_GEOMETRY_AUDIT_V4",
    "publication_authority_granted": False,
    "projector_consumed": False,
    "entries": [
        {
            "claim_key": "mn|broadway",
            "borough": "Manhattan",
            "event_location": "BROADWAY between WORTH STREET and LIBERTY STREET",
            "occurrence_count": 3,
            "source_event_ids": ["a", "b", "c"],
            "geometry_joined": False,
            "reason_code": "LION_GEOMETRY_ENDPOINT_DISAGREEMENT",
            "endpoint_1": {"node": "0010001", "latitude": 40.7, "longitude": -74.0},
            "endpoint_2": {"node": "0010004", "latitude": 40.71, "longitude": -74.0},
        }
    ],
}


class Fake3S:
    def __init__(self, nodes=None, declared=None, fail=False):
        self.nodes = nodes or ["0010001", "0010002", "0010003", "0010004"]
        self.declared = declared
        self.fail = fail

    def call(self, payload):
        self.last_payload = payload
        if self.fail:
            raise RuntimeError("unresolved")
        rows = [{"Node Number": node} for node in self.nodes]
        count = len(rows) if self.declared is None else self.declared
        return {"Number of Intersections": f"{count:03d}", "LIST OF INTERSECTIONS": rows}


class Route3STests(unittest.TestCase):
    def test_ordered_route_certifies_without_geometry_or_publication(self):
        result = audit(copy.deepcopy(V4), Fake3S())
        self.assertEqual(result["target_claim_count"], 1)
        self.assertEqual(result["route_topology_certified_count"], 1)
        self.assertEqual(result["route_topology_certified_occurrence_count"], 3)
        route = result["routes"][0]
        self.assertTrue(route["route_topology_certified"])
        self.assertEqual(route["route_edge_count"], 3)
        self.assertEqual(route["route_orientation"], "FORWARD")
        self.assertFalse(route["geometry_joined"])
        self.assertFalse(route["shortest_path_algorithm_used"])
        self.assertTrue(all(value == 0 for value in result["hard_zero_gates"].values()))

    def test_reverse_terminal_order_is_allowed(self):
        result = audit(copy.deepcopy(V4), Fake3S(nodes=["0010004", "0010003", "0010001"]))
        self.assertEqual(result["route_topology_certified_count"], 1)
        self.assertEqual(result["routes"][0]["route_orientation"], "REVERSE")

    def test_terminal_node_mismatch_blocks(self):
        result = audit(copy.deepcopy(V4), Fake3S(nodes=["0099999", "0010002", "0010004"]))
        self.assertEqual(result["route_topology_certified_count"], 0)
        self.assertEqual(result["routes"][0]["reason_code"], "GEOSUPPORT_3S_ENDPOINT_NODE_MISMATCH")

    def test_repeated_node_blocks(self):
        result = audit(copy.deepcopy(V4), Fake3S(nodes=["0010001", "0010002", "0010002", "0010004"]))
        self.assertEqual(result["route_topology_certified_count"], 0)
        self.assertEqual(result["routes"][0]["reason_code"], "GEOSUPPORT_3S_ROUTE_REPEATS_NODE")

    def test_declared_count_mismatch_blocks(self):
        result = audit(copy.deepcopy(V4), Fake3S(declared=9))
        self.assertEqual(result["route_topology_certified_count"], 0)
        self.assertEqual(result["routes"][0]["reason_code"], "GEOSUPPORT_3S_COUNT_MISMATCH")

    def test_3s_failure_blocks(self):
        result = audit(copy.deepcopy(V4), Fake3S(fail=True))
        self.assertEqual(result["route_topology_certified_count"], 0)
        self.assertEqual(result["routes"][0]["reason_code"], "GEOSUPPORT_3S_UNRESOLVED")

    def test_only_v4_endpoint_disagreement_is_targeted(self):
        v4 = copy.deepcopy(V4)
        other = copy.deepcopy(v4["entries"][0])
        other["claim_key"] = "other"
        other["reason_code"] = "OFFICIAL_LION_SEGMENT_REPRESENTATIONS_CONFLICT"
        v4["entries"].append(other)
        result = audit(v4, Fake3S())
        self.assertEqual(result["target_claim_count"], 1)


if __name__ == "__main__":
    unittest.main()
