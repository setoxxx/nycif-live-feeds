import unittest

from scripts.build_location_resolution_backlog_v1 import build, classify_row


class LocationResolutionBacklogV1Tests(unittest.TestCase):
    def row(self, **overrides):
        row = {
            "title": "Fixture Event",
            "start_date_time": "2026-08-30T12:00:00-04:00",
            "event_role": "public_event",
            "parent_event_id": None,
            "borough": "Brooklyn",
            "event_location": "Fixture Place",
            "source": {"dataset": "fixture", "source_event_id": "1"},
            "nycif": {"map_eligibility_state": "LIST_ONLY", "display_disposition": "list_only"},
        }
        row.update(overrides)
        return row

    def test_route_stays_route(self):
        bucket, _ = classify_row(self.row(event_location="18th Avenue between 65th Street and 75th Street"))
        self.assertEqual(bucket, "ROUTE_OR_STREET_SEGMENT")

    def test_ordinal_street_without_house_number_is_not_exact_address(self):
        bucket, evidence = classify_row(self.row(event_location="18th Avenue"))
        self.assertEqual(bucket, "ROUTE_OR_STREET_SEGMENT")
        self.assertIn("ordinal_street_without_house_number", evidence)

    def test_cemsid_bucket(self):
        bucket, _ = classify_row(self.row(source={"dataset": "fixture", "source_event_id": "1", "source_cemsid": "C123"}))
        self.assertEqual(bucket, "CEMSID")

    def test_park_subfacility_bucket(self):
        bucket, _ = classify_row(self.row(event_location="Marine Park: Lawn (Fillmore Avenue)"))
        self.assertEqual(bucket, "PARK_SUBFACILITY")

    def test_address_bucket(self):
        bucket, _ = classify_row(self.row(event_location="95 Cozine Avenue"))
        self.assertEqual(bucket, "EXACT_ADDRESS")

    def test_borough_only_bucket(self):
        bucket, _ = classify_row(self.row(event_location="Brooklyn"))
        self.assertEqual(bucket, "BOROUGH_ONLY")

    def test_exact_and_approximate_are_excluded(self):
        exact = self.row(source={"dataset": "fixture", "source_event_id": "2"}, nycif={"map_eligibility_state": "MAP_READY", "display_disposition": "standalone_public_event", "certified_pin": True})
        approximate = self.row(source={"dataset": "fixture", "source_event_id": "3"}, nycif={"map_eligibility_state": "GENERAL_AREA", "display_disposition": "approximate_marker", "certified_pin": False})
        queue, report = build([self.row(), exact, approximate], expected_state_counts={"MAP_READY": 1, "GENERAL_AREA": 1, "LIST_ONLY": 1, "REVIEW_REQUIRED": 0})
        self.assertEqual(len(queue), 1)
        self.assertEqual(report["unresolved_canonical_occurrence_count"], 1)
        self.assertEqual(report["unresolved_public_occurrence_count"], 1)
        self.assertTrue(report["qa_pass"])
        self.assertEqual(report["promotion_attempt_count"], 0)
        self.assertFalse(report["public_map_modified"])
        self.assertFalse(report["location_cache_modified"])
        self.assertFalse(report["staged_feed_modified"])

    def test_nonpublic_unresolved_is_classified_but_labeled(self):
        support = self.row(
            source={"dataset": "fixture", "source_event_id": "support"},
            event_role="supporting_permit",
            nycif={"map_eligibility_state": "LIST_ONLY", "display_disposition": "grouped_under_public_event"},
        )
        queue, report = build([support], expected_state_counts={"LIST_ONLY": 1, "REVIEW_REQUIRED": 0})
        self.assertEqual(len(queue), 1)
        self.assertFalse(queue[0]["reader_public"])
        self.assertEqual(report["unresolved_public_occurrence_count"], 0)
        self.assertEqual(report["unresolved_nonpublic_occurrence_count"], 1)
        self.assertTrue(report["qa_pass"])

    def test_missing_state_defaults_to_review_required_like_v3_status_builder(self):
        fixture = self.row(nycif={"display_disposition": "list_only"})
        queue, report = build([fixture], expected_state_counts={"LIST_ONLY": 0, "REVIEW_REQUIRED": 1})
        self.assertEqual(queue[0]["current_map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertTrue(report["canonical_state_count_matches_v3_status"])

    def test_cancelled_title_is_suppressed_but_state_count_still_reconciles(self):
        queue, report = build(
            [self.row(title="CANCELED: Fixture")],
            expected_state_counts={"LIST_ONLY": 1, "REVIEW_REQUIRED": 0},
        )
        self.assertEqual(queue, [])
        self.assertEqual(report["cancelled_unresolved_suppressed"], 1)
        self.assertEqual(report["unresolved_canonical_before_cancel_suppression"], 1)
        self.assertTrue(report["qa_pass"])

    def test_duplicate_identity_fails_closed(self):
        queue, report = build([self.row(), self.row()], expected_state_counts={"LIST_ONLY": 2, "REVIEW_REQUIRED": 0})
        self.assertEqual(len(queue), 1)
        self.assertEqual(report["duplicate_occurrence_count"], 1)
        self.assertFalse(report["qa_pass"])

    def test_v3_state_count_drift_fails_closed(self):
        _queue, report = build([self.row()], expected_state_counts={"LIST_ONLY": 2, "REVIEW_REQUIRED": 0})
        self.assertFalse(report["canonical_state_count_matches_v3_status"])
        self.assertFalse(report["qa_pass"])


if __name__ == "__main__":
    unittest.main()
