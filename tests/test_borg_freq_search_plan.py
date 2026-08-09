from __future__ import annotations

import unittest

from scripts.borg_freq_search_plan import build_search_plan


class BorgFreqSearchPlanTests(unittest.TestCase):
    def setUp(self):
        self.observation = {
            "freq_observation_id": "freq-obs-001",
            "observed_at": "2026-08-09T20:00:00Z",
            "jurisdiction_id": "NYC",
            "service_class": "FIRE_EMS",
            "rights_state": "PUBLIC_SEARCH_ALLOWED",
            "sensitivity_state": "NON_TACTICAL",
            "location_state": "ambiguous",
            "location_evidence_ref": "freq:location:001",
            "terminology_refs": ["alarm"],
            "provenance_ref": "freq:obs:001",
            "public_area_label": "Brooklyn",
            "public_summary_terms": ["fire", "street closure"],
        }
        self.sources = [
            {
                "source_id": "nyc-official",
                "source_tier": "A",
                "jurisdiction": "NYC",
                "canonical_url": "https://example.nyc.gov/feed",
                "authentication_mode": "NONE",
                "network_scope": "PUBLIC",
                "registration_state": "ACTIVE",
                "rights": {"retrieval_allowed": True, "review_state": "APPROVED"},
            },
            {
                "source_id": "discovery",
                "source_tier": "D",
                "jurisdiction": "NYC",
                "canonical_url": "https://example.org/search",
                "authentication_mode": "NONE",
                "network_scope": "PUBLIC",
                "registration_state": "ACTIVE",
                "rights": {"retrieval_allowed": True, "review_state": "APPROVED"},
            },
            {
                "source_id": "blocked-private",
                "source_tier": "A",
                "jurisdiction": "NYC",
                "canonical_url": "http://127.0.0.1/private",
                "authentication_mode": "NONE",
                "network_scope": "LOOPBACK",
                "registration_state": "ACTIVE",
                "rights": {"retrieval_allowed": True, "review_state": "APPROVED"},
            },
        ]

    def test_ambiguous_location_stays_area_only(self):
        result = build_search_plan(observation=self.observation, sources=self.sources)
        self.assertEqual(result["intent_count"], 2)
        self.assertTrue(all(item["location_scope"] == "AREA_OR_JURISDICTION_ONLY" for item in result["intents"]))
        self.assertTrue(all(item["public_location_id"] is None for item in result["intents"]))
        self.assertTrue(all(item["result_authority"] == "OBSERVATION_OR_LEAD_ONLY" for item in result["intents"]))

    def test_official_source_is_corroboration_and_tier_d_is_lead(self):
        result = build_search_plan(observation=self.observation, sources=self.sources)
        by_id = {item["source_id"]: item for item in result["intents"]}
        self.assertEqual(by_id["nyc-official"]["purpose"], "CORROBORATE_OFFICIAL_PUBLIC_RECORD")
        self.assertEqual(by_id["discovery"]["purpose"], "DISCOVER_CORROBORATING_LEAD")

    def test_private_source_is_excluded(self):
        result = build_search_plan(observation=self.observation, sources=self.sources)
        row = next(item for item in result["excluded_sources"] if item["source_id"] == "blocked-private")
        self.assertEqual(row["reason"], "NON_PUBLIC_NETWORK_SCOPE")

    def test_sensitive_bridge_field_fails_closed(self):
        observation = dict(self.observation)
        observation["raw_audio"] = "never allowed"
        with self.assertRaises(ValueError):
            build_search_plan(observation=observation, sources=self.sources)

    def test_rights_or_sensitivity_not_cleared_fails_closed(self):
        observation = dict(self.observation)
        observation["rights_state"] = "REVIEW_REQUIRED"
        with self.assertRaises(ValueError):
            build_search_plan(observation=observation, sources=self.sources)
        observation = dict(self.observation)
        observation["sensitivity_state"] = "TACTICAL"
        with self.assertRaises(ValueError):
            build_search_plan(observation=observation, sources=self.sources)

    def test_resolved_location_requires_public_location_id_for_exact_scope(self):
        observation = dict(self.observation)
        observation["location_state"] = "resolved"
        without_id = build_search_plan(observation=observation, sources=self.sources)
        self.assertTrue(all(item["location_scope"] == "AREA_OR_JURISDICTION_ONLY" for item in without_id["intents"]))
        observation["public_location_id"] = "loc-public-123"
        with_id = build_search_plan(observation=observation, sources=self.sources)
        self.assertTrue(all(item["location_scope"] == "EXACT_AUTHORIZED_LOCATION" for item in with_id["intents"]))

    def test_intent_ids_are_deterministic(self):
        a = build_search_plan(observation=self.observation, sources=self.sources)
        b = build_search_plan(observation=self.observation, sources=self.sources)
        self.assertEqual([row["intent_id"] for row in a["intents"]], [row["intent_id"] for row in b["intents"]])


if __name__ == "__main__":
    unittest.main()
