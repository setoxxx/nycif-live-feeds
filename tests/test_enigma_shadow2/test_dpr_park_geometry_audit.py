import unittest

from scripts.audit_dpr_park_geometry_resolver import unresolved_failure_reason


class DprParkGeometryAuditTests(unittest.TestCase):
    def setUp(self):
        self.lookup = {
            "hamilton fish": {"park_id": "M033"},
            "bryant": {"park_id": "M008"},
        }

    def test_empty_location_category(self):
        self.assertEqual(unresolved_failure_reason({}, self.lookup, set()), "empty_location")

    def test_no_park_terminology_category(self):
        record = {"location": "Corner of First Avenue and East 10th Street"}
        self.assertEqual(unresolved_failure_reason(record, self.lookup, set()), "no_park_terminology")

    def test_ambiguous_alias_category(self):
        record = {"location": "Pool in Unity Park"}
        self.assertEqual(unresolved_failure_reason(record, self.lookup, {"unity"}), "ambiguous_alias")

    def test_multi_park_category(self):
        record = {"location": "Pool in Hamilton Fish Park, class at Bryant Park"}
        self.assertEqual(unresolved_failure_reason(record, self.lookup, set()), "multi_park_string")

    def test_non_dpr_facility_category(self):
        record = {"location": "Library garden at Central Library"}
        self.assertEqual(unresolved_failure_reason(record, self.lookup, set()), "non_dpr_facility")

    def test_unknown_dpr_name_category(self):
        record = {"location": "Pool in Imaginary Moon Park"}
        self.assertEqual(unresolved_failure_reason(record, self.lookup, set()), "unknown_dpr_name")


if __name__ == "__main__":
    unittest.main()
