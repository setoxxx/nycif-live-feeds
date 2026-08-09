from __future__ import annotations

import unittest

from scripts.borg_freq_call_coverage import project_call_coverage


TERMS = [
    {
        "id": "fd-10-75",
        "agency": "FDNY",
        "domain": "dispatch",
        "canonical_text": "10-75",
        "canonical_meaning": "All Hands fire assignment",
        "public_summary": "All Hands fire assignment",
        "code": "10-75",
        "source_ids": ["official-term-source"],
        "confidence": 1.0,
        "sensitivity": "normal",
        "publication_action": "generalize",
        "review_status": "approved",
    }
]


def obs(call_id: str, **overrides):
    row = {
        "freq_observation_id": call_id,
        "observed_at": "2026-08-09T20:00:00Z",
        "jurisdiction_id": "nyc",
        "service_class": "fire",
        "rights_state": "PUBLIC",
        "sensitivity_state": "NON_TACTICAL",
        "location_state": "resolved",
        "location_evidence_ref": "loc-evidence-1",
        "terminology_refs": ["fd-10-75"],
        "provenance_ref": "freq-observation-1",
        "public_area_label": "Brooklyn",
        "public_location_id": "loc:brooklyn:test",
        "public_geometry_state": "none",
    }
    row.update(overrides)
    return row


class BorgFreqCallCoverageTests(unittest.TestCase):
    def test_classified_call_is_retained(self):
        result = project_call_coverage(observations=[obs("c1")], terminology_records=TERMS)
        record = result["records"][0]
        self.assertEqual(record["call_type"], "10-75")
        self.assertEqual(record["call_meaning"], "All Hands fire assignment")
        self.assertEqual(record["coverage_disposition"], "CLASSIFIED_PUBLIC")
        self.assertEqual(result["accounting"]["silent_loss"], 0)
        self.assertEqual(result["accounting"]["nature_filtered_count"], 0)

    def test_unknown_code_is_listed_not_dropped(self):
        row = obs("c2", terminology_refs=["unknown-code"])
        result = project_call_coverage(observations=[row], terminology_records=TERMS)
        record = result["records"][0]
        self.assertEqual(record["classification_state"], "PENDING")
        self.assertEqual(record["coverage_disposition"], "CLASSIFICATION_PENDING_PUBLIC")
        self.assertEqual(result["accounting"]["terminal_record_count"], 1)

    def test_unresolved_location_is_listed_without_exact_pin(self):
        row = obs(
            "c3",
            location_state="unresolved",
            public_location_id="bad-location",
            public_geometry_state="exact_public",
            public_geometry={"type": "Point", "coordinates": [-73.9, 40.7]},
            public_area_label=None,
        )
        result = project_call_coverage(observations=[row], terminology_records=TERMS)
        record = result["records"][0]
        self.assertIsNone(record["public_location_id"])
        self.assertIsNone(record["public_geometry"])
        self.assertEqual(record["public_geometry_state"], "none")
        self.assertEqual(record["public_area_label"], "Location not yet resolved")
        self.assertEqual(record["coverage_disposition"], "CLASSIFIED_PUBLIC_LOCATION_PENDING")

    def test_category_does_not_filter_coverage(self):
        observations = [
            obs("fire", service_class="fire"),
            obs("ems", service_class="ems"),
            obs("law", service_class="law"),
            obs("traffic", service_class="traffic"),
            obs("utility", service_class="utility"),
            obs("quality", service_class="quality_of_life"),
            obs("unknown", service_class="unknown", terminology_refs=[]),
        ]
        result = project_call_coverage(observations=observations, terminology_records=TERMS)
        self.assertEqual(result["accounting"]["input_observation_count"], 7)
        self.assertEqual(result["accounting"]["terminal_record_count"], 7)
        self.assertEqual(result["accounting"]["nature_filtered_count"], 0)
        self.assertEqual(result["accounting"]["silent_loss"], 0)

    def test_rights_review_preserves_record(self):
        result = project_call_coverage(
            observations=[obs("c4", rights_state="REVIEW_REQUIRED")], terminology_records=TERMS
        )
        self.assertEqual(result["records"][0]["coverage_disposition"], "RIGHTS_REVIEW_REQUIRED")
        self.assertEqual(result["accounting"]["terminal_record_count"], 1)

    def test_sensitive_input_is_quarantined_but_accounted(self):
        result = project_call_coverage(
            observations=[obs("c5", raw_audio="not-public")], terminology_records=TERMS
        )
        record = result["records"][0]
        self.assertEqual(record["coverage_disposition"], "QUARANTINE_SENSITIVE_INPUT")
        self.assertEqual(result["accounting"]["silent_loss"], 0)

    def test_duplicate_upstream_id_fails_closed(self):
        with self.assertRaises(ValueError):
            project_call_coverage(observations=[obs("same"), obs("same")], terminology_records=TERMS)

    def test_exact_public_geometry_requires_public_location_id(self):
        with self.assertRaises(ValueError):
            project_call_coverage(
                observations=[
                    obs(
                        "c6",
                        public_location_id=None,
                        public_geometry_state="exact_public",
                        public_geometry={"type": "Point", "coordinates": [-73.9, 40.7]},
                    )
                ],
                terminology_records=TERMS,
            )


if __name__ == "__main__":
    unittest.main()
