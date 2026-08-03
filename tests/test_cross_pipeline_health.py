import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_cross_pipeline_data_health import augment_daily_health, build_report  # noqa: E402
from cross_pipeline_health import account_pipeline, delta, disposition, load_events  # noqa: E402


class CrossPipelineHealthTests(unittest.TestCase):
    def test_disposition_aliases(self):
        self.assertEqual(disposition({"coordinate_status": "map_ready"}), "map_safe")
        self.assertEqual(disposition({"nycif": {"coordinate_status": "approximate"}}), "approximate")
        self.assertEqual(disposition({"map_status": "list_only"}), "list_only")
        self.assertIsNone(disposition({"latitude": 40.7, "longitude": -74.0}))

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

    def test_missing_input_is_reported(self):
        events, missing = load_events([Path("/definitely/missing.json")])
        self.assertEqual(events, [])
        self.assertEqual(len(missing), 1)

    def test_build_report_blocks_missing_nj_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nyc = root / "nyc.json"
            nyc.write_text(
                json.dumps({"events": [{"id": "nyc:1", "map_status": "map_safe"}]}),
                encoding="utf-8",
            )
            report = build_report(
                nyc_paths=[nyc],
                nj_paths=[root / "missing-nj.json"],
            )
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["qa_pass"])
            self.assertEqual(report["blockers"][0]["code"], "NJ_LOCATION_INPUT_MISSING")

    def test_companion_command_passes_accounted_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nyc = root / "nyc.json"
            nj = root / "nj.json"
            output = root / "health.json"
            nyc.write_text(
                json.dumps(
                    {
                        "events": [
                            {"id": "nyc:1", "nycif": {"coordinate_status": "map_ready"}},
                            {"id": "nyc:2", "nycif": {"coordinate_status": "approximate"}},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            nj.write_text(
                json.dumps(
                    {
                        "events": [
                            {"id": "nj:1", "map_status": "map_safe"},
                            {"id": "nj:2", "map_status": "list_only"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_cross_pipeline_data_health.py"),
                    "--nyc-input",
                    str(nyc),
                    "--nj-input",
                    str(nj),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "READY")
            self.assertTrue(report["qa_pass"])

    def test_explicit_augment_blocks_daily_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.json"
            path.write_text(
                json.dumps({"status": "READY", "release_ready": True, "blockers": []}),
                encoding="utf-8",
            )
            cross = {
                "qa_pass": False,
                "blockers": [{"code": "NJ_UNACCOUNTED_LOCATION_RECORDS"}],
            }
            augment_daily_health(path, cross)
            daily = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(daily["status"], "BLOCKED")
            self.assertFalse(daily["release_ready"])


if __name__ == "__main__":
    unittest.main()
