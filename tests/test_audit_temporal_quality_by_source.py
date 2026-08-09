from __future__ import annotations

import unittest

from scripts.audit_temporal_quality_by_source import account_records, extract_records


class TemporalQualityAuditTests(unittest.TestCase):
    def test_extracts_list_and_events_shapes(self):
        rows = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(extract_records(rows), rows)
        self.assertEqual(extract_records({"events": rows}), rows)

    def test_extracts_geojson_features(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "properties": {"id": "a", "start_date_time": "2026-08-09T10:00:00-04:00", "end_date_time": "2026-08-09T11:00:00-04:00"}},
            ],
        }
        extracted = extract_records(payload)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["id"], "a")

    def test_zero_loss_accounting_and_source_counts(self):
        rows = [
            {
                "id": "one",
                "start_date_time": "2026-08-09T10:00:00-04:00",
                "end_date_time": "2026-08-09T11:00:00-04:00",
                "source": {"dataset": "source-a"},
            },
            {
                "id": "two",
                "start_date_time": "2026-08-09T12:00:00-04:00",
                "end_date_time": "2026-08-09T11:00:00-04:00",
                "source": {"dataset": "source-a"},
            },
            {
                "id": "three",
                "start_date_time": "2026-08-09T13:00:00-04:00",
                "end_date_time": None,
                "source_dataset": "source-b",
            },
        ]
        report = account_records(rows)
        self.assertEqual(report["input_count"], 3)
        self.assertEqual(report["accounted_count"], 3)
        self.assertEqual(report["unaccounted_count"], 0)
        self.assertEqual(report["by_source"]["source-a"]["total"], 2)
        self.assertEqual(report["by_source"]["source-b"]["total"], 1)
        self.assertEqual(report["by_source"]["source-a"]["quality_states"]["nonpositive_interval"], 1)
        self.assertEqual(report["by_source"]["source-b"]["quality_states"]["missing_end"], 1)

    def test_occurrence_prefix_used_only_as_audit_fallback(self):
        rows = [
            {
                "occurrence_id": "tvpp-9vvx|review_supplemental:tvpp-9vvx:123@2026-08-09|2026-08-09T10:00:00",
                "start_date_time": "2026-08-09T10:00:00-04:00",
                "end_date_time": "2026-08-09T11:00:00-04:00",
            }
        ]
        report = account_records(rows)
        self.assertIn("tvpp-9vvx", report["by_source"])
        self.assertTrue(report["source_inference_fallback_used"])

    def test_valid_raw_invalid_normalized_is_normalizer_defect(self):
        rows = [
            {
                "id": "x",
                "source_start_raw": "2026-08-09T10:00:00-04:00",
                "source_end_raw": "2026-08-09T12:00:00-04:00",
                "normalized_start": "2026-08-09T10:00:00-04:00",
                "normalized_end": "2026-08-09T09:00:00-04:00",
                "source": {"dataset": "source-c"},
            }
        ]
        report = account_records(rows)
        reasons = report["by_source"]["source-c"]["reason_codes"]
        self.assertEqual(reasons["normalizer_interval_defect"], 1)


if __name__ == "__main__":
    unittest.main()
