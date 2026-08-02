import json
import tempfile
import unittest
from pathlib import Path

from nycif.normalize.facility_resolver import resolve_facility_anchor
from nycif.normalize.park_geometry import (
    build_park_lookup,
    centroid_from_geometry,
    extract_park_names,
    find_park_centroid,
    normalize_park_name,
    representative_point_from_geometry,
    write_park_lookup,
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

    def test_concave_polygon_uses_point_on_surface_when_centroid_is_outside(self):
        geometry = {
            "type": "Polygon",
            "coordinates": [[
                [-74.00, 40.70], [-73.98, 40.70], [-73.98, 40.705],
                [-73.995, 40.705], [-73.995, 40.72], [-74.00, 40.72],
                [-74.00, 40.70],
            ]],
        }
        point = representative_point_from_geometry(geometry)
        self.assertIsNotNone(point)
        lat, lng, method = point
        self.assertEqual(method, "point_on_surface")
        self.assertTrue(40.70 <= lat <= 40.72)
        self.assertTrue(-74.00 <= lng <= -73.98)

    def test_disconnected_multipolygon_falls_back_inside_largest_component(self):
        geometry = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[-74.00, 40.70], [-73.99, 40.70], [-73.99, 40.71], [-74.00, 40.71], [-74.00, 40.70]]],
                [[[-73.90, 40.80], [-73.89, 40.80], [-73.89, 40.81], [-73.90, 40.81], [-73.90, 40.80]]],
            ],
        }
        point = representative_point_from_geometry(geometry)
        self.assertIsNotNone(point)
        lat, lng, method = point
        self.assertEqual(method, "point_on_surface")
        inside_first = 40.70 <= lat <= 40.71 and -74.00 <= lng <= -73.99
        inside_second = 40.80 <= lat <= 40.81 and -73.90 <= lng <= -73.89
        self.assertTrue(inside_first or inside_second)

    def test_lookup_is_stable_across_source_row_order(self):
        rows = [
            {"gispropnum": "M033", "signname": "Hamilton Fish Park", "name311": "Hamilton Fish Playground", "borough": "M", "the_geom": self.geometry},
            {"gispropnum": "M008", "signname": "Bryant Park", "borough": "M", "the_geom": self.geometry},
        ]
        forward = build_park_lookup(rows).lookup
        reverse = build_park_lookup(list(reversed(rows))).lookup
        self.assertEqual(forward, reverse)

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
                [-73.97, 40.73], [-73.96, 40.73], [-73.96, 40.74],
                [-73.97, 40.74], [-73.97, 40.73],
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

    def test_written_lookup_and_ambiguity_file_are_deterministic(self):
        rows = [
            {"gispropnum": "M033", "signname": "Hamilton Fish Park", "name311": "Hamilton Fish Playground", "borough": "M", "the_geom": self.geometry},
            {"gispropnum": "A1", "signname": "Unity Park", "the_geom": self.geometry},
            {"gispropnum": "A2", "signname": "Unity Playground", "the_geom": self.geometry},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            lookup_path = Path(tmp) / "lookup.json"
            ambiguity_path = Path(tmp) / "ambiguous.json"
            write_park_lookup(rows, lookup_path, ambiguity_path)
            first_lookup = lookup_path.read_text()
            first_ambiguity = ambiguity_path.read_text()
            write_park_lookup(list(reversed(rows)), lookup_path, ambiguity_path)
            self.assertEqual(first_lookup, lookup_path.read_text())
            self.assertEqual(first_ambiguity, ambiguity_path.read_text())
            self.assertEqual(json.loads(lookup_path.read_text())["hamilton fish"]["lat"], 40.715)

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
