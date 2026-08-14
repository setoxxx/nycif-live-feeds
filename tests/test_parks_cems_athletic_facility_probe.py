import unittest

from scripts.probe_parks_cems_athletic_facilities import (
    audit_claims,
    current_parks_claims,
    facility_descriptor,
)


class ParksCemsAthleticFacilityProbeTests(unittest.TestCase):
    def test_descriptor_extracts_sport_and_field_number(self):
        self.assertEqual(facility_descriptor("Basketball-01"), ("basketball", "1"))
        self.assertEqual(facility_descriptor("Soccer-02-Stanton St"), ("soccer", "2"))

    def test_current_claims_deduplicate_recurring_permits(self):
        rows = [
            {
                "event_id": "one",
                "event_agency": "Parks Department",
                "event_location": "Belmont Playground: Basketball-01",
                "start_date_time": "2026-08-20T10:00:00",
                "cemsid": ["7056"],
            },
            {
                "event_id": "two",
                "event_agency": "Parks Department",
                "event_location": "Belmont Playground: Basketball-01",
                "start_date_time": "2026-08-21T10:00:00",
                "cemsid": ["7056"],
            },
        ]
        claims = current_parks_claims(rows, "2026-08-13")
        self.assertEqual(len(claims), 1)
        claim = next(iter(claims.values()))
        self.assertEqual(claim["occurrence_count"], 2)
        self.assertEqual(claim["source_cemsids"], ["7056"])

    def test_probe_requires_unique_exact_park_sport_and_number_tokens(self):
        claims = {
            "belmont|basketball": {
                "park_name": "Belmont Playground",
                "facility_descriptor": "Basketball-01",
                "sport_token": "basketball",
                "field_number_token": "1",
                "occurrence_count": 4,
                "source_event_ids": ["one"],
                "source_cemsids": ["7056"],
            },
            "other|soccer": {
                "park_name": "Other Park",
                "facility_descriptor": "Soccer-02",
                "sport_token": "soccer",
                "field_number_token": "2",
                "occurrence_count": 1,
                "source_event_ids": ["two"],
                "source_cemsids": ["999"],
            },
        }
        facilities = [
            {
                "signname": "Belmont Playground",
                "primary_sport": "Basketball",
                "field_number": "01",
                "system": "SYS-1",
                "gispropnum": "X001",
                "multipolygon": {"type": "MultiPolygon", "coordinates": []},
            }
        ]
        report = audit_claims(claims, facilities)
        self.assertEqual(report["unique_tvpp_facility_claims"], 2)
        self.assertEqual(report["unique_deterministic_matches"], 1)
        self.assertEqual(report["occurrence_coverage_by_unique_matches"], 4)
        self.assertEqual(report["disposition_counts"]["UNIQUE_EXACT_TOKENS"], 1)
        self.assertEqual(report["disposition_counts"]["PARK_NAME_NOT_FOUND"], 1)
        self.assertFalse(report["promotion_allowed"])
        matched = next(item for item in report["matches"] if item["disposition"] == "UNIQUE_EXACT_TOKENS")
        self.assertEqual(matched["official_match"]["official_system_id"], "SYS-1")
        self.assertTrue(matched["official_match"]["geometry_present"])


if __name__ == "__main__":
    unittest.main()
