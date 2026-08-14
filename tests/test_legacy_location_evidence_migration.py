import copy
import unittest

from scripts.legacy_location_evidence_migration import migrate_match, migration_decision


class LegacyLocationEvidenceMigrationTests(unittest.TestCase):
    def test_event_id_facility_match_becomes_candidate_not_certificate(self):
        raw = {
            "event_id": "123",
            "event_borough": "Manhattan",
            "event_location": "Central Park: East Meadow",
            "cemsid": ["456"],
        }
        match = {
            "source_event_id": "123",
            "borough": "Manhattan",
            "display_location": "Central Park: East Meadow",
            "lat": 40.772148,
            "lng": -73.977782,
        }
        original = copy.deepcopy(match)
        migrated, decision = migrate_match(raw, "event_id", match)
        self.assertFalse(decision["eligible"])
        self.assertTrue(decision["candidate"])
        self.assertEqual(decision["candidate_tier"], "certified_facility")
        self.assertEqual(decision["reason_code"], "FACILITY_SITE_VALIDATION_REQUIRED")
        self.assertEqual(decision["facility_ids"], ["456"])
        self.assertEqual(migrated, original)
        self.assertNotIn("location_evidence", migrated)
        self.assertEqual(match, original)

    def test_location_cache_requires_allowlisted_provenance(self):
        raw = {
            "event_id": "123",
            "event_borough": "Brooklyn",
            "event_location": "100 Main Street",
        }
        base = {
            "borough": "Brooklyn",
            "display_location": raw["event_location"],
            "lat": 40.65,
            "lng": -73.95,
        }
        rejected = migration_decision(raw, "location_cache", dict(base, source="unknown"))
        self.assertFalse(rejected["eligible"])
        self.assertFalse(rejected["candidate"])
        self.assertEqual(rejected["reason_code"], "LEGACY_PROVENANCE_NOT_ALLOWLISTED")

        accepted = migration_decision(
            raw,
            "location_cache",
            dict(base, source="existing_enriched_feed_gps"),
        )
        self.assertFalse(accepted["eligible"])
        self.assertTrue(accepted["candidate"])
        self.assertEqual(accepted["candidate_tier"], "exact_address")
        self.assertEqual(accepted["reason_code"], "ADDRESS_CANONICAL_RERESOLUTION_REQUIRED")

    def test_legacy_street_segment_requires_canonical_reresolution(self):
        raw = {
            "event_id": "123",
            "event_borough": "Brooklyn",
            "event_location": "EAST 10 STREET between AVENUE A and AVENUE B",
        }
        match = {
            "source_event_id": "123",
            "borough": "Brooklyn",
            "display_location": raw["event_location"],
            "lat": 40.65,
            "lng": -73.95,
            "source": "existing_enriched_feed_gps",
        }
        decision = migration_decision(raw, "event_id", match)
        self.assertFalse(decision["eligible"])
        self.assertTrue(decision["candidate"])
        self.assertEqual(decision["candidate_tier"], "certified_street_segment")
        self.assertEqual(
            decision["reason_code"],
            "STREET_SEGMENT_REQUIRES_CANONICAL_RERESOLUTION",
        )

    def test_location_text_mismatch_stays_blocked(self):
        raw = {
            "event_id": "123",
            "event_borough": "Queens",
            "event_location": "100 Main Street",
        }
        match = {
            "source_event_id": "123",
            "borough": "Queens",
            "display_location": "200 Other Street",
            "lat": 40.74,
            "lng": -73.84,
        }
        decision = migration_decision(raw, "event_id", match)
        self.assertFalse(decision["eligible"])
        self.assertFalse(decision["candidate"])
        self.assertEqual(decision["reason_code"], "CURRENT_LOCATION_TEXT_MISMATCH")

    def test_event_id_mismatch_stays_blocked(self):
        raw = {
            "event_id": "123",
            "event_borough": "Queens",
            "event_location": "100 Main Street",
        }
        match = {
            "source_event_id": "999",
            "borough": "Queens",
            "display_location": "100 Main Street",
            "lat": 40.74,
            "lng": -73.84,
        }
        decision = migration_decision(raw, "event_id", match)
        self.assertFalse(decision["eligible"])
        self.assertFalse(decision["candidate"])
        self.assertEqual(decision["reason_code"], "SOURCE_EVENT_ID_MISMATCH")

    def test_borough_coordinate_contradiction_stays_blocked(self):
        raw = {
            "event_id": "123",
            "event_borough": "Bronx",
            "event_location": "100 Main Street",
        }
        match = {
            "source_event_id": "123",
            "borough": "Bronx",
            "display_location": "100 Main Street",
            "lat": 40.58,
            "lng": -74.15,
        }
        decision = migration_decision(raw, "event_id", match)
        self.assertFalse(decision["eligible"])
        self.assertFalse(decision["candidate"])
        self.assertEqual(decision["reason_code"], "CURRENT_BOROUGH_COORDINATE_MISMATCH")

    def test_general_venue_without_exact_claim_stays_blocked(self):
        raw = {
            "event_id": "123",
            "event_borough": "Manhattan",
            "event_location": "Some Plaza",
        }
        match = {
            "source_event_id": "123",
            "borough": "Manhattan",
            "display_location": "Some Plaza",
            "lat": 40.75,
            "lng": -73.98,
        }
        decision = migration_decision(raw, "event_id", match)
        self.assertFalse(decision["eligible"])
        self.assertFalse(decision["candidate"])
        self.assertEqual(decision["reason_code"], "CURRENT_LOCATION_CLAIM_NOT_EXACT_TIER")

    def test_secondary_match_classes_are_not_in_wave_one(self):
        raw = {
            "event_id": "123",
            "event_borough": "Manhattan",
            "event_location": "100 Main Street",
        }
        match = {
            "borough": "Manhattan",
            "display_location": "100 Main Street",
            "lat": 40.75,
            "lng": -73.98,
        }
        for match_type in ("cemsid", "text_date_location", "tier_1_gazetteer_display"):
            with self.subTest(match_type=match_type):
                decision = migration_decision(raw, match_type, match)
                self.assertFalse(decision["eligible"])
                self.assertFalse(decision["candidate"])
                self.assertEqual(decision["reason_code"], "MATCH_CLASS_NOT_MIGRATABLE")


if __name__ == "__main__":
    unittest.main()
