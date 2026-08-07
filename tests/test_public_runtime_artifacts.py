from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "build_public_runtime_artifacts.py"
SPEC = importlib.util.spec_from_file_location("build_public_runtime_artifacts", MODULE_PATH)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class PublicRuntimeArtifactTests(unittest.TestCase):
    def base_event(self) -> dict:
        return {
            "id": "evt-1",
            "title": "Public Event",
            "event_role": "public_event",
            "category": "arts",
            "event_date": "2026-08-07",
            "start_date_time": "2026-08-07T18:00:00-04:00",
            "location": "Example Hall",
            "borough": "Brooklyn",
            "source_dataset": "private-internal-source",
            "source_event_id": "secret-upstream-id",
            "priority_score": 999,
            "review_notes": "internal review only",
        }

    def test_legacy_coordinates_do_not_create_exact_public_pin(self) -> None:
        row = self.base_event()
        row.update(
            {
                "lat": 40.68,
                "lng": -73.98,
                "coordinate_status": "map_ready",
                "map_eligibility_state": "REVIEW_REQUIRED",
                "certified_pin": False,
                "address": "123 Private Exact Street",
            }
        )
        projected = MOD.project_event(row)
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertFalse(projected["certified_pin"])
        self.assertEqual(projected["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertNotIn("latitude", projected)
        self.assertNotIn("longitude", projected)
        self.assertNotIn("address", projected.get("place", {}))

    def test_semantic_exact_authority_can_publish_coordinates(self) -> None:
        row = self.base_event()
        row.update(
            {
                "lat": 40.68,
                "lng": -73.98,
                "map_eligibility_state": "MAP_READY",
                "certified_pin": True,
                "address": "123 Public Street",
            }
        )
        projected = MOD.project_event(row)
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertTrue(projected["certified_pin"])
        self.assertEqual(projected["map_eligibility_state"], "MAP_READY")
        self.assertEqual(projected["latitude"], 40.68)
        self.assertEqual(projected["longitude"], -73.98)
        self.assertEqual(projected["place"]["address"], "123 Public Street")

    def test_private_source_and_ranking_fields_are_not_projected(self) -> None:
        row = self.base_event()
        row.update({"map_eligibility_state": "LIST_ONLY", "certified_pin": False})
        projected = MOD.project_event(row)
        self.assertIsNotNone(projected)
        assert projected is not None
        encoded = json.dumps(projected)
        self.assertNotIn("private-internal-source", encoded)
        self.assertNotIn("secret-upstream-id", encoded)
        self.assertNotIn("priority_score", encoded)
        self.assertNotIn("review_notes", encoded)
        self.assertNotIn("source_dataset", encoded)
        self.assertNotIn("source_event_id", encoded)

    def test_parent_and_non_public_roles_are_not_emitted(self) -> None:
        parent = self.base_event()
        parent["parent_event_id"] = "root-event"
        self.assertIsNone(MOD.project_event(parent))

        media = self.base_event()
        media["event_role"] = "media_event"
        self.assertIsNone(MOD.project_event(media))

    def test_public_payload_scan_rejects_private_repo_url(self) -> None:
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.scan_public_payload(
                {"url": "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/private.json"}
            )

    def test_public_payload_scan_rejects_denied_key(self) -> None:
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.scan_public_payload({"title": "ok", "priority_score": 100})

    def test_end_to_end_build_writes_reader_safe_manifest_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            approved = root / "approved"
            pages = approved / "pages"
            major = root / "major" / "events.json"
            pages.mkdir(parents=True)
            major.parent.mkdir(parents=True)

            page_events = [
                {
                    **self.base_event(),
                    "map_eligibility_state": "LIST_ONLY",
                    "certified_pin": False,
                    "lat": 40.7,
                    "lng": -74.0,
                }
            ]
            (pages / "page-0001.json").write_text(json.dumps(page_events), encoding="utf-8")
            (approved / "manifest.json").write_text(
                json.dumps({"pages": [{"page": "page-0001.json"}]}), encoding="utf-8"
            )
            major.write_text(json.dumps({"events": page_events}), encoding="utf-8")

            output = root / "public-data"
            report = MOD.build(
                approved_manifest=approved / "manifest.json",
                major_events=major,
                output_root=output,
                release_sha="abc123",
            )
            self.assertTrue(report["qa_pass"])
            public_manifest = json.loads((output / "events" / "manifest.json").read_text())
            self.assertEqual(public_manifest["release_sha"], "abc123")
            artifact_manifest = json.loads((output / "artifact-manifest.json").read_text())
            self.assertTrue(artifact_manifest["artifacts"])
            emitted = json.loads((output / "events" / "pages" / "page-0001.json").read_text())
            encoded = json.dumps(emitted)
            self.assertNotIn("private-internal-source", encoded)
            self.assertNotIn("latitude", encoded)
            self.assertNotIn("longitude", encoded)


if __name__ == "__main__":
    unittest.main()
