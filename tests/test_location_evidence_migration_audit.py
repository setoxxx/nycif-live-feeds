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

    def test_audit_accounts_every_row_without_promotion(self):
        rows = [
            {"id": "one", "start_date_time": "2026-08-13T10:00:00"},
            {"id": "two", "start_date_time": "2026-08-13T12:00:00"},
        ]
        explicit = {
            "lat": 40.72,
            "lng": -73.98,
            "location_evidence": {
                "tier": "exact_source_coordinate",
                "validation_state": "validated",
                "exact_pin_eligible": True,
                "source_provenance": "official-open-data",
            },
        }
        legacy = {"lat": 40.73, "lng": -73.99}

        import scripts.audit_location_evidence_migration as audit
        original_build_indexes = audit.enrich.build_indexes
        original_find_match = audit.enrich.find_match
        try:
            audit.enrich.build_indexes = lambda enriched: {}
            answers = iter([("event_id", explicit), ("location_cache", legacy)])
            audit.enrich.find_match = lambda raw, indexes, cache, resolver: next(answers)
            before = repr(rows)
            report = audit_rows(rows, [], {}, FakeResolver())
            self.assertEqual(report["input_rows"], 2)
            self.assertEqual(report["accounted_rows"], 2)
            self.assertEqual(report["silent_loss_count"], 0)
            self.assertEqual(report["migration_debt_count"], 1)
            self.assertEqual(report["bucket_counts"]["READY_EXPLICIT_EVIDENCE"], 1)
            self.assertEqual(report["bucket_counts"]["MIGRATION_DEBT_LEGACY_COORDINATES"], 1)
            self.assertFalse(report["promotion_allowed"])
            self.assertEqual(repr(rows), before)
        finally:
            audit.enrich.build_indexes = original_build_indexes
            audit.enrich.find_match = original_find_match


if __name__ == "__main__":
    unittest.main()
