import copy
import unittest

from scripts.audit_exact_event_area_evidence_v1 import audit, geometry_sha256


CONTRACT = {
    "artifact_type": "nycif_exact_event_area_evidence_contract_v1",
    "required_registry_entry_fields": [
        "registry_key", "evidence_class", "publication_state", "source_cemsid",
        "official_system_id", "official_featurestatus", "matched_permit_fields",
        "geometry_type", "geometry_source_field", "geometry_sha256", "geometry",
        "event_site_agreement", "point_generated", "centroid_generated",
        "publication_eligible", "exact_pin_eligible",
    ],
    "required_event_site_agreement_flags": [
        "property_name_and_borough_unique", "sport_field_pair_strict",
        "field_identifier_exact", "sport_permit_explicit",
        "source_cemsid_singleton", "official_system_one_to_one",
        "featurestatus_active",
    ],
    "allowed_geometry_types": ["MultiPolygon"],
    "contract_audit_gates": {
        "invalid_registry_entry_count_required": 0,
        "duplicate_registry_system_count_required": 0,
        "duplicate_registry_source_cemsid_count_required": 0,
        "geometry_hash_mismatch_count_required": 0,
        "point_generated_count_required": 0,
        "centroid_generated_count_required": 0,
        "publication_eligible_count_required": 0,
        "exact_pin_candidate_count_required": 0,
        "projector_consumed_required": False,
    },
}


def registry_entry():
    geometry = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]]}
    return {
        "registry_key": "parks-cems-area:10:Q001-BASKETBALL-1",
        "evidence_class": "OFFICIAL_PARKS_FACILITY_AREA",
        "publication_state": "NONPUBLIC_EVIDENCE_ONLY",
        "source_cemsid": "10",
        "official_system_id": "Q001-BASKETBALL-1",
        "official_featurestatus": "Active",
        "matched_permit_fields": ["basketball"],
        "geometry_type": "MultiPolygon",
        "geometry_source_field": "multipolygon",
        "geometry_sha256": geometry_sha256(geometry),
        "geometry": geometry,
        "event_site_agreement": {
            "property_name_and_borough_unique": True,
            "sport_field_pair_strict": True,
            "field_identifier_exact": True,
            "sport_permit_explicit": True,
            "source_cemsid_singleton": True,
            "official_system_one_to_one": True,
            "featurestatus_active": True,
        },
        "point_generated": False,
        "centroid_generated": False,
        "publication_eligible": False,
        "exact_pin_eligible": False,
    }


def registry(entries):
    return {
        "schema_version": "NYCIF_PARKS_CEMS_AREA_EVIDENCE_REGISTRY_V7",
        "registry_occurrence_coverage": len(entries),
        "blocked_candidate_count": 0,
        "point_generated_count": 0,
        "centroid_generated_count": 0,
        "publication_eligible_count": 0,
        "exact_pin_candidate_count": 0,
        "projector_consumed": False,
        "entries": entries,
    }


class ExactEventAreaEvidenceAuditTests(unittest.TestCase):
    def test_clean_nonpublic_area_entry_passes(self):
        report = audit(CONTRACT, registry([registry_entry()]))
        self.assertTrue(report["pass"])
        self.assertEqual(report["gate_results"]["invalid_registry_entry_count"], 0)
        self.assertFalse(report["publication_authority_granted"])
        self.assertFalse(report["projector_consumption_authorized"])

    def test_geometry_hash_mismatch_fails(self):
        entry = registry_entry()
        entry["geometry_sha256"] = "0" * 64
        report = audit(CONTRACT, registry([entry]))
        self.assertFalse(report["pass"])
        self.assertEqual(report["gate_results"]["geometry_hash_mismatch_count"], 1)

    def test_duplicate_system_or_cemsid_fails(self):
        first = registry_entry()
        second = copy.deepcopy(first)
        second["registry_key"] = "parks-cems-area:10:Q001-BASKETBALL-1-copy"
        report = audit(CONTRACT, registry([first, second]))
        self.assertFalse(report["pass"])
        self.assertEqual(report["gate_results"]["duplicate_registry_system_count"], 1)
        self.assertEqual(report["gate_results"]["duplicate_registry_source_cemsid_count"], 1)

    def test_any_publication_or_point_authority_fails(self):
        entry = registry_entry()
        entry["publication_eligible"] = True
        payload = registry([entry])
        payload["publication_eligible_count"] = 1
        payload["point_generated_count"] = 1
        payload["projector_consumed"] = True
        report = audit(CONTRACT, payload)
        self.assertFalse(report["pass"])
        self.assertGreater(report["gate_results"]["invalid_registry_entry_count"], 0)


if __name__ == "__main__":
    unittest.main()
