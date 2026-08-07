from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("mc_summary", SCRIPTS / "build_mission_control_summary.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class MissionControlSummaryTests(unittest.TestCase):
    def evidence(self):
        return {
            "certified": True,
            "generated_at": "2026-08-07T16:45:00Z",
            "release_id": "release-abcdef1",
            "release_sha": "abcdef1",
            "current_pointer": "current/release.json",
            "data_health": "READY",
            "sources": [
                {"label": "Permitted Events", "health": "FRESH", "last_success_age_seconds": 60, "safe_event_count": 12, "last_release_id": "release-abcdef1"},
                {"label": "Citywide Calendar", "health": "STALE", "last_success_age_seconds": 7200, "safe_event_count": 8, "last_release_id": "release-abcdef1"},
                {"label": "Parks BigApps", "health": "BLOCKED", "last_success_age_seconds": None, "safe_event_count": None, "last_release_id": "release-abcdef1"},
            ],
            "daily_event_count": 20,
            "new_event_count": 3,
            "projector_status": "PASS",
            "reconciliation_status": "PASS",
            "silent_identity_loss": 0,
            "unsupported_exact_pins": 0,
            "duplicate_exact_occurrences": 0,
            "daily_health": "READY",
            "anonymous_audit_status": "PENDING",
        }

    def test_complete_summary(self):
        summary = MOD.build_summary(self.evidence(), "abcdef1", "1234567")
        self.assertEqual(summary["schema_version"], MOD.SCHEMA)
        self.assertEqual(summary["release_sha"], "abcdef1")
        self.assertEqual(summary["rollback_release"], "1234567")
        self.assertEqual(summary["daily_event_count"], 20)
        self.assertEqual(len(summary["sources"]), 3)
        MOD.validate_summary(summary, "abcdef1")

    def test_missing_source_becomes_unavailable_not_zero(self):
        evidence = self.evidence()
        evidence["sources"] = evidence["sources"][:2]
        summary = MOD.build_summary(evidence, "abcdef1")
        parks = next(row for row in summary["sources"] if row["label"] == "Parks BigApps")
        self.assertEqual(parks["health"], "UNAVAILABLE")
        self.assertIsNone(parks["safe_event_count"])

    def test_missing_counts_remain_null(self):
        evidence = self.evidence()
        evidence.pop("daily_event_count")
        evidence.pop("new_event_count")
        summary = MOD.build_summary(evidence, "abcdef1")
        self.assertIsNone(summary["daily_event_count"])
        self.assertIsNone(summary["new_event_count"])

    def test_missing_reconciliation_is_unavailable(self):
        evidence = self.evidence()
        evidence.pop("reconciliation_status")
        summary = MOD.build_summary(evidence, "abcdef1")
        self.assertEqual(summary["reconciliation_status"], "UNAVAILABLE")

    def test_missing_rollback_omits_pointer(self):
        summary = MOD.build_summary(self.evidence(), "abcdef1")
        self.assertNotIn("rollback_release", summary)

    def test_malformed_json_fails_closed(self):
        with self.assertRaises(Exception):
            MOD.loads_evidence("{")

    def test_unexpected_field_rejected(self):
        evidence = self.evidence()
        evidence["private_debug"] = "no"
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_private_path_rejected(self):
        evidence = self.evidence()
        evidence["current_pointer"] = "private source/path"
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_raw_github_rejected(self):
        evidence = self.evidence()
        evidence["current_pointer"] = "https://raw.githubusercontent.com/example/file.json"
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_credential_like_text_rejected(self):
        evidence = self.evidence()
        evidence["current_pointer"] = "token=abcdefghi"
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_negative_count_rejected(self):
        evidence = self.evidence()
        evidence["daily_event_count"] = -1
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_non_integer_count_rejected(self):
        evidence = self.evidence()
        evidence["daily_event_count"] = 1.5
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_duplicate_source_rejected(self):
        evidence = self.evidence()
        evidence["sources"].append(dict(evidence["sources"][0]))
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_unknown_source_rejected(self):
        evidence = self.evidence()
        evidence["sources"][0]["label"] = "Internal Feed X"
        with self.assertRaises(Exception):
            MOD.build_summary(evidence, "abcdef1")

    def test_release_mismatch_rejected(self):
        with self.assertRaises(Exception):
            MOD.build_summary(self.evidence(), "7654321")


if __name__ == "__main__":
    unittest.main()
