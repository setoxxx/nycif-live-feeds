from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("shadow_release", SCRIPTS / "build_public_shadow_release.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ShadowReleaseTests(unittest.TestCase):
    def row(self):
        return {
            "id": "evt-1",
            "title": "Public Event",
            "event_role": "public_event",
            "category": "arts",
            "start_date_time": "2026-08-07T12:00:00-04:00",
            "event_date": "2026-08-07",
            "location": "Hall",
            "borough": "Brooklyn",
            "source_dataset": "private-source-id",
            "source_event_id": "private-event-id",
            "certified_pin": False,
        }

    def fixture(self, root: Path):
        approved = root / "approved"
        pages = approved / "pages"
        pages.mkdir(parents=True)
        rows = [self.row()]
        (pages / "page-0001.json").write_text(json.dumps(rows), encoding="utf-8")
        manifest = approved / "manifest.json"
        manifest.write_text(json.dumps({"pages": [{"page": "page-0001.json"}]}), encoding="utf-8")
        major = root / "major/events.json"
        major.parent.mkdir(parents=True)
        major.write_text(json.dumps({"events": rows}), encoding="utf-8")
        return manifest, major

    def mission_control_evidence(self, root: Path, release_sha: str = "abcdef1") -> Path:
        path = root / "mission-control-evidence.json"
        path.write_text(json.dumps({
            "certified": True,
            "generated_at": "2026-08-07T16:45:00Z",
            "release_id": f"release-{release_sha}",
            "release_sha": release_sha,
            "current_pointer": "current/release.json",
            "data_health": "READY",
            "sources": [
                {"label": "Permitted Events", "health": "FRESH", "last_success_age_seconds": 60, "safe_event_count": 12, "last_release_id": f"release-{release_sha}"},
                {"label": "Citywide Calendar", "health": "FRESH", "last_success_age_seconds": 120, "safe_event_count": 8, "last_release_id": f"release-{release_sha}"},
                {"label": "Parks BigApps", "health": "UNAVAILABLE", "last_success_age_seconds": None, "safe_event_count": None, "last_release_id": f"release-{release_sha}"},
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
        }), encoding="utf-8")
        return path

    def test_release_is_versioned_and_current_is_pointer_directory(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, major = self.fixture(root)
            shadow = root / "shadow"
            out = MOD.build_shadow_release(manifest, major, shadow, "abcdef1", "1234567")
            self.assertTrue(out["qa_pass"])
            release = shadow / "releases/abcdef1"
            self.assertTrue((release / "events/manifest.json").exists())
            self.assertTrue((release / "events/major/events.json").exists())
            self.assertTrue((release / "artifact-manifest.json").exists())
            self.assertTrue((release / "health/public-summary.json").exists())
            self.assertTrue((release / "PUBLIC_DATA_SHADOW_RELEASE_MANIFEST.json").exists())
            pointer = json.loads((shadow / "current/release.json").read_text())
            self.assertEqual(pointer["release_sha"], "abcdef1")
            self.assertEqual(pointer["rollback_release_sha"], "1234567")
            self.assertFalse(pointer["publication_authorized"])
            self.assertFalse(out["mission_control_summary_present"])

    def test_summary_is_in_same_release_and_manifest_hashes_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, major = self.fixture(root)
            evidence = self.mission_control_evidence(root)
            shadow = root / "shadow"
            out = MOD.build_shadow_release(manifest, major, shadow, "abcdef1", "1234567", evidence)
            self.assertTrue(out["mission_control_summary_present"])
            release = shadow / "releases/abcdef1"
            summary_path = release / "mission-control-summary.json"
            self.assertTrue(summary_path.exists())
            summary = json.loads(summary_path.read_text())
            self.assertEqual(summary["release_sha"], "abcdef1")
            self.assertEqual(summary["rollback_release"], "1234567")
            release_manifest = json.loads((release / "PUBLIC_DATA_SHADOW_RELEASE_MANIFEST.json").read_text())
            self.assertTrue(release_manifest["mission_control_summary_present"])
            item = next(row for row in release_manifest["artifacts"] if row["path"] == "mission-control-summary.json")
            self.assertEqual(item["sha256"], MOD.sha256(summary_path))

    def test_summary_release_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, major = self.fixture(root)
            evidence = self.mission_control_evidence(root, "7654321")
            with self.assertRaises(Exception):
                MOD.build_shadow_release(manifest, major, root / "shadow", "abcdef1", None, evidence)

    def test_public_health_has_exact_allowlist_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, major = self.fixture(root)
            shadow = root / "shadow"
            MOD.build_shadow_release(manifest, major, shadow, "abcdef1")
            health = json.loads((shadow / "releases/abcdef1/health/public-summary.json").read_text())
            self.assertEqual(set(health), MOD.ALLOWED_HEALTH_KEYS)
            MOD.validate_health(health)
            encoded = json.dumps(health).lower()
            for token in MOD.DENIED_HEALTH_TOKENS:
                self.assertNotIn(token, encoded)

    def test_release_manifest_contains_hash_size_and_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, major = self.fixture(root)
            shadow = root / "shadow"
            MOD.build_shadow_release(manifest, major, shadow, "abcdef1", "1234567")
            payload = json.loads((shadow / "releases/abcdef1/PUBLIC_DATA_SHADOW_RELEASE_MANIFEST.json").read_text())
            self.assertEqual(payload["release_sha"], "abcdef1")
            self.assertEqual(payload["rollback_release_sha"], "1234567")
            self.assertGreater(payload["file_count"], 0)
            self.assertGreater(payload["total_size_bytes"], 0)
            self.assertTrue(all(item["sha256"] and item["size_bytes"] >= 0 for item in payload["artifacts"]))
            self.assertFalse(payload["publication_authorized"])

    def test_invalid_release_sha_fails_closed(self):
        with self.assertRaises(Exception):
            MOD.validate_release_sha("not-a-sha")

    def test_same_release_cannot_be_rollback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest, major = self.fixture(root)
            with self.assertRaises(Exception):
                MOD.build_shadow_release(manifest, major, root / "shadow", "abcdef1", "abcdef1")


if __name__ == "__main__":
    unittest.main()
