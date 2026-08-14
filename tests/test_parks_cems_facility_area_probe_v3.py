import unittest

from scripts.probe_parks_cems_facility_area_v3 import audit_claims, borough_code


class ParksCemsFacilityAreaProbeV3Tests(unittest.TestCase):
    def test_borough_aliases(self):
        self.assertEqual(borough_code("Manhattan"), "M")
        self.assertEqual(borough_code("Brooklyn"), "B")
        self.assertEqual(borough_code("Queens"), "Q")
        self.assertEqual(borough_code("Bronx"), "X")
        self.assertEqual(borough_code("Staten Island"), "R")

    def test_unique_property_and_facility_match_is_area_evidence_only(self):
        claims = {
            "b|belmont playground|basketball 01": {
                "borough_code": "B",
                "park_name": "Belmont Playground",
                "facility_descriptor": "Basketball-01",
                "field_number_token": "1",
                "occurrence_count": 3,
                "source_event_ids": ["one"],
                "source_cemsids": ["7056"],
            }
        }
        properties = [{"gispropnum": "B123", "signname": "Belmont Playground"}]
        facilities = [
            {
                "gispropnum": "B123",
                "primary_sport": "Basketball",
                "field_number": "01",
                "system": "SYS-1",
                "multipolygon": {"type": "MultiPolygon", "coordinates": []},
            }
        ]
        report = audit_claims(claims, properties, facilities)
        self.assertEqual(report["property_resolved_claim_count"], 1)
        self.assertEqual(report["facility_area_candidate_count"], 1)
        self.assertEqual(report["facility_area_candidates_with_geometry"], 1)
        self.assertEqual(report["occurrence_coverage_by_facility_area_candidates"], 3)
        self.assertEqual(report["publication_eligible_count"], 0)
        self.assertEqual(report["exact_pin_candidate_count"], 0)
        self.assertEqual(report["centroid_generated_count"], 0)
        self.assertEqual(report["point_generated_count"], 0)
        match = report["matches"][0]
        self.assertEqual(match["disposition"], "UNIQUE_OFFICIAL_PROPERTY_AND_FACILITY_AREA")
        self.assertFalse(match["official_match"]["centroid_generated"])
        self.assertFalse(match["official_match"]["point_generated"])

    def test_duplicate_property_match_remains_ambiguous(self):
        claims = {
            "b|same park|basketball 01": {
                "borough_code": "B",
                "park_name": "Same Park",
                "facility_descriptor": "Basketball-01",
                "field_number_token": "1",
                "occurrence_count": 1,
                "source_event_ids": [],
                "source_cemsids": [],
            }
        }
        properties = [
            {"gispropnum": "B001", "signname": "Same Park"},
            {"gispropnum": "B002", "signname": "Same Park"},
        ]
        report = audit_claims(claims, properties, [])
        self.assertEqual(report["facility_area_candidate_count"], 0)
        self.assertEqual(report["disposition_counts"]["AMBIGUOUS_PROPERTY_GISPROPNUM"], 1)

    def test_same_property_wrong_field_does_not_match(self):
        claims = {
            "q|park|soccer 02": {
                "borough_code": "Q",
                "park_name": "Park",
                "facility_descriptor": "Soccer-02",
                "field_number_token": "2",
                "occurrence_count": 1,
                "source_event_ids": [],
                "source_cemsids": [],
            }
        }
        properties = [{"gispropnum": "Q001", "signname": "Park"}]
        facilities = [{"gispropnum": "Q001", "primary_sport": "Soccer", "field_number": "03", "system": "S"}]
        report = audit_claims(claims, properties, facilities)
        self.assertEqual(report["facility_area_candidate_count"], 0)
        self.assertEqual(report["disposition_counts"]["PROPERTY_RESOLVED_NO_EXACT_SPORT_FIELD_MATCH"], 1)


if __name__ == "__main__":
    unittest.main()
