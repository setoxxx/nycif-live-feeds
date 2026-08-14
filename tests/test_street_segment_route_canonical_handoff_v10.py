from __future__ import annotations

import copy
import unittest

from scripts.audit_street_segment_route_canonical_handoff_v10 import audit


def v9_report():
    return {
        "schema_version": "NYCIF_STREET_SEGMENT_ROUTE_OCCURRENCE_REGISTRY_V9",
        "registry_conformance_pass": True,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "promotion_allowed": False,
        "registry_occurrence_count": 2,
        "registry": [
            {
                "registry_key": "a" * 64,
                "route_bundle_sha256": "c" * 64,
                "occurrence_key_v2": ["nyc-open-data-permitted-events", "100", "2026-09-01T10:00:00"],
            },
            {
                "registry_key": "b" * 64,
                "route_bundle_sha256": "d" * 64,
                "occurrence_key_v2": ["nyc-open-data-permitted-events", "100", "2026-09-08T10:00:00"],
            },
        ],
    }


def event(start: str, *, point: bool = False):
    result = {
        "id": "canonical-" + start,
        "source_dataset": "nyc-open-data-permitted-events",
        "source_event_id": "100",
        "start_date_time": start,
        "event_role": "public_event",
        "parent_event_id": None,
        "nycif": {
            "map_eligibility_state": "LIST_ONLY",
            "certified_pin": False,
            "location_authority": "projector_v3_semantic_map_decision",
            "display_disposition": "list_only",
        },
    }
    if point:
        result["latitude"] = 40.7
        result["longitude"] = -73.9
        result["location_evidence"] = {
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "source": "fixture",
        }
        result["nycif"]["map_eligibility_state"] = "MAP_READY"
        result["nycif"]["certified_pin"] = True
    return result


class CanonicalRouteHandoffV10Tests(unittest.TestCase):
    def test_valid_handoff_preserves_reader_projection(self):
        result = audit(v9_report(), [event("2026-09-01T10:00:00"), event("2026-09-08T10:00:00")])
        self.assertTrue(result["handoff_conformance_pass"])
        self.assertEqual(result["canonical_handoff_certified_count"], 2)
        self.assertEqual(result["no_existing_exact_geometry_authority_count"], 2)
        self.assertTrue(all(value == 0 for value in result["hard_zero_gates"].values()))

    def test_missing_canonical_occurrence_blocks(self):
        result = audit(v9_report(), [event("2026-09-01T10:00:00")])
        self.assertFalse(result["handoff_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["canonical_occurrence_missing_count"], 1)
        self.assertEqual(result["hard_zero_gates"]["silent_canonical_handoff_loss_count"], 1)

    def test_duplicate_canonical_occurrence_blocks(self):
        first = event("2026-09-01T10:00:00")
        result = audit(v9_report(), [first, copy.deepcopy(first), event("2026-09-08T10:00:00")])
        self.assertFalse(result["handoff_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["canonical_occurrence_not_unique_count"], 1)

    def test_duplicate_v9_occurrence_key_blocks(self):
        report = v9_report()
        report["registry"][1]["occurrence_key_v2"] = list(report["registry"][0]["occurrence_key_v2"])
        result = audit(report, [event("2026-09-01T10:00:00")])
        self.assertFalse(result["handoff_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["duplicate_v9_occurrence_key_count"], 1)

    def test_existing_point_authority_wins_without_failure(self):
        result = audit(v9_report(), [event("2026-09-01T10:00:00", point=True), event("2026-09-08T10:00:00")])
        self.assertTrue(result["handoff_conformance_pass"])
        self.assertEqual(result["existing_point_authority_count"], 1)
        first = next(row for row in result["handoffs"] if row["occurrence_key_v2"][2] == "2026-09-01T10:00:00")
        self.assertEqual(first["authority_precedence"], "EXISTING_POINT_AUTHORITY_WINS")

    def test_upstream_publication_boundary_violation_raises(self):
        report = v9_report()
        report["publication_authority_granted"] = True
        with self.assertRaises(ValueError):
            audit(report, [event("2026-09-01T10:00:00"), event("2026-09-08T10:00:00")])


if __name__ == "__main__":
    unittest.main()
