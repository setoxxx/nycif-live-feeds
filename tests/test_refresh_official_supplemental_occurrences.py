import unittest

from scripts.refresh_official_supplemental_occurrences import (
    borough_from_text,
    canonical_borough,
    intake_row,
    resolve_borough,
)


class SupplementalOccurrenceBoroughTests(unittest.TestCase):
    def test_single_source_borough_is_preserved(self) -> None:
        self.assertEqual(canonical_borough(["Manhattan"]), "Manhattan")
        self.assertEqual(resolve_borough({"boroughs": ["Brooklyn"]}), ("Brooklyn", "boroughs"))

    def test_multiple_source_boroughs_fail_closed(self) -> None:
        self.assertIsNone(canonical_borough(["Manhattan", "Queens"]))
        self.assertEqual(resolve_borough({"boroughs": ["Manhattan", "Queens"]}), (None, None))

    def test_location_suffix_recovers_segment_borough(self) -> None:
        location = " WEST 23 STREET between 8 AVENUE and 9 AVENUE Manhattan"
        self.assertEqual(borough_from_text(location), "Manhattan")
        self.assertEqual(resolve_borough({"address": location}), ("Manhattan", "location_text"))

    def test_multiple_text_boroughs_fail_closed(self) -> None:
        self.assertIsNone(borough_from_text("Brooklyn to Queens"))

    def test_intake_row_only_repairs_borough(self) -> None:
        row = {
            "source_dataset": "nyc-citywide-events-calendar-api",
            "source_event_id": "1045196",
            "start_date_time": "2026-08-01T08:00:00",
            "title": "Down to Earth Chelsea Farmers Market",
            "address": "WEST 23 STREET between 8 AVENUE and 9 AVENUE Manhattan",
            "boroughs": [],
        }
        result = intake_row(row, "approved")
        self.assertEqual(result["borough"], "Manhattan")
        self.assertEqual(result["borough_resolution_source"], "location_text")
        self.assertFalse(result["promotion_allowed"])
        self.assertFalse(result["public_map_modified"])
        self.assertNotIn("lat", result)
        self.assertNotIn("lng", result)


if __name__ == "__main__":
    unittest.main()
