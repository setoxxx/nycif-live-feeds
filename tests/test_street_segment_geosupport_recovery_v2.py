from __future__ import annotations

import unittest

from scripts.audit_street_segment_geosupport_recovery_v2 import (
    EVIDENCE_CLASS,
    GeoSupportStreetEvidence,
    audit_claims,
    borough_code,
)


class FakeGeoSupport:
    def __init__(
        self,
        *,
        mismatch_segment: bool = False,
        bad_coordinate: bool = False,
        missing_segment_identifier: bool = False,
    ) -> None:
        self.mismatch_segment = mismatch_segment
        self.bad_coordinate = bad_coordinate
        self.missing_segment_identifier = missing_segment_identifier

    def call(self, payload):
        function = str(payload.get("function")).upper()
        if function == "2":
            cross = str(payload.get("street_name_2") or "").lower()
            if "worth" in cross:
                return {"LION Node Number": "0015487", "Number of Intersecting Streets": "2"}
            if "leonard" in cross:
                return {"LION Node Number": "0020353", "Number of Intersecting Streets": "2"}
            raise RuntimeError("unresolved")
        if function == "2W":
            node = str(payload.get("node"))
            if node == "0015487":
                return {
                    "Latitude": "40.714000000",
                    "Longitude": "-74.002000000",
                    "List of Street Names": ["LAFAYETTE STREET", "WORTH STREET"],
                }
            if node == "0020353":
                return {
                    "Latitude": "0" if self.bad_coordinate else "40.718000000",
                    "Longitude": "0" if self.bad_coordinate else "-74.001000000",
                    "List of Street Names": ["LAFAYETTE STREET", "LEONARD STREET"],
                }
            raise RuntimeError("node not found")
        if function == "3":
            if self.mismatch_segment:
                return {
                    "From Node": "9999999",
                    "To Node": "0020353",
                    "Segment Identifier": "0023578",
                }
            return {
                "From Node": "0015487",
                "To Node": "0020353",
                "Segment Identifier": "" if self.missing_segment_identifier else "0023578",
            }
        raise RuntimeError(f"unsupported function {function}")


CLAIM = {
    "borough": "Manhattan",
    "event_location": "Lafayette St between Worth St and Leonard St",
    "occurrence_count": 3,
    "source_event_ids": ["1", "2", "3"],
}


class GeoSupportStreetSegmentRecoveryTests(unittest.TestCase):
    def test_borough_mapping(self) -> None:
        self.assertEqual(borough_code("Brooklyn"), "BK")
        self.assertEqual(borough_code("Staten Island"), "SI")
        self.assertIsNone(borough_code("Nassau"))

    def test_strict_candidate_is_nonpublic_only(self) -> None:
        evidence = GeoSupportStreetEvidence(FakeGeoSupport())
        result = evidence.resolve_segment(CLAIM)
        self.assertTrue(result["strict_nonpublic_segment_evidence"])
        self.assertEqual(result["evidence_class"], EVIDENCE_CLASS)
        self.assertEqual(result["publication_state"], "NONPUBLIC_EVIDENCE_ONLY")
        self.assertFalse(result["publication_allowed"])
        self.assertFalse(result["exact_pin_eligible"])
        self.assertFalse(result["projector_consumed"])
        self.assertEqual(result["function_3_from_node"], "0015487")
        self.assertEqual(result["function_3_to_node"], "0020353")
        self.assertEqual(result["function_3_segment_identifier"], "0023578")
        self.assertTrue(
            result["candidate_midpoint"]["must_not_be_used_as_public_exact_point"]
        )
        self.assertGreater(result["distance_m"], 20)

    def test_function_3_node_pair_mismatch_blocks(self) -> None:
        evidence = GeoSupportStreetEvidence(FakeGeoSupport(mismatch_segment=True))
        result = evidence.resolve_segment(CLAIM)
        self.assertFalse(result["strict_nonpublic_segment_evidence"])
        self.assertEqual(result["reason_code"], "SEGMENT_NODE_PAIR_MISMATCH")

    def test_missing_segment_identifier_blocks(self) -> None:
        evidence = GeoSupportStreetEvidence(FakeGeoSupport(missing_segment_identifier=True))
        result = evidence.resolve_segment(CLAIM)
        self.assertFalse(result["strict_nonpublic_segment_evidence"])
        self.assertEqual(result["reason_code"], "SEGMENT_IDENTIFIER_MISSING")

    def test_invalid_endpoint_coordinate_blocks(self) -> None:
        evidence = GeoSupportStreetEvidence(FakeGeoSupport(bad_coordinate=True))
        result = evidence.resolve_segment(CLAIM)
        self.assertFalse(result["strict_nonpublic_segment_evidence"])
        self.assertEqual(result["reason_code"], "INTERSECTION_COORDINATE_INVALID")
        self.assertEqual(result["failed_endpoint"], "cross2")

    def test_report_hard_zero_gates_remain_zero(self) -> None:
        evidence = GeoSupportStreetEvidence(FakeGeoSupport())
        report = audit_claims({"mn|lafayette": dict(CLAIM)}, evidence)
        self.assertEqual(report["strict_nonpublic_segment_evidence_count"], 1)
        self.assertEqual(report["strict_nonpublic_occurrence_coverage"], 3)
        self.assertEqual(report["unresolved_or_blocked_claim_count"], 0)
        self.assertEqual(report["geosupport_call_count"], 5)
        self.assertEqual(
            report["geometry_join_status"],
            "SEGMENT_IDENTIFIER_ONLY_GEOMETRY_NOT_YET_JOINED",
        )
        self.assertEqual(
            report["hard_zero_gates"],
            {
                "publication_count": 0,
                "exact_pin_eligible_count": 0,
                "public_map_write_count": 0,
                "location_cache_write_count": 0,
                "projector_consumed_count": 0,
                "midpoint_publication_count": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
