from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "public_artifacts", ROOT / "scripts/build_public_runtime_artifacts.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class PublicRuntimeArtifactTests(unittest.TestCase):
    def base(self):
        return {
            "id": "evt-1",
            "title": "Event",
            "event_role": "public_event",
            "category": "arts",
            "event_date": "2026-08-07",
            "location": "Hall",
            "borough": "Brooklyn",
            "source_dataset": "internal-source",
            "source_event_id": "internal-id",
            "priority_score": 999,
        }

    def exact_evidence(self):
        return {
            "tier": "exact_address",
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "source_provenance": "authoritative-public-source",
        }

    def test_legacy_coordinates_are_not_exact(self):
        row = self.base() | {
            "lat": 40.68,
            "lng": -73.98,
            "coordinate_status": "map_ready",
            "map_eligibility_state": "REVIEW_REQUIRED",
            "certified_pin": False,
            "address": "123 Exact Street",
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)
        self.assertNotIn("address", out.get("place", {}))

    def test_map_ready_without_certification_is_demoted(self):
        row = self.base() | {
            "lat": 40.68,
            "lng": -73.98,
            "map_eligibility_state": "MAP_READY",
            "certified_pin": False,
            "location_evidence": self.exact_evidence(),
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)

    def test_map_ready_and_certified_still_requires_evidence_contract(self):
        row = self.base() | {
            "lat": 40.68,
            "lng": -73.98,
            "map_eligibility_state": "MAP_READY",
            "certified_pin": True,
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)

    def test_semantic_exact_authority_can_publish_coordinates(self):
        row = self.base() | {
            "lat": 40.68,
            "lng": -73.98,
            "map_eligibility_state": "MAP_READY",
            "certified_pin": True,
            "address": "123 Public Street",
            "location_evidence": self.exact_evidence(),
        }
        out = MOD.project_event(row)
        self.assertTrue(out["certified_pin"])
        self.assertEqual(out["latitude"], 40.68)
        self.assertEqual(out["longitude"], -73.98)
        self.assertEqual(out["place"]["address"], "123 Public Street")

    def test_general_area_never_publishes_exact_location(self):
        row = self.base() | {
            "lat": 40.68,
            "lng": -73.98,
            "address": "123 Exact Street",
            "location": "Exact Venue",
            "general_area_label": "Downtown Brooklyn",
            "neighborhood": "Downtown Brooklyn",
            "map_eligibility_state": "GENERAL_AREA",
            "certified_pin": False,
            "location_evidence": {
                "tier": "approximate_area",
                "validation_state": "validated",
            },
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "GENERAL_AREA")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)
        self.assertNotIn("address", out.get("place", {}))
        self.assertNotIn("location", out.get("place", {}))
        self.assertEqual(out["place"]["general_area_label"], "Downtown Brooklyn")

    def test_source_and_ranking_fields_are_removed_and_id_is_opaque(self):
        out = MOD.project_event(
            self.base()
            | {
                "map_eligibility_state": "LIST_ONLY",
                "certified_pin": False,
            }
        )
        encoded = json.dumps(out)
        self.assertNotIn("internal-source", encoded)
        self.assertNotIn("internal-id", encoded)
        self.assertNotIn("priority_score", encoded)
        self.assertNotIn("source_dataset", encoded)
        self.assertTrue(out["id"].startswith("evt_"))
        self.assertNotEqual(out["id"], "evt-1")

    def test_parent_nonpublic_and_missing_roles_are_suppressed(self):
        self.assertIsNone(MOD.project_event(self.base() | {"parent_event_id": "root"}))
        self.assertIsNone(MOD.project_event(self.base() | {"event_role": "media_event"}))
        row = dict(self.base())
        row.pop("event_role")
        self.assertIsNone(MOD.project_event(row))

    def test_scan_rejects_all_internal_url_fragments_and_denied_key(self):
        for url in (
            "https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/x.json",
            "https://github.com/setoxxx/nycif-live-feeds/blob/main/x.json",
            "https://setoxxx.github.io/nycif-field-desk/",
            "http://localhost:8000/internal",
        ):
            with self.subTest(url=url):
                with self.assertRaises(MOD.PublicArtifactError):
                    MOD.scan({"url": url})
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.scan({"priority_score": 100})
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.scan({"location_evidence": {"tier": "exact_address"}})

    def test_malformed_payload_fails_closed(self):
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.rows({"not_events": []})

    def test_duplicate_public_occurrence_ids_fail_closed(self):
        row = self.base() | {
            "map_eligibility_state": "LIST_ONLY",
            "certified_pin": False,
        }
        projected = [MOD.project_event(row), MOD.project_event(dict(row))]
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.ensure_unique_public_ids(projected, scope="test")

    def test_end_to_end_build(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            approved = root / "approved"
            (approved / "pages").mkdir(parents=True)
            major = root / "major/events.json"
            major.parent.mkdir(parents=True)
            source_rows = [
                self.base()
                | {
                    "map_eligibility_state": "LIST_ONLY",
                    "certified_pin": False,
                    "lat": 40.7,
                    "lng": -74.0,
                }
            ]
            (approved / "pages/page-0001.json").write_text(
                json.dumps(source_rows), encoding="utf-8"
            )
            (approved / "manifest.json").write_text(
                json.dumps({"pages": [{"page": "page-0001.json"}]}), encoding="utf-8"
            )
            major.write_text(json.dumps({"events": source_rows}), encoding="utf-8")
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

    def test_failed_publish_restores_previous_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "public-data"
            output.mkdir()
            (output / "sentinel.txt").write_text("old", encoding="utf-8")
            staged = root / "staged"
            staged.mkdir()
            (staged / "sentinel.txt").write_text("new", encoding="utf-8")
            real_replace = MOD.os.replace
            calls = {"count": 0}

            def flaky_replace(src, dst):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise OSError("simulated final swap failure")
                return real_replace(src, dst)

            with mock.patch.object(MOD.os, "replace", side_effect=flaky_replace):
                with self.assertRaises(OSError):
                    MOD._publish_staged(staged, output)

            self.assertTrue(output.exists())
            self.assertEqual((output / "sentinel.txt").read_text(), "old")


if __name__ == "__main__":
    unittest.main()
