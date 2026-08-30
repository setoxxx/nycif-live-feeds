import unittest

from scripts.classify_unresolved_location_backlog_v1 import build, classify


class UnresolvedLocationBacklogTests(unittest.TestCase):
    def row(self, **overrides):
        base = {
            "title": "Example event",
            "event_role": "public_event",
            "parent_event_id": None,
            "start_date_time": "2026-08-30T12:00:00-04:00",
            "borough": "Brooklyn",
            "event_location": "Example Place",
            "source": {"dataset": "fixture", "source_event_id": "1"},
            "nycif": {"map_eligibility_state": "LIST_ONLY", "display_disposition": "list_only"},
        }
        base.update(overrides)
        return base

    def test_cemsid_precedes_generic_named_place(self):
        row = self.row(source={"dataset": "fixture", "source_event_id": "1", "source_cemsid": "ABC123"})
        self.assertEqual(classify(row)[0], "CEMSID")

    def test_route_is_never_point_bucket(self):
        row = self.row(event_location="18th Avenue between 65th Street and 75th Street")
        self.assertEqual(classify(row)[0], "ROUTE_OR_STREET_SEGMENT")

    def test_park_subfacility(self):
        row = self.row(event_location="Marine Park: Lawn (Fillmore Avenue)")
        self.assertEqual(classify(row)[0], "PARK_SUBFACILITY")

    def test_exact_address(self):
        row = self.row(event_location="95 Cozine Avenue")
        self.assertEqual(classify(row)[0], "EXACT_ADDRESS")

    def test_borough_only(self):
        row = self.row(event_location="Brooklyn")
        self.assertEqual(classify(row)[0], "BOROUGH_ONLY")

    def test_build_excludes_exact_and_approximate(self):
        unresolved = self.row()
        exact = self.row(source={"dataset": "fixture", "source_event_id": "2"}, nycif={"map_eligibility_state": "MAP_READY", "display_disposition": "standalone_public_event", "certified_pin": True})
        approximate = self.row(source={"dataset": "fixture", "source_event_id": "3"}, nycif={"map_eligibility_state": "GENERAL_AREA", "display_disposition": "approximate_marker", "certified_pin": False})
        items, report = build([unresolved, exact, approximate])
        self.assertEqual(len(items), 1)
        self.assertEqual(report["eligible_unresolved_count"], 1)
        self.assertTrue(report["qa_pass"])
        self.assertFalse(items[0]["promotion_allowed"])
        self.assertFalse(items[0]["public_map_modified"])
        self.assertFalse(items[0]["location_cache_modified"])

    def test_duplicate_occurrence_fails_closed(self):
        a = self.row()
        b = self.row()
        _items, report = build([a, b])
        self.assertEqual(report["duplicate_occurrence_count"], 1)
        self.assertFalse(report["qa_pass"])


if __name__ == "__main__":
    unittest.main()
