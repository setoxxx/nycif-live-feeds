"""God View project-state generator — Enigma SHADOW-1 closeout program block.

Standard-library unittest (also collected by the repo's pytest). Proves the
public-safe enigma_shadow_program facts, the refreshed command center, generator
determinism apart from the generated timestamp, and that no private national-pilot
URL, private commit SHA, local path, credential, or raw payload enters the public
status artifact.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_godview_project_state as generator  # noqa: E402
from generate_godview_project_state import (  # noqa: E402
    build_enigma_shadow_program,
    build_state,
    refresh_legacy_project_status,
)

STATE_ARTIFACT = ROOT / "status" / "nycif-godview-project-state-v02.json"
LEGACY_ARTIFACT = ROOT / "status" / "nycif-project-status.json"


def _normalize_generated(value):
    """Recursively replace every generated_at_utc value with a constant so two
    builds differing only by wall-clock time compare equal."""
    if isinstance(value, dict):
        return {
            k: ("<GENERATED>" if k == "generated_at_utc" else _normalize_generated(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_normalize_generated(v) for v in value]
    return value


_ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def _blank_timestamps(value):
    """Replace every embedded ISO-8601 UTC stamp (including ones interpolated
    into summary strings) so two builds differing only by wall-clock compare
    equal. Used for the deterministic-generation seam."""
    if isinstance(value, dict):
        return {k: _blank_timestamps(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_blank_timestamps(v) for v in value]
    if isinstance(value, str):
        return _ISO_UTC.sub("<GENERATED>", value)
    return value


class EnigmaShadowProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.prog = build_enigma_shadow_program()
        cls.state, cls.report = build_state(fetch_github=False)

    def test_gate_states_exact(self) -> None:
        self.assertEqual(
            self.prog["gates"],
            {"A": "complete", "B": "complete", "C": "complete", "D": "complete",
             "E": "accepted_with_conditions", "F": "owner_accepted"},
        )
        self.assertEqual(self.prog["status"], "owner_accepted_shadow_only")
        self.assertEqual(self.prog["owner_decision"], "APPROVE SHADOW-ONLY — PARK BOTH MINORS")

    def test_test_totals_exact(self) -> None:
        self.assertEqual(
            self.prog["test_totals"],
            {"isolation": 16, "enigma_core": 127, "bundle_producer": 125, "viewer": 61, "total": 329},
        )
        # total is internally consistent
        t = self.prog["test_totals"]
        self.assertEqual(t["isolation"] + t["enigma_core"] + t["bundle_producer"] + t["viewer"], t["total"])

    def test_fixture_counts_exact(self) -> None:
        self.assertEqual(
            self.prog["fixture_accounting"],
            {"requested": 12, "accepted_rows": 9, "distinct_occurrences": 7, "in_viewport": 4,
             "outside_viewport": 0, "unpinnable": 3, "duplicate_groups": 2, "silent_loss": 0},
        )
        fa = self.prog["fixture_accounting"]
        self.assertEqual(fa["in_viewport"] + fa["outside_viewport"] + fa["unpinnable"], fa["distinct_occurrences"])
        self.assertEqual(fa["silent_loss"], 0)

    def test_authority_flags(self) -> None:
        self.assertEqual(
            self.prog["authority"],
            {"v1_is_sole_production_authority": True, "shadow_only": True, "synthetic_fixture_only": True,
             "real_feed_authorized": False, "deployment_authorized": False,
             "public_promotion_authorized": False, "publication_authorized": False},
        )

    def test_shadow2_not_authorized(self) -> None:
        self.assertEqual(self.prog["next_phase"]["name"], "SHADOW-2 Gate A")
        self.assertEqual(self.prog["next_phase"]["status"], "not_authorized")
        self.assertEqual(self.prog["real_data_comparison"], "not_started")
        self.assertEqual(self.prog["production_promotion"], "not_authorized")
        self.assertEqual(self.prog["synthetic_validation"], "complete")

    def test_parked_minors_present(self) -> None:
        self.assertEqual(len(self.prog["parked_minors"]), 2)
        joined = " ".join(self.prog["parked_minors"]).lower()
        self.assertIn("json", joined)
        self.assertIn("contrast", joined)

    def test_command_center_refreshed(self) -> None:
        cc = self.state["command_center"]
        self.assertIn("SHADOW-1", cc["current_gate"])
        self.assertIn("SHADOW-2 Gate A", cc["next_gate"])
        self.assertIn("not authorized", cc["next_gate"].lower())
        # stale objective must be gone
        self.assertNotIn("Stabilize Map v1 and operate", cc["current_objective"])
        self.assertNotIn("Map chat integration (M12) on field-desk", cc["next_gate"])

    def test_state_embeds_program_and_preserves_map_v1_and_m12(self) -> None:
        self.assertEqual(self.state["enigma_shadow_program"], self.prog)
        # unrelated operational context preserved
        self.assertIn("chat_integration_handoff", self.state)
        self.assertTrue(any("Map v1 freeze" in d.get("title", "") for d in self.state["decisions"]))
        self.assertTrue(any("M12" in i.get("title", "") for i in self.state["timeline"]["next"]))
        self.assertGreater(len(self.state["workstreams"]), 0)

    def test_deterministic_apart_from_generated_time(self) -> None:
        a, _ = build_state(fetch_github=False)
        b, _ = build_state(fetch_github=False)
        self.assertEqual(_normalize_generated(a), _normalize_generated(b))
        # the program block is fully static (no timestamp inside)
        self.assertEqual(build_enigma_shadow_program(), build_enigma_shadow_program())

    def test_no_private_or_credential_or_local_path_in_public_artifact(self) -> None:
        blob = json.dumps(self.state, ensure_ascii=False)
        for forbidden in ("national-pilot", "nycif-national", "/private/tmp", "/Users/",
                          "ghp_", "github_pat_", "mock raw payload", "raw_value"):
            self.assertNotIn(forbidden, blob, f"public artifact leaks {forbidden!r}")
        # no 40-hex private commit SHA introduced by the enigma block
        self.assertFalse(re.search(r"[0-9a-f]{40}", json.dumps(self.prog)))

    def test_report_safety_flags_public_safe(self) -> None:
        self.assertTrue(self.report["safety"]["safe_for_public_dashboard"])
        self.assertFalse(self.report["safety"]["write_controls"])
        self.assertFalse(self.report["safety"]["deploy_controls"])


class LegacyProjectStatusConsistencyTests(unittest.TestCase):
    """status/nycif-project-status.json is the legacy artifact the field-desk
    admin `master-projects.html` panel consumes. It is refreshed by the same
    canonical generator entry point (main() -> refresh_legacy_project_status)
    and must not drift from the God View project state."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.prog = build_enigma_shadow_program()
        with STATE_ARTIFACT.open(encoding="utf-8") as handle:
            cls.state_artifact = json.load(handle)
        with LEGACY_ARTIFACT.open(encoding="utf-8") as handle:
            cls.legacy = json.load(handle)

    def test_committed_artifacts_carry_identical_program_block(self) -> None:
        self.assertEqual(self.state_artifact["enigma_shadow_program"], self.prog)
        self.assertEqual(self.legacy["enigma_shadow_program"], self.prog)
        self.assertEqual(self.legacy["enigma_shadow_program"], self.state_artifact["enigma_shadow_program"])

    def test_committed_legacy_headline_matches_command_center(self) -> None:
        cc = self.state_artifact["command_center"]
        self.assertEqual(self.legacy["current_phase"], cc["current_stage"])
        self.assertEqual(self.legacy["next_action"], cc["next_gate"])
        self.assertEqual(self.legacy["completion_percent"], cc["completion_percent"])
        self.assertEqual(self.legacy["health"], cc["health"])

    def test_committed_legacy_stale_claims_removed(self) -> None:
        self.assertNotEqual(
            self.legacy["current_phase"],
            "Post Map v1 freeze — GPS audit + supplemental merge + admin automation",
        )
        self.assertNotEqual(self.legacy["next_action"], "Map chat integration (M12) on field-desk")
        self.assertIn("SHADOW-1", self.legacy["current_phase"])
        self.assertIn("SHADOW-2 Gate A", self.legacy["next_action"])
        self.assertIn("not authorized", self.legacy["next_action"].lower())

    def test_committed_legacy_preserves_unrelated_project_context(self) -> None:
        for key in ("map_v1", "photographer_assignment_calendar", "civic_people_facing",
                    "viral_recurrence_memory", "admin_dashboard_urls", "recent_prs",
                    "blockers", "resolved_blockers", "safety"):
            self.assertIn(key, self.legacy, f"legacy project status lost {key!r}")
        self.assertTrue(self.legacy["map_v1"]["frozen"])
        self.assertEqual(self.legacy["artifact_type"], "nycif_project_status")
        self.assertEqual(self.legacy["visibility"], "public")

    def test_committed_legacy_is_public_safe(self) -> None:
        blob = json.dumps(self.legacy, ensure_ascii=False)
        for forbidden in ("national-pilot", "nycif-national", "/private/tmp", "/Users/",
                          "ghp_", "github_pat_", "mock raw payload", "raw_value"):
            self.assertNotIn(forbidden, blob, f"legacy project status leaks {forbidden!r}")
        self.assertFalse(re.search(r"[0-9a-f]{40}", blob))

    def test_legacy_refresh_is_deterministic_and_additive(self) -> None:
        """Deterministic-generation seam: refresh twice into clean temp copies."""
        import shutil
        import tempfile

        state, _ = build_state(fetch_github=False)
        original_status_dir = generator.STATUS
        outputs = []
        try:
            for _ in range(2):
                tmp = Path(tempfile.mkdtemp())
                shutil.copy2(LEGACY_ARTIFACT, tmp / "nycif-project-status.json")
                generator.STATUS = tmp
                refresh_legacy_project_status(state)
                with (tmp / "nycif-project-status.json").open(encoding="utf-8") as handle:
                    outputs.append(json.load(handle))
                shutil.rmtree(tmp)
        finally:
            generator.STATUS = original_status_dir

        self.assertEqual(_blank_timestamps(outputs[0]), _blank_timestamps(outputs[1]))
        self.assertEqual(outputs[0]["enigma_shadow_program"], self.prog)
        # additive: unrelated keys survive the refresh untouched
        self.assertEqual(outputs[0]["map_v1"], self.legacy["map_v1"])
        self.assertEqual(outputs[0]["photographer_assignment_calendar"],
                         self.legacy["photographer_assignment_calendar"])


if __name__ == "__main__":
    unittest.main()
