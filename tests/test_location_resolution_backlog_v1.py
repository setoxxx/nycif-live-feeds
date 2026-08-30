import unittest

from scripts.build_location_resolution_backlog_v1 import classify_row, build


def row(location="Brooklyn", **extra):
    base = {
        "title": "Test event",
        "start_date_time": "2026-08-30T18:00:00-04:00",
        "borough": "Brooklyn",
        "event_location": location,
        "source": {"dataset": "fixture", "source_event_id": "1"},
        "nycif": {"map_eligibility_state": "LIST_ONLY", "display_disposition": "list_only"},
    }
    base.update(extra)
    return base


class ClassifierTests(unittest.TestCase):
    def test_cemsid_wins(self):
        r = row("Marine Park: Lawn", source={"dataset": "fixture", "source_event_id": "1", "source_cemsid": "123"})
        self.assertEqual(classify_row(r)[0], "CEMSID")

    def test_exact_address(self):
        self.assertEqual(classify_row(row("95 Cozine Avenue"))[0], "EXACT_ADDRESS")

    def test_intersection(self):
        self.assertEqual(classify_row(row("Atlantic Avenue and Flatbush Avenue"))[0], "INTERSECTION")

    def test_route(self):
        self.assertEqual(classify_row(row("18th Avenue from 65th Street to 75th Street"))[0], "ROUTE_OR_STREET_SEGMENT")

    def test_park_subfacility(self):
        self.assertEqual(classify_row(row("Marine Park: Lawn (Fillmore Avenue)"))[0], "PARK_SUBFACILITY")

    def test_sports_field(self):
        self.assertEqual(classify_row(row("Owl Hollow Soccer Field 2"))[0], "SPORTS_FIELD")

    def test_borough_only(self):
        self.assertEqual(classify_row(row("Brooklyn"))[0], "BOROUGH_ONLY")

    def test_malformed_source(self):
        r = row("Brooklyn", source={"dataset": "fixture", "source_event_id": ""})
        self.assertEqual(classify_row(r)[0], "MALFORMED_SOURCE")

    def test_build_never_promotes(self):
        queue, report = build([row("95 Cozine Avenue", id="fixture-occurrence")])
        self.assertTrue(report["qa_pass"])
        self.assertEqual(report["promotion_attempt_count"], 0)
        self.assertFalse(report["public_map_modified"])
        self.assertFalse(queue[0]["promotion_allowed"])
        self.assertFalse(queue[0]["location_cache_modified"])

    def test_cancelled_title_is_excluded(self):
        queue, report = build([row("95 Cozine Avenue", title="CANCELED: Test", id="cancelled")])
        self.assertEqual(queue, [])
        self.assertEqual(report["unresolved_public_occurrence_count"], 0)


if __name__ == "__main__":
    unittest.main()
