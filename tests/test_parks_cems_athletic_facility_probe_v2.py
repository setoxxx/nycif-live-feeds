import unittest

from scripts.probe_parks_cems_athletic_facilities_v2 import audit_claims


class ParksCemsAthleticFacilityProbeV2Tests(unittest.TestCase):
    def claim(self, *, cemsid="7056", sport="basketball", number="1", occurrences=3):
        return {
            "park_name": "Belmont Playground",
            "facility_descriptor": "Basketball-01",
            "sport_token": sport,
            "field_number_token": number,
            "occurrence_count": occurrences,
            "source_event_ids": ["one"],
            "source_cemsids": [cemsid],
        }

    def facility(self, *, system="7056", sport="Basketball", number="01", geometry=True):
        row = {
            "system": system,
            "primary_sport": sport,
            "field_number": number,
            "gispropnum": "X001",
        }
        if geometry:
            row["multipolygon"] = {"type": "MultiPolygon", "coordinates": []}
        return row

    def test_unique_identifier_match_is_candidate_not_publication_authority(self):
        report = audit_claims({"belmont": self.claim()}, [self.facility()])
        self.assertEqual(report["identifier_candidate_count"], 1)
        self.assertEqual(report["descriptor_consistent_identifier_candidates"], 1)
        self.assertEqual(report["identifier_candidates_with_geometry"], 1)
        self.assertEqual(report["occurrence_coverage_by_identifier_candidates"], 3)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertFalse(report["promotion_allowed"])
        self.assertEqual(
            report["disposition_counts"]["CEMSID_SYSTEM_UNIQUE_DESCRIPTOR_CONSISTENT"],
            1,
        )

    def test_descriptor_conflict_remains_explicit(self):
        report = audit_claims(
            {"belmont": self.claim(sport="soccer")},
            [self.facility(sport="Basketball")],
        )
        self.assertEqual(report["identifier_candidate_count"], 1)
        self.assertEqual(report["descriptor_conflict_identifier_candidates"], 1)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertEqual(
            report["disposition_counts"]["CEMSID_SYSTEM_UNIQUE_DESCRIPTOR_CONFLICT"],
            1,
        )

    def test_duplicate_official_system_value_is_ambiguous(self):
        report = audit_claims(
            {"belmont": self.claim()},
            [self.facility(), self.facility(number="02")],
        )
        self.assertEqual(report["duplicate_official_system_value_count"], 1)
        self.assertEqual(report["identifier_candidate_count"], 0)
        self.assertEqual(report["disposition_counts"]["AMBIGUOUS_CEMSID_SYSTEM_ROWS"], 1)
        self.assertEqual(report["publication_eligible_count"], 0)

    def test_unknown_cemsid_stays_unmatched(self):
        report = audit_claims({"unknown": self.claim(cemsid="9999")}, [self.facility()])
        self.assertEqual(report["identifier_candidate_count"], 0)
        self.assertEqual(report["disposition_counts"]["CEMSID_SYSTEM_NOT_FOUND"], 1)
        self.assertEqual(report["publication_eligible_count"], 0)


if __name__ == "__main__":
    unittest.main()
