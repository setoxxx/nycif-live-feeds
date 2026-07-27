#!/usr/bin/env python3
"""Static contract tests for the protected City Engine WordPress staging bridge."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "docs/wordpress-plugin-deploy/nycif-city-engine-staging/nycif-city-engine-staging.php"
README = ROOT / "docs/wordpress-plugin-deploy/nycif-city-engine-staging/README.md"
PUBLIC_PLUGIN = ROOT / "docs/wordpress-plugin-deploy/nycif-events-map/nycif-events-map.php"


class CityEngineWordPressStagingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PLUGIN.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")
        cls.public_source = PUBLIC_PLUGIN.read_text(encoding="utf-8")

    def test_companion_plugin_exists(self):
        self.assertTrue(PLUGIN.exists())
        self.assertIn("Plugin Name: NYCIF City Engine Staging", self.source)

    def test_staging_shortcode_is_separate_from_public_shortcode(self):
        self.assertIn("nycif_city_engine_staging", self.source)
        self.assertNotIn("add_shortcode('nycif_events_map'", self.source)
        self.assertIn("add_shortcode('nycif_events_map'", self.public_source)

    def test_requires_authenticated_editor_and_designated_draft(self):
        for token in (
            "is_user_logged_in()",
            "current_user_can(NYCIF_CITY_ENGINE_STAGING_CAPABILITY)",
            "is_page(NYCIF_CITY_ENGINE_STAGING_PAGE_ID)",
            "'draft' === get_post_status(NYCIF_CITY_ENGINE_STAGING_PAGE_ID)",
            "define('NYCIF_CITY_ENGINE_STAGING_PAGE_ID', 2865)",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_unauthorized_response_is_generic(self):
        self.assertIn("This preview is not available.", self.source)
        unauthorized_function = self.source.split("function nycif_city_engine_staging_unavailable", 1)[1].split("function nycif_city_engine_staging_request_is_authorized", 1)[0]
        self.assertNotIn("2865", unauthorized_function)
        self.assertNotIn("setoxxx", unauthorized_function)
        self.assertNotIn("manifest", unauthorized_function.lower())

    def test_manifest_is_local_commit_pinned_and_hash_verified(self):
        required_tokens = (
            "source_repository",
            "source_commit",
            "entrypoint_sha256",
            "setoxxx/nycif-web-platform",
            "preg_match('/^[0-9a-f]{40}$/",
            "preg_match('/^[0-9a-f]{64}$/",
            "hash_file('sha256'",
            "hash_equals(",
            "plugins_url($entrypoint, __FILE__)",
        )
        for token in required_tokens:
            with self.subTest(token=token):
                self.assertIn(token, self.source)

    def test_remote_and_traversal_paths_are_rejected(self):
        self.assertIn("strpos($entrypoint, '..')", self.source)
        self.assertRegex(self.source, re.compile(r"preg_match\('#\^\[a-z\]"))
        self.assertIn("realpath(__DIR__ . '/' . $entrypoint)", self.source)

    def test_iframe_uses_restrictive_browser_policy(self):
        for token in (
            'referrerpolicy="no-referrer"',
            'sandbox="allow-scripts allow-same-origin"',
            'allow="fullscreen"',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)
        self.assertNotIn("allow=\"geolocation", self.source)

    def test_documentation_preserves_no_public_change_boundary(self):
        for phrase in (
            "Fail closed",
            "does not",
            "modify public page 2647 or `/map/`",
            "change the existing `[nycif_events_map]` shortcode",
            "change `feeds=main`",
            "publish or deploy anything",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.readme)


if __name__ == "__main__":
    unittest.main(verbosity=2)
