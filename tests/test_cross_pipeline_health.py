import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_cross_pipeline_data_health as cross_builder  # noqa: E402
from cross_pipeline_health import account_pipeline, delta, disposition, event_rows  # noqa: E402


class CrossPipelineHealthTests(unittest.TestCase):
    def test_disposition_aliases(self):
        self.assertEqual(disposition({"coordinate_status": "map_ready"}), "map_safe")
        self.assertEqual(disposition({"nycif": {"coordinate_status": "approximate"}}), "approximate")
        self.assertEqual(disposition({"map_status": "list_only"}), "list_only")
        self.assertIsNone(disposition({"latitude": 40.7, "longitude": -74.0}))

    def test_event_rows_accepts_supported_envelopes(self):
        row = {"id": "one", "map_status": "list_only"}
        self.assertEqual(event_rows({"events": [row]}), [row])
        self.assertEqual(event_rows([row]), [row])
        self.assertEqual(event_rows({"unknown": [row]}), [])

    def test_accounting_requires_explicit_status(self):
        report = account_pipeline(
            "nj",
            [
                {"id": "1", "map_status": "map_safe"},
                {"id": "2", "map_status": "approximate"},
                {"id": "3", "map_status": "list_only"},
                {"id": "4", "latitude": 40.7, "longitude": -74.0},
            ],
        )
        self.assertEqual(report["total_count"], 4)
        self.assertEqual(report["accounted_count"], 3)
        self.assertEqual(report["unaccounted_count"], 1)
        self.assertFalse(report["qa_pass"])

    def test_accounting_invariant_passes(self):
        report = account_pipeline(
            "nyc",
            [
                {"id": "1", "nycif": {"coordinate_status": "map_ready"}},
                {"id": "2", "nycif": {"coordinate_precision": "certified_facility"}},
                {"id": "3", "nycif": {"coordinate_status": "list_only"}},
            ],
        )
        self.assertEqual(
            report["map_safe_count"] + report["approximate_count"] + report["list_only_count"],
            report["total_count"],
        )
        self.assertTrue(report["qa_pass"])

    def test_duplicate_ids_are_reported(self):
        report = account_pipeline(
            "nyc",
            [
                {"id": "same", "map_status": "map_safe"},
                {"id": "same", "map_status": "list_only"},
            ],
        )
        self.assertEqual(report["duplicate_id_count"], 1)
        self.assertEqual(report["total_count"], 1)

    def test_daily_delta(self):
        current = {
            "total_count": 12,
            "map_safe_count": 7,
            "approximate_count": 2,
            "list_only_count": 3,
            "unaccounted_count": 0,
        }
        previous = {
            "total_count": 10,
            "map_safe_count": 6,
            "approximate_count": 1,
            "list_only_count": 3,
            "unaccounted_count": 0,
        }
        self.assertEqual(delta(current, previous)["total_count"], 2)
        self.assertEqual(delta(current, previous)["approximate_count"], 1)

    def test_build_report_blocks_missing_nj_handoff(self):
        report = cross_builder.build_report(
            nyc_events=[{"id": "nyc:1", "map_status": "map_safe"}],
            nj_events=[],
            missing_nj_input=True,
        )
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["qa_pass"])
        self.assertEqual(report["blockers"][0]["code"], "NJ_LOCATION_INPUT_MISSING")

    def test_build_report_passes_accounted_events(self):
        report = cross_builder.build_report(
            nyc_events=[
                {"id": "nyc:1", "nycif": {"coordinate_status": "map_ready"}},
                {"id": "nyc:2", "nycif": {"coordinate_status": "approximate"}},
            ],
            nj_events=[
                {"id": "nj:1", "map_status": "map_safe"},
                {"id": "nj:2", "map_status": "list_only"},
            ],
        )
        self.assertEqual(report["status"], "READY")
        self.assertTrue(report["qa_pass"])

    def test_fixed_contract_uses_parsed_fixed_artifacts(self):
        written = []
        with (
            patch.object(
                cross_builder,
                "_read_nyc_staged",
                return_value={"events": [{"id": "nyc:1", "map_status": "map_safe"}]},
            ),
            patch.object(
                cross_builder,
                "_read_nyc_supplemental",
                return_value={"events": [{"id": "nyc:2", "map_status": "approximate"}]},
            ),
            patch.object(
                cross_builder,
                "_read_nj_handoff",
                return_value={"events": [{"id": "nj:1", "map_status": "list_only"}]},
            ),
            patch.object(cross_builder, "_read_previous_output", return_value={}),
            patch.object(cross_builder, "_write_output", side_effect=written.append),
        ):
            report = cross_builder.run_fixed_contract()
        self.assertEqual(report["status"], "READY")
        self.assertEqual(written, [report])

    def test_apply_cross_to_daily_blocks_release(self):
        daily = {"status": "READY", "release_ready": True, "blockers": []}
        cross = {
            "qa_pass": False,
            "blockers": [{"code": "NJ_UNACCOUNTED_LOCATION_RECORDS"}],
        }
        combined = cross_builder.apply_cross_to_daily(daily, cross)
        self.assertEqual(combined["status"], "BLOCKED")
        self.assertFalse(combined["release_ready"])
        self.assertEqual(daily["status"], "READY")


if __name__ == "__main__":
    unittest.main()
