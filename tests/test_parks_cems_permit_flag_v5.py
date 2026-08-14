import unittest

from scripts.probe_parks_cems_permit_flag_v5 import probe_claims


class ParksCemsPermitFlagV5Tests(unittest.TestCase):
    def test_permit_flag_disambiguates_same_number_rows_but_stays_nonpublic(self):
        claims = {
            "B|sample park|basketball 01": {
                "borough_code": "B",
                "park_name": "Sample Park",
                "facility_descriptor": "Basketball-01",
                "field_number_token": "1",
                "occurrence_count": 3,
                "source_event_ids": ["e1"],
                "source_cemsids": ["100"],
            }
        }
        properties = [{"gispropnum": "B001", "borough": "B", "signname": "Sample Park"}]
        facilities = [
            {
                "gispropnum": "B001",
                "field_number": "01",
                "system": "B001-BASKETBALL-1",
                "primary_sport": "BKB",
                "basketball": True,
                "multipolygon": {"type": "MultiPolygon", "coordinates": []},
            },
            {
                "gispropnum": "B001",
                "field_number": "01",
                "system": "B001-HANDBALL-1",
                "primary_sport": "HDB",
                "handball": True,
                "multipolygon": {"type": "MultiPolygon", "coordinates": []},
            },
        ]
        report = probe_claims(claims, properties, facilities)
        self.assertEqual(report["unique_permitted_area_candidate_count"], 1)
        self.assertEqual(report["occurrence_coverage_by_unique_permitted_area_candidates"], 3)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertEqual(report["exact_pin_candidate_count"], 0)
        self.assertEqual(report["centroid_generated_count"], 0)
        self.assertEqual(report["point_generated_count"], 0)
        matched = report["matches"][0]
        self.assertEqual(matched["disposition"], "UNIQUE_FIELD_NUMBER_AND_PERMITTED_SPORT_AREA")
        self.assertEqual(matched["official_match"]["official_system_id"], "B001-BASKETBALL-1")
        self.assertEqual(matched["official_match"]["matched_permit_fields"], ["basketball"])

    def test_multiple_permitted_rows_remain_ambiguous(self):
        claims = {
            "B|sample park|soccer 01": {
                "borough_code": "B",
                "park_name": "Sample Park",
                "facility_descriptor": "Soccer-01",
                "field_number_token": "1",
                "occurrence_count": 1,
                "source_event_ids": ["e1"],
                "source_cemsids": ["100"],
            }
        }
        properties = [{"gispropnum": "B001", "borough": "B", "signname": "Sample Park"}]
        facilities = [
            {"gispropnum": "B001", "field_number": "01", "system": "one", "regulation_soccer": True},
            {"gispropnum": "B001", "field_number": "01", "system": "two", "nonregulation_soccer": True},
        ]
        report = probe_claims(claims, properties, facilities)
        self.assertEqual(report["disposition_counts"]["AMBIGUOUS_MULTIPLE_PERMITTED_FACILITY_ROWS"], 1)
        self.assertEqual(report["unique_permitted_area_candidate_count"], 0)

    def test_false_or_missing_permit_flag_does_not_match(self):
        claims = {
            "B|sample park|tennis 01": {
                "borough_code": "B",
                "park_name": "Sample Park",
                "facility_descriptor": "Tennis-01",
                "field_number_token": "1",
                "occurrence_count": 1,
                "source_event_ids": ["e1"],
                "source_cemsids": ["100"],
            }
        }
        properties = [{"gispropnum": "B001", "borough": "B", "signname": "Sample Park"}]
        facilities = [{"gispropnum": "B001", "field_number": "01", "system": "one", "tennis": False}]
        report = probe_claims(claims, properties, facilities)
        self.assertEqual(report["disposition_counts"]["FIELD_NUMBER_ROWS_BUT_SPORT_NOT_PERMITTED"], 1)
        self.assertEqual(report["unique_permitted_area_candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
