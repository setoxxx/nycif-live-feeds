import unittest

from scripts.probe_parks_cems_facility_numbering_v4 import diagnose_claims


class ParksCemsFacilityNumberingV4Tests(unittest.TestCase):
    def test_unique_field_number_exact_sport_is_diagnostic_only(self):
        claims = {
            "B|belmont playground|basketball 01": {
                "borough_code": "B",
                "park_name": "Belmont Playground",
                "facility_descriptor": "Basketball-01",
                "field_number_token": "1",
                "occurrence_count": 3,
                "source_event_ids": ["one"],
                "source_cemsids": ["7056"],
            }
        }
        properties = [{"gispropnum": "B001", "borough": "B", "signname": "Belmont Playground"}]
        facilities = [{
            "gispropnum": "B001",
            "system": "SYS-1",
            "primary_sport": "Basketball",
            "field_number": "01",
            "multipolygon": {"type": "MultiPolygon", "coordinates": []},
        }]
        report = diagnose_claims(claims, properties, facilities)
        self.assertEqual(report["field_alignment_counts"]["UNIQUE_FIELD_NUMBER_EXACT_SPORT"], 1)
        self.assertEqual(report["unique_field_number_exact_sport_count"], 1)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertEqual(report["exact_pin_candidate_count"], 0)
        self.assertEqual(report["centroid_generated_count"], 0)
        self.assertEqual(report["point_generated_count"], 0)

    def test_unique_field_number_sport_mismatch_is_explicit(self):
        claims = {
            "B|belmont playground|soccer 01": {
                "borough_code": "B",
                "park_name": "Belmont Playground",
                "facility_descriptor": "Soccer-01",
                "field_number_token": "1",
                "occurrence_count": 1,
                "source_event_ids": ["one"],
                "source_cemsids": ["7056"],
            }
        }
        properties = [{"gispropnum": "B001", "borough": "B", "signname": "Belmont Playground"}]
        facilities = [{"gispropnum": "B001", "system": "SYS-1", "primary_sport": "Basketball", "field_number": "01"}]
        report = diagnose_claims(claims, properties, facilities)
        self.assertEqual(report["field_alignment_counts"]["UNIQUE_FIELD_NUMBER_SPORT_MISMATCH"], 1)
        self.assertEqual(report["unique_field_number_sport_mismatch_count"], 1)
        self.assertEqual(report["publication_eligible_count"], 0)

    def test_ambiguous_field_number_can_record_unique_exact_sport(self):
        claims = {
            "B|belmont playground|soccer 01": {
                "borough_code": "B",
                "park_name": "Belmont Playground",
                "facility_descriptor": "Soccer-01",
                "field_number_token": "1",
                "occurrence_count": 1,
                "source_event_ids": ["one"],
                "source_cemsids": ["7056"],
            }
        }
        properties = [{"gispropnum": "B001", "borough": "B", "signname": "Belmont Playground"}]
        facilities = [
            {"gispropnum": "B001", "system": "SYS-1", "primary_sport": "Soccer", "field_number": "01"},
            {"gispropnum": "B001", "system": "SYS-2", "primary_sport": "Basketball", "field_number": "01"},
        ]
        report = diagnose_claims(claims, properties, facilities)
        self.assertEqual(report["field_alignment_counts"]["AMBIGUOUS_FIELD_NUMBER_UNIQUE_EXACT_SPORT"], 1)
        self.assertEqual(report["ambiguous_field_number_unique_exact_sport_count"], 1)
        self.assertEqual(report["publication_eligible_count"], 0)


if __name__ == "__main__":
    unittest.main()
