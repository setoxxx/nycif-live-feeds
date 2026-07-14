"""Tests for tiered resolver integration in sync_nyc_open_data."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import sync_nyc_open_data as sync
from scripts.nyc_location_resolver import ResolveResult


def test_classify_with_resolver_uses_resolver_when_no_match():
    index = sync.EnrichedIndex({}, {}, {})
    resolver = MagicMock()
    resolver._live_calls = 0
    resolver.resolve.return_value = ResolveResult(
        resolved=True,
        tier="tier_1_gazetteer_display",
        lat=40.758,
        lng=-73.985,
        source="test_gazetteer",
        confidence="high",
        confidence_reason="test",
    )

    row = {
        "event_id": "999999",
        "event_name": "Test Event",
        "event_borough": "Manhattan",
        "event_location": "Central Park",
        "start_date_time": "2026-08-01T10:00:00",
    }
    match_type, match = sync.classify_with_resolver(row, index, {}, resolver)
    assert match_type == "tier_1_gazetteer_display"
    assert match is not None
    assert sync.has_gps(match)


def test_classify_with_resolver_skips_resolver_when_gps_already_present():
    index = sync.EnrichedIndex(
        {"123": {"lat": 40.7, "lng": -74.0}},
        {},
        {},
    )
    resolver = MagicMock()
    row = {"event_id": "123", "event_name": "Known", "start_date_time": "2026-08-01T10:00:00"}
    match_type, match = sync.classify_with_resolver(row, index, {}, resolver)
    assert match_type == "event_id"
    resolver.resolve.assert_not_called()


def test_classify_with_resolver_returns_original_match_without_gps_when_unresolved():
    cached = {"display_location": "Mystery Place", "lat": None, "lng": None}
    index = sync.EnrichedIndex({}, {}, {})
    location_cache = {f"event_id:555": cached}
    resolver = MagicMock()
    resolver._live_calls = 0
    resolver.resolve.return_value = ResolveResult(
        resolved=False,
        tier="unresolved",
        lat=None,
        lng=None,
        source=None,
        confidence=None,
        confidence_reason=None,
    )
    row = {
        "event_id": "555",
        "event_name": "No GPS Event",
        "event_borough": "Queens",
        "event_location": "Unknown",
        "start_date_time": "2026-08-01T10:00:00",
    }
    match_type, match = sync.classify_with_resolver(row, index, location_cache, resolver)
    assert match_type == "location_cache"
    assert match == cached
