from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_artifacts", ROOT / "scripts/build_public_runtime_artifacts.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class PublicRuntimeArtifactTests(unittest.TestCase):
    def base(self):
        return {
            "id": "evt-1", "title": "Event", "event_role": "public_event",
            "category": "arts", "event_date": "2026-08-07", "location": "Hall",
            "borough": "Brooklyn", "source_dataset": "internal-source",
            "source_event_id": "internal-id", "priority_score": 999,
        }

    def test_legacy_coordinates_are_not_exact(self):
        row = self.base() | {
            "lat": 40.68, "lng": -73.98, "coordinate_status": "map_ready",
            "map_eligibility_state": "REVIEW_REQUIRED", "certified_pin": False,
            "address": "123 Exact Street",
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)
        self.assertNotIn("address", out.get("place", {}))

    def test_semantic_exact_authority_can_publish_coordinates(self):
        row = self.base() | {
            "lat": 40.68, "lng": -73.98,
            "map_eligibility_state": "MAP_READY", "certified_pin": True,
            "address": "123 Public Street",
        }
        out = MOD.project_event(row)
        self.assertTrue(out["certified_pin"])
        self.assertEqual(out["latitude"], 40.68)
        self.assertEqual(out["longitude"], -73.98)
        self.assertEqual(out["place"]["address"], "123 Public Street")

    def test_source_and_ranking_fields_are_removed(self):
        out = MOD.project_event(self.base() | {"map_eligibility_state": "LIST_ONLY", "certified_pin": False})
        encoded = json.dumps(out)
        self.assertNotIn("internal-source", encoded)
        self.assertNotIn("internal-id", encoded)
        self.assertNotIn("priority_score", encoded)
        self.assertNotIn("source_dataset", encoded)

    def test_parent_and_nonpublic_roles_are_suppressed(self):
        self.assertIsNone(MOD.project_event(self.base() | {"parent_event_id": "root"}))
        self.assertIsNone(MOD.project_event(self.base() | {"event_role": "media_event"}))

    def test_scan_rejects_private_repo_url_and_denied_key(self):
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.scan({"url": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/x.json"})
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.scan({"priority_score": 100})

    def test_end_to_end_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            approved = root / "approved"
            (approved / "pages").mkdir(parents=True)
            major = root / "major/events.json"
            major.parent.mkdir(parents=True)
            rows = [self.base() | {"map_eligibility_state": "LIST_ONLY", "certified_pin": False, "lat": 40.7, "lng": -74.0}]
            (approved / "pages/page-0001.json").write_text(json.dumps(rows), encoding="utf-8")
            (approved / "manifest.json").write_text(json.dumps({"pages": [{"page": "page-0001.json"}]}), encoding="utf-8")
            major.write_text(json.dumps({"events": rows}), encoding="utf-8")
            output = root / "public-data"
            report = MOD.build(approved / "manifest.json", major, output, "abc123")
            self.assertTrue(report["qa_pass"])
            emitted = json.loads((output / "events/pages/page-0001.json").read_text())
            encoded = json.dumps(emitted)
            self.assertNotIn("internal-source", encoded)
            self.assertNotIn("latitude", encoded)
            self.assertNotIn("longitude", encoded)
            artifact_manifest = json.loads((output / "artifact-manifest.json").read_text())
            self.assertTrue(artifact_manifest["artifacts"])

if __name__ == "__main__":
    unittest.main()
