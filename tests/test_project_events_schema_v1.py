import unittest

from scripts.project_events_schema_v1 import apply_supplemental_park_anchor


class SupplementalParkProjectionTests(unittest.TestCase):
    def setUp(self):
        self.lookup = {
            "hamilton fish": {
                "lat": 40.7191,
                "lng": -73.9816,
                "park_id": "M033",
                "park_name": "Hamilton Fish Park",
                "borough": "Manhattan",
                "source_dataset": "enfh-gkve",
            }
        }

    def test_unresolved_list_only_becomes_approximate_not_map_ready(self):
        projected = {
            "id": "review_supplemental:test",
            "title": "Swim",
            "borough": None,
            "location": "Main Pool in Hamilton Fish Park",
            "latitude": None,
            "longitude": None,
            "nycif": {
                "data_layer": "review_supplemental",
                "coordinate_status": "list_only",
                "promotion_allowed": False,
                "production_feed": False,
            },
        }
        result = apply_supplemental_park_anchor(
            projected,
            {"location": projected["location"]},
            park_lookup=self.lookup,
        )
        self.assertEqual(result["nycif"]["coordinate_status"], "approximate")
        self.assertEqual(result["nycif"]["display_disposition"], "approximate_marker")
        self.assertEqual(result["nycif"]["coordinate_precision"], "park_level_anchor")
        self.assertFalse(result["nycif"]["promotion_allowed"])
        self.assertFalse(result["nycif"]["production_feed"])
        self.assertEqual(result["location"], "Main Pool in Hamilton Fish Park")

    def test_existing_map_ready_record_is_untouched(self):
        projected = {
            "location": "Main Pool in Hamilton Fish Park",
            "latitude": 40.7,
            "longitude": -73.9,
            "nycif": {
                "data_layer": "review_supplemental",
                "coordinate_status": "map_ready",
                "promotion_allowed": False,
            },
        }
        result = apply_supplemental_park_anchor(
            projected,
            {"location": projected["location"]},
            park_lookup=self.lookup,
        )
        self.assertEqual(result["nycif"]["coordinate_status"], "map_ready")
        self.assertNotIn("coordinate_precision", result["nycif"])

    def test_unknown_park_stays_list_only(self):
        projected = {
            "location": "Pool in Imaginary Moon Park",
            "latitude": None,
            "longitude": None,
            "nycif": {
                "data_layer": "review_supplemental",
                "coordinate_status": "list_only",
                "promotion_allowed": False,
            },
        }
        result = apply_supplemental_park_anchor(
            projected,
            {"location": projected["location"]},
            park_lookup=self.lookup,
        )
        self.assertEqual(result["nycif"]["coordinate_status"], "list_only")
        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])


if __name__ == "__main__":
    unittest.main()
