#!/usr/bin/env python3
"""Regression tests for the scheduled live-event intake refresh."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_daily_data_health import required_event_status  # noqa: E402
from scripts.live_event_intake_refresh import (  # noqa: E402
    coordinate_matches_borough,
    resolve_street_segment_by_intersections,
)
from scripts.nyc_location_resolver import ResolveResult, parse_street_between  # noqa: E402


BLOCK_PARTY_LOCATION = "EAST   74 STREET between AVENUE U and AVENUE T"


class RecordingResolver:
    def __init__(self, points: dict[str, tuple[float, float]] | None = None) -> None:
        self.queries: list[tuple[str, str | None]] = []
        self.points = points or {}

    def _resolve_geosearch(self, query: str, borough: str | None = None) -> ResolveResult | None:
        self.queries.append((query, borough))
        if query not in self.points:
            return None
        lat, lng = self.points[query]
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


def test_required_block_party_uses_certified_brooklyn_segment() -> None:
    parsed = parse_street_between(BLOCK_PARTY_LOCATION)
    assert parsed == ("EAST   74 STREET", "AVENUE U", "AVENUE T")

    resolver = RecordingResolver()
    result = resolve_street_segment_by_intersections(resolver, BLOCK_PARTY_LOCATION, "Brooklyn")
    assert result is not None and result.resolved
    assert result.lat == 40.618
    assert result.lng == -73.905
    assert result.label == BLOCK_PARTY_LOCATION
    assert result.tier == "tier_1_certified_segment"
    assert result.source == "nycif_certified_segment_midpoint"
    assert resolver.queries == []
    assert coordinate_matches_borough(result.lat, result.lng, "Brooklyn")
    assert not coordinate_matches_borough(40.772418, -73.963278, "Brooklyn")


def test_general_segment_uses_alternate_intersection_queries() -> None:
    display = "TEST STREET between FIRST AVENUE and SECOND AVENUE"
    resolver = RecordingResolver(
        {
            "TEST STREET & FIRST AVENUE": (40.6200, -73.9100),
            "TEST STREET & SECOND AVENUE": (40.6220, -73.9100),
        }
    )
    result = resolve_street_segment_by_intersections(resolver, display, "Brooklyn")
    assert result is not None and result.resolved
    assert result.tier == "tier_2_geosearch_midpoint"
    assert result.lat == 40.621
    assert result.lng == -73.91
    assert result.query_used == "TEST STREET & FIRST AVENUE / TEST STREET & SECOND AVENUE"
    assert resolver.queries[:2] == [
        ("TEST STREET and FIRST AVENUE", "Brooklyn"),
        ("TEST STREET & FIRST AVENUE", "Brooklyn"),
    ]


def test_cross_borough_geosearch_results_are_rejected() -> None:
    display = "TEST STREET between FIRST AVENUE and SECOND AVENUE"
    resolver = RecordingResolver(
        {
            query: (40.772418, -73.963278)
            for query in (
                "TEST STREET and FIRST AVENUE",
                "TEST STREET & FIRST AVENUE",
                "FIRST AVENUE and TEST STREET",
                "FIRST AVENUE & TEST STREET",
                "TEST STREET at FIRST AVENUE",
                "TEST STREET and SECOND AVENUE",
                "TEST STREET & SECOND AVENUE",
                "SECOND AVENUE and TEST STREET",
                "SECOND AVENUE & TEST STREET",
                "TEST STREET at SECOND AVENUE",
            )
        }
    )
    result = resolve_street_segment_by_intersections(resolver, display, "Brooklyn")
    assert result is None
    assert len(resolver.queries) == 10


def valid_required_event(*, lat: float = 40.618, lng: float = -73.905) -> dict:
    return {
        "id": "nyc_open_data:tvpp-9vvx:923896@2026-08-01",
        "title": "Block Party",
        "borough": "Brooklyn",
        "location": "EAST 74 STREET between AVENUE U and AVENUE T",
        "start_date_time": "2026-08-01T11:00:00-04:00",
        "end_date_time": "2026-08-01T20:00:00-04:00",
        "latitude": lat,
        "longitude": lng,
        "source": {
            "dataset": "tvpp-9vvx",
            "source_event_id": "923896",
        },
        "nycif": {
            "coordinate_status": "map_ready",
        },
    }


def write_page(root: pathlib.Path, name: str, events: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(json.dumps({"events": events}), encoding="utf-8")


def test_required_event_public_feed_gate() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        write_page(pages, "page-0001.json", [valid_required_event()])
        result = required_event_status(pages)
        assert result["qa_pass"] is True
        assert result["match_count"] == 1
        assert result["latitude"] == 40.618
        assert result["longitude"] == -73.905

    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        write_page(pages, "page-0001.json", [valid_required_event(lat=40.772418, lng=-73.963278)])
        result = required_event_status(pages)
        assert result["qa_pass"] is False
        assert any("latitude" in failure or "longitude" in failure for failure in result["failures"])

    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        event = valid_required_event()
        write_page(pages, "page-0001.json", [event])
        write_page(pages, "page-0002.json", [dict(event)])
        result = required_event_status(pages)
        assert result["qa_pass"] is False
        assert result["match_count"] == 2


def test_refresh_workflow_contract() -> None:
    workflow = (ROOT / ".github" / "workflows" / "discovery-feed-refresh.yml").read_text(encoding="utf-8")
    assert "python scripts/live_event_intake_refresh.py" in workflow
    assert "python scripts/build_daily_data_health.py" in workflow
    for path in (
        "data/raw_nyc_open_data_snapshot.json",
        "data/live_sync_report.json",
        "data/nycif_live_test_enriched_events.json",
        "data/test_enriched_feed_manifest.json",
        "data/nycif_staged_live_events.json",
        "data/staged_live_manifest.json",
        "data/nyc_geosearch_gazetteer_cache.json",
        "status/nycif-daily-data-health.json",
    ):
        assert path in workflow


if __name__ == "__main__":
    test_required_block_party_uses_certified_brooklyn_segment()
    test_general_segment_uses_alternate_intersection_queries()
    test_cross_borough_geosearch_results_are_rejected()
    test_required_event_public_feed_gate()
    test_refresh_workflow_contract()
    print("live event intake refresh regression tests passed")
