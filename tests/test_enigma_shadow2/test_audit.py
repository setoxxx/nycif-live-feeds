import tempfile
import unittest
from pathlib import Path

from enigma.shadow2.audit import (
    build_unresolved_diagnostics,
    find_coordinate_pairs,
    infer_borough,
    render_markdown,
    source_identity,
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

    def test_unresolved_nonempty_facility_text(self) -> None:
        item = self._unresolved_item(location="Main Pool in Hamilton Fish Park")
        diagnostic = build_unresolved_diagnostics([item], {})
        self.assertEqual(diagnostic["location_text"]["present"], 1)
        self.assertEqual(diagnostic["facility_terminology"]["pool"], 1)
        self.assertEqual(diagnostic["facility_terminology"]["park"], 1)
        self.assertEqual(diagnostic["facility_within_park_candidates"], 1)

    def test_unresolved_empty_location_text(self) -> None:
        diagnostic = build_unresolved_diagnostics([self._unresolved_item(location="")], {})
        self.assertEqual(diagnostic["location_text"]["empty"], 1)
        self.assertEqual(diagnostic["location_text"]["present"], 0)

    def test_source_identity_safely_reads_source_dictionary(self) -> None:
        self.assertEqual(
            source_identity(
                {
                    "source": {
                        "dataset": "nyc-parks-bigapps-events",
                        "source_event_id": "park-1",
                    }
                }
            ),
            ("nyc-parks-bigapps-events", "park-1"),
        )

    def test_unresolved_raw_coordinate_present_projected_absent(self) -> None:
        item = self._unresolved_item(
            dataset="nyc-parks-bigapps-events",
            source_event_id="park-1",
            location="Pool in Park",
        )
        raw_index = {
            ("nyc-parks-bigapps-events", "park-1"): [
                {"lat": 40.7, "lng": -73.9}
            ]
        }
        diagnostic = build_unresolved_diagnostics([item], raw_index)
        trace = diagnostic["raw_to_projected_coordinate_trace"]
        self.assertEqual(trace["coordinate_loss_candidate_occurrences"], 1)
        self.assertEqual(trace["parks_coordinate_loss_candidate_occurrences"], 1)
        self.assertEqual(trace["unresolved_occurrences_with_projected_coordinates"], 0)

    def test_unresolved_ambiguous_borough_text_remains_null(self) -> None:
        item = self._unresolved_item(
            location="Brooklyn and Queens program",
            borough=None,
        )
        diagnostic = build_unresolved_diagnostics([item], {})
        self.assertEqual(diagnostic["borough_state"]["null"], 1)
        self.assertEqual(infer_borough({"location": item["location"]}), (None, None))

    def test_unresolved_duplicate_facility_container_detected(self) -> None:
        item = self._unresolved_item(
            location="Greenbelt Recreation Center in Greenbelt Recreation Center"
        )
        diagnostic = build_unresolved_diagnostics([item], {})
        self.assertEqual(diagnostic["duplicate_facility_container"], 1)

    def test_unresolved_classifier_tier_separate_from_coordinate_precision(self) -> None:
        item = self._unresolved_item(location="Some Park")
        item["coordinate_precision"] = "exact_address"
        diagnostic = build_unresolved_diagnostics([item], {})
        self.assertEqual(diagnostic["total_unresolved"], 1)

    def test_non_unresolved_items_are_excluded(self) -> None:
        resolved = self._unresolved_item(location="123 Main Street")
        resolved["evidence_tier"] = "exact_address"
        unresolved = self._unresolved_item(location="Pool in Park")
        diagnostic = build_unresolved_diagnostics([resolved, unresolved], {})
        self.assertEqual(diagnostic["total_unresolved"], 1)

    def test_projected_coordinates_prevent_coordinate_loss_flag(self) -> None:
        item = self._unresolved_item(
            dataset="nyc-parks-bigapps-events",
            source_event_id="park-2",
            location="Court in Park",
        )
        item["projected_coordinate_pairs"] = [
            {"latitude": 40.71, "longitude": -73.91, "path": "$", "kind": "named_fields"}
        ]
        raw_index = {
            ("nyc-parks-bigapps-events", "park-2"): [
                {"lat": 40.71, "lng": -73.91}
            ]
        }
        diagnostic = build_unresolved_diagnostics([item], raw_index)
        trace = diagnostic["raw_to_projected_coordinate_trace"]
        self.assertEqual(trace["coordinate_loss_candidate_occurrences"], 0)
        self.assertEqual(trace["unresolved_occurrences_with_projected_coordinates"], 1)

    def test_zero_coordinate_pair_is_not_dropped_from_raw_trace(self) -> None:
        item = self._unresolved_item(source_event_id="zero-1", location="Test Park")
        raw_index = {
            ("nyc-citywide-events-calendar-api", "zero-1"): [
                {"latitude": 0, "longitude": 0}
            ]
        }
        diagnostic = build_unresolved_diagnostics([item], raw_index)
        trace = diagnostic["raw_to_projected_coordinate_trace"]
        self.assertEqual(trace["unresolved_occurrences_with_raw_coordinates"], 1)
        self.assertEqual(trace["coordinate_loss_candidate_occurrences"], 1)

    @staticmethod
    def _unresolved_item(
        *,
        location: str,
        dataset: str = "nyc-citywide-events-calendar-api",
        source_event_id: str = "event-1",
        borough=None,
    ) -> dict:
        return {
            "id": "projected-1",
            "title": "Test event",
            "location": location,
            "borough": borough,
            "source_dataset": dataset,
            "source_event_id": source_event_id,
            "coordinate_status": "list_only",
            "evidence_tier": "unresolved",
            "evidence_reason": "MISSING_EVIDENCE",
            "projected_coordinate_pairs": [],
            "pipeline_reason_fields": {},
            "promotion_allowed": False,
        }


if __name__ == "__main__":
    unittest.main()
