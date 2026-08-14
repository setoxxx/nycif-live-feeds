import unittest

from scripts.build_parks_cems_area_evidence_registry_v7 import build_registry


class ParksCemsAreaEvidenceRegistryV7Tests(unittest.TestCase):
    def _candidate(self, *, claim, cemsid, system, occurrence_count=1, descriptor="Soccer-01"):
        return {
            "claim_key": claim,
            "borough_code": "Q",
            "park_name": "Example Park",
            "facility_descriptor": descriptor,
            "parsed_sport": "soccer",
            "parsed_field_id": "1",
            "occurrence_count": occurrence_count,
            "source_event_ids": [f"event-{claim}"],
            "source_cemsids": [cemsid],
            "evidence": {
                "official_system_id": system,
                "official_gispropnum": "Q001",
            },
        }

    def _facility(self, *, system="Q001-SOCCER-1", field="01"):
        return {
            "gispropnum": "Q001",
            "system": system,
            "field_number": field,
            "featurestatus": "Active",
            "regulation_soccer": True,
            "nonregulation_soccer": True,
            "primary_sport": "SCR",
            "multipolygon": {"type": "MultiPolygon", "coordinates": []},
        }

    def _report(self, candidates):
        return {
            "schema_version": "NYCIF_PARKS_CEMS_STRICT_FACILITY_AREA_PROBE_V6",
            "publication_eligible_count": 0,
            "exact_pin_candidate_count": 0,
            "strict_occurrence_coverage": sum(c["occurrence_count"] for c in candidates),
            "candidates": candidates,
        }

    def test_clean_one_to_one_candidate_becomes_nonpublic_registry_entry(self):
        candidate = self._candidate(claim="a", cemsid="100", system="Q001-SOCCER-1", occurrence_count=4)
        report = build_registry(self._report([candidate]), [self._facility()])
        self.assertEqual(report["registry_entry_count"], 1)
        self.assertEqual(report["registry_occurrence_coverage"], 4)
        self.assertEqual(report["duplicate_registry_system_count"], 0)
        self.assertEqual(report["duplicate_registry_source_cemsid_count"], 0)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertEqual(report["exact_pin_candidate_count"], 0)
        self.assertEqual(report["point_generated_count"], 0)
        self.assertEqual(report["centroid_generated_count"], 0)
        self.assertFalse(report["projector_consumed"])
        entry = report["entries"][0]
        self.assertEqual(entry["publication_state"], "NONPUBLIC_EVIDENCE_ONLY")
        self.assertEqual(entry["geometry_type"], "MultiPolygon")
        self.assertEqual(len(entry["geometry_sha256"]), 64)
        self.assertFalse(entry["publication_eligible"])
        self.assertFalse(entry["exact_pin_eligible"])

    def test_system_shared_across_source_claims_is_blocked(self):
        candidates = [
            self._candidate(claim="a", cemsid="100", system="Q001-SOCCER-1"),
            self._candidate(claim="b", cemsid="101", system="Q001-SOCCER-1", descriptor="Youth Soccer-01"),
        ]
        report = build_registry(self._report(candidates), [self._facility()])
        self.assertEqual(report["registry_entry_count"], 0)
        self.assertEqual(report["blocked_candidate_count"], 2)
        self.assertEqual(report["block_reason_counts"]["SYSTEM_SHARED_ACROSS_SOURCE_CLAIMS"], 2)

    def test_multiple_source_cemsids_are_blocked(self):
        candidate = self._candidate(claim="a", cemsid="100", system="Q001-SOCCER-1")
        candidate["source_cemsids"] = ["100", "101"]
        report = build_registry(self._report([candidate]), [self._facility()])
        self.assertEqual(report["registry_entry_count"], 0)
        self.assertEqual(report["block_reason_counts"]["SOURCE_CEMSID_NOT_SINGLE"], 1)

    def test_live_source_revalidation_blocks_inactive_or_wrong_geometry(self):
        candidate = self._candidate(claim="a", cemsid="100", system="Q001-SOCCER-1")
        facility = self._facility()
        facility["featurestatus"] = "Inactive"
        facility["multipolygon"] = {"type": "Point", "coordinates": [0, 0]}
        report = build_registry(self._report([candidate]), [facility])
        self.assertEqual(report["registry_entry_count"], 0)
        reasons = report["blocked"][0]["block_reasons"]
        self.assertIn("OFFICIAL_FEATURESTATUS_NOT_ACTIVE", reasons)
        self.assertIn("OFFICIAL_MULTIPOLYGON_REVALIDATION_FAILED", reasons)

    def test_refuses_v6_with_publication_authority(self):
        candidate = self._candidate(claim="a", cemsid="100", system="Q001-SOCCER-1")
        report = self._report([candidate])
        report["publication_eligible_count"] = 1
        with self.assertRaises(RuntimeError):
            build_registry(report, [self._facility()])


if __name__ == "__main__":
    unittest.main()
