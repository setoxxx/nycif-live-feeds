import unittest

from scripts.temporal_quality import (
    MISSING_END,
    NONPOSITIVE_INTERVAL,
    PARSE_ERROR,
    VALID,
    classify_temporal_quality,
    is_temporally_projectable,
)


class TemporalQualityV1Tests(unittest.TestCase):
    def test_valid_interval_is_projectable(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T11:00:00-04:00",
            source_end_raw="2026-08-09T16:00:00-04:00",
        )
        self.assertEqual(result["quality_state"], VALID)
        self.assertFalse(result["repair_applied"])
        self.assertTrue(is_temporally_projectable(result))

    def test_source_invalid_interval_is_review_required(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T16:00:00-04:00",
            source_end_raw="2026-08-09T11:00:00-04:00",
        )
        self.assertEqual(result["quality_state"], NONPOSITIVE_INTERVAL)
        self.assertEqual(result["reason_code"], "source_invalid_interval")
        self.assertTrue(result["review_required"])
        self.assertFalse(is_temporally_projectable(result))

    def test_normalizer_defect_is_distinguished_from_source(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T11:00:00-04:00",
            source_end_raw="2026-08-09T16:00:00-04:00",
            normalized_start="2026-08-09T16:00:00-04:00",
            normalized_end="2026-08-09T11:00:00-04:00",
        )
        self.assertEqual(result["quality_state"], NONPOSITIVE_INTERVAL)
        self.assertEqual(result["reason_code"], "normalizer_interval_defect")
        self.assertTrue(result["review_required"])

    def test_missing_source_end_is_not_repaired(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T11:00:00-04:00",
            source_end_raw=None,
        )
        self.assertEqual(result["quality_state"], MISSING_END)
        self.assertEqual(result["reason_code"], "missing_end_source")
        self.assertFalse(result["source_supports_end"])
        self.assertFalse(result["repair_applied"])
        self.assertFalse(is_temporally_projectable(result))

    def test_missing_normalized_end_is_distinguished(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T11:00:00-04:00",
            source_end_raw="2026-08-09T16:00:00-04:00",
            normalized_start="2026-08-09T11:00:00-04:00",
            normalized_end=None,
        )
        # None means no downstream override was supplied, so raw source end remains valid.
        self.assertEqual(result["quality_state"], VALID)

    def test_parse_error_does_not_guess(self):
        result = classify_temporal_quality(
            source_start_raw="not-a-date",
            source_end_raw="also-not-a-date",
        )
        self.assertEqual(result["quality_state"], PARSE_ERROR)
        self.assertEqual(result["reason_code"], "temporal_parse_error")
        self.assertFalse(result["repair_applied"])
        self.assertFalse(is_temporally_projectable(result))

    def test_mixed_timezone_awareness_is_review_required(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T11:00:00",
            source_end_raw="2026-08-09T16:00:00-04:00",
        )
        self.assertEqual(result["quality_state"], PARSE_ERROR)
        self.assertEqual(result["reason_code"], "mixed_timezone_awareness")
        self.assertTrue(result["review_required"])

    def test_equal_start_end_is_not_projectable(self):
        result = classify_temporal_quality(
            source_start_raw="2026-08-09T11:00:00-04:00",
            source_end_raw="2026-08-09T11:00:00-04:00",
        )
        self.assertEqual(result["quality_state"], NONPOSITIVE_INTERVAL)
        self.assertFalse(is_temporally_projectable(result))


if __name__ == "__main__":
    unittest.main()
