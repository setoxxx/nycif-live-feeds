import unittest

from scripts.probe_parks_cems_strict_facility_area_v6 import (
    canonical_field_id,
    parse_descriptor,
    probe_claims,
)


class ParksCemsStrictFacilityAreaV6Tests(unittest.TestCase):
    def test_adjacent_sport_field_pair_ignores_subfacility_number(self):
        self.assertEqual(parse_descriptor("Dyker Bay 8-Baseball-01"), ("PARSED", "baseball", "1"))

    def test_suffix_is_preserved(self):
        self.assertEqual(canonical_field_id("01A"), "1A")
        self.assertEqual(parse_descriptor("Softball-01A"), ("PARSED", "softball", "1A"))

    def test_composite_descriptor_is_rejected(self):
        state, sport, field_id = parse_descriptor(
            "Basketball-01   ,Example Park: Basketball-02"
        )
        self.assertEqual(state, "COMPOSITE_LOCATION_DESCRIPTOR")
        self.assertFalse(sport)
        self.assertFalse(field_id)

    def test_multiple_sports_are_rejected(self):
        state, _, _ = parse_descriptor("Dust Bowl - Soccer/Football-01")
        self.assertEqual(state, "MULTIPLE_SPORT_FAMILIES")

    def test_unique_active_permitted_area_is_evidence_only(self):
        claims = {
            "q": {
                "borough_code": "Q",
                "park_name": "Example Park",
                "facility_descriptor": "Fields 8-Baseball-01A",
                "occurrence_count": 4,
                "source_event_ids": ["x"],
                "source_cemsids": ["999"],
            }
        }
        properties = [{"gispropnum": "Q001", "signname": "Example Park"}]
        facilities = [
            {
                "gispropnum": "Q001",
                "system": "Q001-BASEBALL-1A",
                "field_number": "01A",
                "featurestatus": "Active",
                "adult_baseball": True,
                "primary_sport": "BSB",
                "multipolygon": {"type": "MultiPolygon", "coordinates": []},
            }
        ]
        report = probe_claims(claims, properties, facilities)
        self.assertEqual(report["strict_facility_area_candidate_count"], 1)
        self.assertEqual(report["strict_occurrence_coverage"], 4)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertEqual(report["exact_pin_candidate_count"], 0)
        self.assertEqual(report["centroid_generated_count"], 0)
        self.assertEqual(report["point_generated_count"], 0)

    def test_inactive_row_is_blocked(self):
        claims = {
            "b": {
                "borough_code": "B",
                "park_name": "Example Park",
                "facility_descriptor": "Basketball-01",
                "occurrence_count": 1,
                "source_event_ids": [],
                "source_cemsids": [],
            }
        }
        properties = [{"gispropnum": "B001", "signname": "Example Park"}]
        facilities = [
            {
                "gispropnum": "B001",
                "system": "B001-BASKETBALL-1",
                "field_number": "01",
                "featurestatus": "Inactive",
                "basketball": True,
                "multipolygon": {"type": "MultiPolygon", "coordinates": []},
            }
        ]
        report = probe_claims(claims, properties, facilities)
        self.assertEqual(report["strict_facility_area_candidate_count"], 0)
        self.assertEqual(report["disposition_counts"]["UNIQUE_ROW_NOT_ACTIVE"], 1)


if __name__ == "__main__":
    unittest.main()
