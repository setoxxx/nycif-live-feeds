#!/usr/bin/env python3
"""Validate the reviewed City Engine staging bundle metadata without authorizing installation."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "docs/wordpress-plugin-deploy/nycif-city-engine-staging/reviewed-bundles/73fd0fe"
MANIFEST = REVIEW / "city-engine-staging-manifest.json"
REPORT = REVIEW / "bundle-report.json"
PROVENANCE = REVIEW / "provenance.json"
EXPECTED_COMMIT = "73fd0fe8118b0915de1152b40f3cd5623986ace4"
EXPECTED_ENTRYPOINT_HASH = "e3951f76d29cb72b14a558884c800fb2703d0cf2998941e453b8fc3e4b7bf7fb"


class ReviewedBundleProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))

    def test_exact_source_identity(self):
        for payload in (self.manifest, self.report, self.provenance):
            self.assertEqual(payload["source_repository"], "setoxxx/nycif-web-platform")
            self.assertEqual(payload["source_commit"], EXPECTED_COMMIT)
        self.assertRegex(EXPECTED_COMMIT, r"^[0-9a-f]{40}$")

    def test_manifest_is_complete_and_internally_consistent(self):
        self.assertEqual(self.manifest["schema_version"], "1")
        self.assertEqual(self.manifest["file_count"], 34)
        self.assertEqual(len(self.manifest["files_sha256"]), 34)
        self.assertEqual(self.manifest["entrypoint_sha256"], EXPECTED_ENTRYPOINT_HASH)
        self.assertEqual(
            self.manifest["files_sha256"][self.manifest["entrypoint"]],
            EXPECTED_ENTRYPOINT_HASH,
        )
        for path, digest in self.manifest["files_sha256"].items():
            self.assertTrue(path.startswith("assets/city-engine/"))
            self.assertNotIn("..", path)
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_report_matches_manifest(self):
        self.assertEqual(self.report["file_count"], self.manifest["file_count"])
        self.assertEqual(self.report["entrypoint"], self.manifest["entrypoint"])
        self.assertEqual(self.report["entrypoint_sha256"], EXPECTED_ENTRYPOINT_HASH)
        self.assertEqual(self.report["safety_scan"], "passed")
        self.assertFalse(self.report["writes_wordpress"])
        self.assertFalse(self.report["publishes"])

    def test_artifact_and_package_hashes_are_immutable(self):
        self.assertEqual(self.provenance["source_workflow_run_id"], 30313903626)
        self.assertEqual(self.provenance["source_workflow_artifact_id"], 8671412101)
        self.assertRegex(self.provenance["source_workflow_artifact_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(self.provenance["deterministic_asset_zip_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(self.provenance["assembled_plugin_zip_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(self.provenance["entrypoint_sha256"], EXPECTED_ENTRYPOINT_HASH)

    def test_no_authorization_is_implied(self):
        for payload in (self.manifest, self.provenance):
            self.assertFalse(payload["production_authorized"])
            self.assertFalse(payload["wordpress_install_authorized"])
        self.assertFalse(self.provenance["wordpress_page_update_authorized"])
        self.assertFalse(self.provenance["publishes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
