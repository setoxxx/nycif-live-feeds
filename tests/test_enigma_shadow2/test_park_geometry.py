import unittest

from nycif.normalize.facility_resolver import resolve_facility_anchor
from nycif.normalize.park_geometry import (
    build_park_lookup,
    centroid_from_geometry,
    extract_park_names,
    find_park_centroid,
    normalize_park_name,
)


class ParkGeometryTests(unittest.TestCase):
    def setUp(self):
        self.geometry = {
            "type": "Polygon",
            "coordinates": [[
                [-73.99, 40.71],
                [-73.98, 40.71],
                [-73.98, 40.72],
                [-73.99, 40.72],
                [-73.99, 40.71],
            ]],
        }
        result = build_park_lookup([
            {
                "gispropnum": "M033",
                "signname": "Hamilton Fish Park",
                "name311": "Hamilton Fish Playground",
                "borough": "M",
                "the_geom": self.geometry,
            }
        ])
        self.lookup = result.lookup

    def test_centroid_calculation_sanity(self):
        centroid = centroid_from_geometry(self.geometry)
        self.assertIsNotNone(centroid)
        lat, lng = centroid
        self.assertAlmostEqual(lat, 40.715, places=5)
        self.assertAlmostEqual(lng, -73.985, places=5)
        self.assertNotEqual((lat, lng), (0.0, 0.0))

    def test_extracts_container_name(self):
        self.assertIn("Hamilton Fish Park", extract_park_names("Main Pool in Hamilton Fish Park"))

    def test_suffix_variation_matches(self):
        self.assertEqual(normalize_park_name("Hamilton Fish Park"), "hamilton fish")
        self.assertEqual(normalize_park_name("Hamilton Fish Playground"), "hamilton fish")
        match = find_park_centroid("Pool in Hamilton Fish Playground", lookup=self.lookup)
        self.assertEqual(match["park_id"], "M033")

    def test_unknown_park_fails_closed(self):
        self.assertIsNone(find_park_centroid("Pool in Imaginary Moon Park", lookup=self.lookup))

    def test_facility_resolver_only_resolves_unresolved(self):
        record = {
            "evidence_tier": "unresolved",
            "location": "Main Pool in Hamilton Fish Park",
        }
        resolved = resolve_facility_anchor(record, lookup=self.lookup)
        self.assertEqual(resolved["coordinate_precision"], "park_level_anchor")
        self.assertEqual(resolved["coordinate_source"], "dpr_parks_properties_centroid")
        self.assertFalse(resolved["promotion_allowed"])
        self.assertEqual(resolved["park_borough"], "Manhattan")
        record["evidence_tier"] = "exact_address"
        self.assertIsNone(resolve_facility_anchor(record, lookup=self.lookup))

    def test_multiple_distinct_parks_fail_closed(self):
        second_geometry = {
            "type": "Polygon",
            "coordinates": [[
                [-73.97, 40.73],
                [-73.96, 40.73],
                [-73.96, 40.74],
                [-73.97, 40.74],
                [-73.97, 40.73],
            ]],
        }
        lookup = build_park_lookup([
            {"gispropnum": "M033", "signname": "Hamilton Fish Park", "the_geom": self.geometry},
            {"gispropnum": "M008", "signname": "Bryant Park", "the_geom": second_geometry},
        ]).lookup
        self.assertIsNone(
            find_park_centroid(
                "Pool in Hamilton Fish Park, class at Bryant Park",
                lookup=lookup,
            )
        )

    def test_ambiguous_alias_is_omitted(self):
        rows = [
            {"gispropnum": "A1", "signname": "Unity Park", "the_geom": self.geometry},
            {"gispropnum": "A2", "signname": "Unity Playground", "the_geom": self.geometry},
        ]
        result = build_park_lookup(rows)
        self.assertNotIn("unity", result.lookup)
        self.assertIn("unity", result.ambiguous_aliases)


if __name__ == "__main__":
    unittest.main()
