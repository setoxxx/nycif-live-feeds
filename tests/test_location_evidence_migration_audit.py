import unittest

from scripts.audit_location_evidence_migration import audit_rows, classification


class FakeResolver:
    def __init__(self):
        self._live_calls = 0


class LocationEvidenceMigrationAuditTests(unittest.TestCase):
    def test_classifies_explicit_ready_evidence(self):
        match = {
            "lat": 40.72,
            "lng": -73.98,
            "location_evidence": {
                "tier": "exact_source_coordinate",
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": "official-open-data",
            },
        }
        self.assertEqual(classification("event_id", match), "READY_EXPLICIT_EVIDENCE")

    def test_classifies_legacy_coordinate_as_migration_debt(self):
        match = {"lat": 40.72, "lng": -73.98, "display_location": "Test location"}
        self.assertEqual(classification("location_cache", match), "MIGRATION_DEBT_LEGACY_COORDINATES")

    def test_no_match_is_unresolved(self):
        self.assertEqual(classification("none", None), "UNRESOLVED_NO_MATCH")

    def test_audit_keeps_ready_candidate_and_new_eligibility_disjoint(self):
        rows = [
            {
                "id": "one",
                "event_id": "one",
                "event_borough": "Manhattan",
                "event_location": "1 Centre Street",
                "event_agency": "Test Agency",
                "start_date_time": "2026-08-13T10:00:00",
            },
            {
                "id": "two",
                "event_id": "two",
                "event_borough": "Brooklyn",
                "event_location": "100 Main Street",
                "event_agency": "Test Agency",
                "start_date_time": "2026-08-13T12:00:00",
            },
        ]
        explicit = {
            "source_event_id": "one",
            "display_location": "1 Centre Street",
            "lat": 40.72,
            "lng": -73.98,
            "location_evidence": {
                "tier": "exact_source_coordinate",
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": "official-open-data",
            },
        }
        legacy = {
            "borough": "Brooklyn",
            "display_location": "100 Main Street",
            "lat": 40.65,
            "lng": -73.95,
            "source": "existing_enriched_feed_gps",
        }

        import scripts.audit_location_evidence_migration as audit
        original_build_indexes = audit.enrich.build_indexes
        original_find_match = audit.enrich.find_match
        try:
            audit.enrich.build_indexes = lambda enriched: {}
            answers = iter([("event_id", explicit), ("location_cache", legacy)])
            audit.enrich.find_match = lambda raw, indexes, cache, resolver: next(answers)
            before = repr(rows)
            report = audit_rows(rows, [], {}, FakeResolver())
            self.assertEqual(report["schema_version"], "NYCIF_LOCATION_EVIDENCE_MIGRATION_AUDIT_V3")
            self.assertEqual(report["input_rows"], 2)
            self.assertEqual(report["accounted_rows"], 2)
            self.assertEqual(report["silent_loss_count"], 0)
            self.assertEqual(report["migration_debt_count"], 1)
            self.assertEqual(report["bucket_counts"]["READY_EXPLICIT_EVIDENCE"], 1)
            self.assertEqual(report["bucket_counts"]["MIGRATION_DEBT_LEGACY_COORDINATES"], 1)
            self.assertEqual(report["already_ready_explicit_evidence_count"], 1)
            self.assertEqual(report["recovery_candidate_count"], 1)
            self.assertEqual(report["recovery_candidate_tier_counts"], {"exact_address": 1})
            self.assertEqual(report["recovery_candidate_agency_counts"], {"Test Agency": 1})
            self.assertEqual(report["unique_recovery_claim_count"], 1)
            self.assertEqual(report["unique_recovery_claim_tier_counts"], {"exact_address": 1})
            self.assertEqual(report["migration_new_publication_eligible_count"], 0)
            self.assertEqual(report["publication_ready_total_count"], 1)
            self.assertEqual(report["wave1_migration_eligible_count"], 0)
            self.assertFalse(report["promotion_allowed"])
            self.assertEqual(repr(rows), before)
        finally:
            audit.enrich.build_indexes = original_build_indexes
            audit.enrich.find_match = original_find_match


if __name__ == "__main__":
    unittest.main()
