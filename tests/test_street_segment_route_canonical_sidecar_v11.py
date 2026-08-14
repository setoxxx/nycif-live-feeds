from __future__ import annotations

import copy
import unittest

from scripts.build_street_segment_route_canonical_sidecar_v11 import build


def handoff(index: int = 1) -> dict:
    start = f"2026-08-{14 + index:02d}T11:00:00"
    registry_key = f"{index:064x}"[-64:]
    bundle_hash = f"{index + 100:064x}"[-64:]
    reader_hash = f"{index + 200:064x}"[-64:]
    return {
        "occurrence_key_v2": ["tvpp-9vvx", str(900000 + index), start],
        "registry_key": registry_key,
        "route_bundle_sha256": bundle_hash,
        "canonical_event_id": f"review_supplemental:tvpp-9vvx:{900000 + index}@2026-08-{14 + index:02d}",
        "canonical_map_state": "LIST_ONLY",
        "canonical_display_disposition": "list_only",
        "existing_point_authority": False,
        "existing_area_authority": False,
        "authority_precedence": "ROUTE_EVIDENCE_REMAINS_NONPUBLIC_SIDECAR_ONLY",
        "reader_projection_sha256": reader_hash,
        "canonical_handoff_certified": True,
        "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
    }


def payload(rows: list[dict]) -> dict:
    return {
        "schema_version": "NYCIF_STREET_SEGMENT_ROUTE_CANONICAL_HANDOFF_AUDIT_V10",
        "handoff_conformance_pass": True,
        "release_status": "NONPUBLIC_EVIDENCE_ONLY",
        "publication_authority_granted": False,
        "public_renderer_enabled": False,
        "projector_consumed": False,
        "promotion_allowed": False,
        "canonical_modified": False,
        "reader_safe_modified": False,
        "input_v9_occurrence_count": len(rows),
        "canonical_handoff_certified_count": len(rows),
        "hard_zero_gates": {"publication_count": 0},
        "handoffs": rows,
    }


class CanonicalRouteSidecarV11Tests(unittest.TestCase):
    def test_valid_reference_only_sidecar(self) -> None:
        result = build(payload([handoff(1), handoff(2)]))
        self.assertTrue(result["sidecar_conformance_pass"])
        self.assertEqual(result["sidecar_entry_count"], 2)
        self.assertEqual(result["unique_canonical_event_id_count"], 2)
        self.assertTrue(result["reference_only"])
        self.assertFalse(result["publication_authority_granted"])
        self.assertTrue(all(value == 0 for value in result["hard_zero_gates"].values()))
        for row in result["sidecar"]:
            self.assertFalse(row["contains_geometry"])
            self.assertFalse(row["contains_coordinates"])
            self.assertEqual(row["attachment_state"], "REFERENCE_ONLY_NOT_ATTACHED_TO_CANONICAL")

    def test_duplicate_canonical_event_id_blocks(self) -> None:
        first = handoff(1)
        second = handoff(2)
        second["canonical_event_id"] = first["canonical_event_id"]
        result = build(payload([first, second]))
        self.assertFalse(result["sidecar_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["duplicate_canonical_event_id_count"], 1)

    def test_duplicate_occurrence_key_blocks(self) -> None:
        first = handoff(1)
        second = handoff(2)
        second["occurrence_key_v2"] = list(first["occurrence_key_v2"])
        result = build(payload([first, second]))
        self.assertFalse(result["sidecar_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["duplicate_occurrence_key_count"], 1)

    def test_point_authority_blocks_sidecar_candidate(self) -> None:
        row = handoff(1)
        row["existing_point_authority"] = True
        row["authority_precedence"] = "EXISTING_POINT_AUTHORITY_WINS"
        result = build(payload([row]))
        self.assertFalse(result["sidecar_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["existing_point_authority_count"], 1)

    def test_non_list_only_state_blocks(self) -> None:
        row = handoff(1)
        row["canonical_map_state"] = "MAP_READY"
        result = build(payload([row]))
        self.assertFalse(result["sidecar_conformance_pass"])
        self.assertEqual(result["hard_zero_gates"]["non_list_only_map_state_count"], 1)

    def test_upstream_publication_boundary_violation_raises(self) -> None:
        source = payload([handoff(1)])
        source["publication_authority_granted"] = True
        with self.assertRaises(ValueError):
            build(source)

    def test_upstream_nonzero_gate_raises(self) -> None:
        source = payload([handoff(1)])
        source["hard_zero_gates"]["publication_count"] = 1
        with self.assertRaises(ValueError):
            build(source)

    def test_sidecar_key_changes_if_evidence_reference_changes(self) -> None:
        source = payload([handoff(1)])
        first = build(source)["sidecar"][0]["sidecar_key"]
        changed = copy.deepcopy(source)
        changed["handoffs"][0]["route_bundle_sha256"] = "f" * 64
        second = build(changed)["sidecar"][0]["sidecar_key"]
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
