from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pin_integrity
from occurrence_identity_contract import occurrence_key_v2

SPEC = importlib.util.spec_from_file_location(
    "public_artifacts", SCRIPTS / "build_public_runtime_artifacts.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class PublicRuntimeArtifactIntegrationTests(unittest.TestCase):
    def base(self):
        return {
            "id": "evt-1",
            "title": "Event",
            "event_role": "public_event",
            "category": "arts",
            "start_date_time": "2026-08-07T12:00:00-04:00",
            "event_date": "2026-08-07",
            "location": "Hall",
            "borough": "Brooklyn",
            "source_dataset": "internal-source",
            "source_event_id": "internal-id",
            "priority_score": 999,
        }

    def exact_evidence(self, **overrides):
        evidence = {
            "tier": "exact_address",
            "validation_state": "validated",
            "exact_pin_eligible": True,
            "source_provenance": "authoritative-public-source",
        }
        evidence.update(overrides)
        return evidence

    def exact_row(self, **overrides):
        row = self.base() | {
            "latitude": 40.68,
            "longitude": -73.98,
            "map_eligibility_state": "MAP_READY",
            "certified_pin": True,
            "address": "123 Public Street",
            "location_evidence": self.exact_evidence(),
        }
        row.update(overrides)
        return row

    def test_builder_uses_shared_location_authority(self):
        self.assertIs(MOD.evaluate_map_eligibility, pin_integrity.evaluate_map_eligibility)

    def test_coordinates_without_evidence_cannot_publish_exact_pin(self):
        row = self.base() | {
            "latitude": 40.68,
            "longitude": -73.98,
            "coordinate_status": "map_ready",
            "certified_pin": True,
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)

    def test_legacy_map_ready_is_not_authority(self):
        row = self.base() | {
            "latitude": 40.68,
            "longitude": -73.98,
            "coordinate_status": "map_ready",
            "certified_pin": False,
        }
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])

    def test_forged_map_ready_text_with_invalid_evidence_fails_closed(self):
        row = self.exact_row(
            location_evidence=self.exact_evidence(validation_state="unvalidated"),
        )
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)
        self.assertNotIn("longitude", out)

    def test_general_area_with_centroid_never_publishes_exact_location(self):
        row = self.base() | {
            "latitude": 40.68,
            "longitude": -73.98,
            "address": "123 Exact Street",
            "location": "Exact Venue",
            "general_area_label": "Downtown Brooklyn",
            "neighborhood": "Downtown Brooklyn",
            "certified_pin": False,
            "location_evidence": {
                "tier": "approximate_area",
                "validation_state": "validated",
                "exact_pin_eligible": False,
                "source_provenance": "generalized-public-area",
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

    def test_borough_contradiction_represented_as_invalid_validation_is_not_exact(self):
        row = self.exact_row(
            location_evidence=self.exact_evidence(validation_state="conflict"),
        )
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])

    def test_zip_contradiction_represented_as_invalid_validation_is_not_exact(self):
        row = self.exact_row(
            location_evidence=self.exact_evidence(validation_state="conflict"),
        )
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])

    def test_validated_exact_evidence_and_certified_claim_can_publish_coordinates(self):
        row = self.exact_row()
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "MAP_READY")
        self.assertTrue(out["certified_pin"])
        self.assertEqual(out["latitude"], 40.68)
        self.assertEqual(out["longitude"], -73.98)
        self.assertEqual(out["place"]["address"], "123 Public Street")

    def test_shared_authority_without_upstream_certified_claim_cannot_publish_exact(self):
        row = self.exact_row(certified_pin=False)
        decision = pin_integrity.evaluate_map_eligibility(row)
        self.assertEqual(decision["map_eligibility"], "MAP_READY")
        out = MOD.project_event(row)
        self.assertEqual(out["map_eligibility_state"], "REVIEW_REQUIRED")
        self.assertFalse(out["certified_pin"])
        self.assertNotIn("latitude", out)

    def test_parent_and_supporting_rows_never_become_public_events(self):
        self.assertIsNone(MOD.project_event(self.exact_row(parent_event_id="root")))
        self.assertIsNone(MOD.project_event(self.exact_row(event_role="supporting_permit")))

    def test_public_id_uses_canonical_occurrence_v2_and_is_opaque(self):
        row = self.base()
        same = dict(row)
        later = dict(row, start_date_time="2026-08-07T18:30:00-04:00")
        other_day = dict(row, start_date_time="2026-08-08T12:00:00-04:00", event_date="2026-08-08")
        self.assertEqual(occurrence_key_v2(row), occurrence_key_v2(same))
        self.assertEqual(MOD.public_event_id(row), MOD.public_event_id(same))
        self.assertNotEqual(MOD.public_event_id(row), MOD.public_event_id(later))
        self.assertNotEqual(MOD.public_event_id(row), MOD.public_event_id(other_day))
        encoded = MOD.public_event_id(row)
        self.assertTrue(encoded.startswith("evt_"))
        self.assertNotIn("internal-source", encoded)
        self.assertNotIn("internal-id", encoded)

    def test_ambiguous_occurrence_identity_fails_closed(self):
        row = self.base()
        row.pop("start_date_time")
        row.pop("event_date")
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.public_event_id(row)

    def test_duplicate_canonical_occurrence_identity_fails_build_projection(self):
        row = self.base() | {"certified_pin": False}
        with self.assertRaises(MOD.PublicArtifactError):
            MOD.project([row, dict(row)], scope="duplicate-test")

    def test_source_ranking_evidence_and_internal_urls_are_denied(self):
        out = MOD.project_event(self.base() | {"certified_pin": False})
        encoded = json.dumps(out)
        for secret in ("internal-source", "internal-id", "priority_score", "source_dataset"):
            self.assertNotIn(secret, encoded)
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
            MOD.scan({"location_evidence": {"tier": "exact_address"}})

    def test_page_date_bounds_ignore_malformed_dates(self):
        events = [
            {"event_date": "2026-08-09"},
            {"start_date_time": "2026-08-07T12:00:00-04:00"},
            {"when": {"event_date": "not-a-date"}},
        ]
        self.assertEqual(MOD.page_date_bounds(events), ("2026-08-07", "2026-08-09"))
        self.assertEqual(MOD.page_date_bounds([]), (None, None))

    def test_end_to_end_build_emits_reader_safe_manifest_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            approved = root / "approved"
            (approved / "pages").mkdir(parents=True)
            major = root / "major/events.json"
            major.parent.mkdir(parents=True)
            source_rows = [self.base() | {"certified_pin": False}]
            (approved / "pages/page-0001.json").write_text(json.dumps(source_rows), encoding="utf-8")
            (approved / "manifest.json").write_text(
                json.dumps({"pages": [{"page": "page-0001.json"}]}), encoding="utf-8"
            )
            major.write_text(json.dumps({"events": source_rows}), encoding="utf-8")
            output = root / "public-data"
            report = MOD.build(approved / "manifest.json", major, output, "abc123")
            self.assertTrue(report["qa_pass"])
            manifest = json.loads((output / "events/manifest.json").read_text())
            self.assertEqual(manifest["major_feed"], "major/events.json")
            self.assertEqual(manifest["pages"][0]["earliest_date"], "2026-08-07")
            self.assertEqual(manifest["pages"][0]["latest_date"], "2026-08-07")
            emitted = json.loads((output / "events/pages/page-0001.json").read_text())
            encoded = json.dumps(emitted)
            self.assertNotIn("internal-source", encoded)
            self.assertNotIn("priority_score", encoded)
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
