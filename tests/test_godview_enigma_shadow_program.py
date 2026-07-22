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

from generate_godview_project_state import (  # noqa: E402
    build_enigma_shadow_program,
    build_state,
)


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


if __name__ == "__main__":
    unittest.main()
