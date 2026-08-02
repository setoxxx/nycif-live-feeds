import tempfile
import unittest
from pathlib import Path

from enigma.shadow2.audit import (
    find_coordinate_pairs,
    infer_borough,
    render_markdown,
    write_reports,
)


class Shadow2AuditTests(unittest.TestCase):
    def test_infer_borough_from_source_array_before_text(self) -> None:
        self.assertEqual(infer_borough({"boroughs": ["Queens"]}), ("Queens", "boroughs"))

    def test_infer_borough_from_segment_suffix(self) -> None:
        record = {
            "location": "SCHENCK AVENUE between NEW LOTS AVENUE and LIVONIA AVENUE Brooklyn"
        }
        self.assertEqual(infer_borough(record), ("Brooklyn", "location_text"))

    def test_infer_borough_refuses_ambiguous_text(self) -> None:
        self.assertEqual(infer_borough({"location": "Brooklyn and Queens"}), (None, None))

    def test_coordinate_diagnostic_counts_zero_values_and_geojson(self) -> None:
        pairs = find_coordinate_pairs(
            {
                "latitude": 0,
                "longitude": 0,
                "geometry": {"type": "Point", "coordinates": [-73.9, 40.7]},
            }
        )
        self.assertEqual(len(pairs), 2)
        self.assertTrue(any(pair["kind"] == "named_fields" for pair in pairs))
        self.assertTrue(any(pair["kind"] == "geojson_point" for pair in pairs))

    def test_report_files_preserve_fail_closed_repair_queue(self) -> None:
        report = {
            "input_totals": {
                "approved_events": 1,
                "review_events": 1,
                "classified_events": 2,
                "raw_records": 1,
                "raw_snapshot_files": 1,
            },
            "evidence_distribution": {"total": {tier: 0 for tier in (
                "exact_source_coordinate", "exact_address", "exact_intersection",
                "certified_street_segment", "certified_facility", "approximate_area",
                "unresolved", "malformed"
            )}},
            "review_list_only": {
                "count": 1,
                "tier_distribution": {"certified_street_segment": 1},
                "borough_null_count": 1,
                "borough_repair_candidate_count": 1,
                "records": [],
            },
            "raw_coordinate_diagnostic": {
                "records_with_coordinate_pairs": 0,
                "records_without_coordinate_pairs": 1,
            },
            "reconciliation": {
                "occurrence_minus_raw_delta": 1,
                "status": "requires_occurrence_expansion_contract",
                "note": "Not reconciled.",
            },
            "repair_queue": [{"promotion_allowed": False}],
        }
        markdown = render_markdown(report)
        self.assertIn("Street-segment claims in list-only review: **1**", markdown)
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_reports(report, Path(tmp))
            self.assertTrue(Path(paths["repair_queue"]).exists())
            self.assertIn('"promotion_allowed": false', Path(paths["repair_queue"]).read_text())


if __name__ == "__main__":
    unittest.main()
