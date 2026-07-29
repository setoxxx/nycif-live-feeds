#!/usr/bin/env python3
"""Regression tests for the scheduled live-event intake refresh."""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.live_event_intake_refresh import (  # noqa: E402
    resolve_street_segment_by_intersections,
)
from scripts.nyc_location_resolver import ResolveResult, parse_street_between  # noqa: E402


BLOCK_PARTY_LOCATION = "EAST   74 STREET between AVENUE U and AVENUE T"


class FakeResolver:
    def __init__(self) -> None:
        self.queries: list[tuple[str, str | None]] = []

    def _resolve_geosearch(self, query: str, borough: str | None = None) -> ResolveResult | None:
        self.queries.append((query, borough))
        points = {
            "EAST   74 STREET and AVENUE U": (40.6200, -73.9050),
            "EAST   74 STREET and AVENUE T": (40.6160, -73.9050),
        }
        if query not in points:
            return None
        lat, lng = points[query]
        return ResolveResult(
            resolved=True,
            tier="test",
            lat=lat,
            lng=lng,
            source="test",
            confidence="high",
            confidence_reason="fixture",
            label=query,
            query_used=query,
        )


def test_block_party_segment() -> None:
    parsed = parse_street_between(BLOCK_PARTY_LOCATION)
    assert parsed == ("EAST   74 STREET", "AVENUE U", "AVENUE T")

    resolver = FakeResolver()
    result = resolve_street_segment_by_intersections(resolver, BLOCK_PARTY_LOCATION, "Brooklyn")
    assert result is not None and result.resolved
    assert result.lat == 40.618
    assert result.lng == -73.905
    assert result.label == BLOCK_PARTY_LOCATION
    assert resolver.queries == [
        ("EAST   74 STREET and AVENUE U", "Brooklyn"),
        ("EAST   74 STREET and AVENUE T", "Brooklyn"),
    ]
    assert all("Brooklyn" not in query for query, _borough in resolver.queries)


def test_refresh_workflow_contract() -> None:
    workflow = (ROOT / ".github" / "workflows" / "discovery-feed-refresh.yml").read_text(encoding="utf-8")
    assert "python scripts/live_event_intake_refresh.py" in workflow
    for path in (
        "data/raw_nyc_open_data_snapshot.json",
        "data/live_sync_report.json",
        "data/nycif_live_test_enriched_events.json",
        "data/test_enriched_feed_manifest.json",
        "data/nycif_staged_live_events.json",
        "data/staged_live_manifest.json",
        "data/nyc_geosearch_gazetteer_cache.json",
    ):
        assert path in workflow


if __name__ == "__main__":
    test_block_party_segment()
    test_refresh_workflow_contract()
    print("live event intake refresh regression tests passed")
