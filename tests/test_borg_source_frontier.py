from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.borg_source_frontier import build_frontier


class BorgSourceFrontierTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 9, 20, 30, tzinfo=timezone.utc)
        self.gaps = [{
            "gap_id": "gap-nyc-public-safety",
            "priority_class": "PUBLIC_SAFETY_OR_CIVIC_TIME_SENSITIVITY",
            "candidate_source_ids": ["official", "discovery", "blocked"],
        }]
        self.sources = [
            {
                "source_id": "official",
                "source_tier": "A",
                "canonical_url": "https://example.gov/feed.json",
                "rights": {"retrieval_allowed": True},
                "authentication_mode": "NONE",
                "network_scope": "PUBLIC",
                "health": "HEALTHY",
                "last_success_at": "2026-08-09T10:00:00+00:00",
                "freshness_sla_hours": 2,
                "parser_version": "v1",
            },
            {
                "source_id": "discovery",
                "source_tier": "D",
                "canonical_url": "https://example.org/page",
                "rights": {"retrieval_allowed": True},
                "authentication_mode": "NONE",
                "network_scope": "PUBLIC",
                "health": "FAILED",
                "last_success_at": "2026-08-09T19:00:00+00:00",
                "freshness_sla_hours": 24,
                "parser_version": "v1",
            },
            {
                "source_id": "blocked",
                "source_tier": "A",
                "canonical_url": "http://127.0.0.1/private",
                "rights": {"retrieval_allowed": True},
                "authentication_mode": "NONE",
                "network_scope": "LOOPBACK",
                "health": "HEALTHY",
                "last_success_at": None,
                "freshness_sla_hours": 1,
                "parser_version": "v1",
            },
        ]

    def test_official_stale_source_prioritized_for_fetch(self):
        result = build_frontier(gaps=self.gaps, sources=self.sources, now=self.now)
        first = result["items"][0]
        self.assertEqual(first["source_id"], "official")
        self.assertEqual(first["action"], "FETCH")
        self.assertIn("STALE", first["reasons"])

    def test_failed_discovery_source_retries_but_lower_priority(self):
        result = build_frontier(gaps=self.gaps, sources=self.sources, now=self.now)
        row = next(item for item in result["items"] if item["source_id"] == "discovery")
        self.assertEqual(row["action"], "RETRY")
        self.assertIn("SOURCE_FAILED", row["reasons"])
        self.assertLess(row["priority_score"], result["items"][0]["priority_score"])

    def test_private_network_target_routes_to_review(self):
        result = build_frontier(gaps=self.gaps, sources=self.sources, now=self.now)
        row = next(item for item in result["items"] if item["source_id"] == "blocked")
        self.assertEqual(row["action"], "REVIEW")
        self.assertIn("NON_PUBLIC_NETWORK_TARGET", row["reasons"])

    def test_deterministic_item_ids_and_accounting(self):
        a = build_frontier(gaps=self.gaps, sources=self.sources, now=self.now)
        b = build_frontier(gaps=self.gaps, sources=self.sources, now=self.now)
        self.assertEqual([x["frontier_item_id"] for x in a["items"]], [x["frontier_item_id"] for x in b["items"]])
        self.assertEqual(sum(a["action_accounting"].values()), a["frontier_item_count"])


if __name__ == "__main__":
    unittest.main()
