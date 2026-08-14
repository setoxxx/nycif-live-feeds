#!/usr/bin/env python3
"""Run current daily preflight regressions against the canonical resolver.

The August 1 live-occurrence behavior remains covered with deterministic fixtures.
After August 1, the real repository check uses the immutable Event 923896
certification artifact instead of current approved pages, which legitimately age
past occurrences out of the serving feed.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.test_live_event_intake_refresh as regression  # noqa: E402
from scripts.nyc_location_gazetteer import NYCLocationGazetteer  # noqa: E402
from scripts.nyc_location_resolver import NYCLocationResolver  # noqa: E402


BLOCK_PARTY_LOCATION = "EAST   74 STREET between AVENUE U and AVENUE T"


class FakeGeoclient:
    def __init__(self, hits: dict[tuple[str, str, str], tuple[float, float]] | None = None) -> None:
        self.hits = hits or {}
        self.calls: list[tuple[str, str, str]] = []

    def resolve_intersection(self, street1: str, street2: str, borough: str):
        key = (street1, street2, borough)
        self.calls.append(key)
        point = self.hits.get(key)
        if point is None:
            return None
        lat, lng = point
        return {
            "lat": lat,
            "lng": lng,
            "geocoder_source": "nyc_geoclient_intersection",
            "geoclient_label": f"{street1} & {street2}",
        }


class RecordingResolver(NYCLocationResolver):
    def __init__(self, geoclient_hits: dict[tuple[str, str, str], tuple[float, float]] | None = None) -> None:
        self.fake_geoclient = FakeGeoclient(geoclient_hits)
        super().__init__(
            NYCLocationGazetteer({}),
            {},
            allow_live_geosearch=False,
            geoclient=self.fake_geoclient,
        )


def test_canonical_required_block_party_segment() -> None:
    resolver = RecordingResolver()
    result = resolver.resolve(display_location=BLOCK_PARTY_LOCATION, borough="Brooklyn")
    assert result.resolved
    assert result.tier == "certified_street_segment"
    assert result.lat == 40.618
    assert result.lng == -73.905
    assert result.validation_state == "validated"
    assert result.exact_pin_eligible is True
    assert result.reason_code == "SEGMENT_CERTIFIED_REFERENCE"
    assert resolver.fake_geoclient.calls == []


def test_canonical_general_segment_midpoint() -> None:
    display = "TEST STREET between FIRST AVENUE and SECOND AVENUE"
    resolver = RecordingResolver(
        {
            ("TEST STREET", "FIRST AVENUE", "Brooklyn"): (40.6200, -73.9100),
            ("TEST STREET", "SECOND AVENUE", "Brooklyn"): (40.6220, -73.9100),
        }
    )
    result = resolver.resolve(display_location=display, borough="Brooklyn")
    assert result.resolved
    assert result.tier == "certified_street_segment"
    assert result.lat == 40.621
    assert result.lng == -73.91
    assert result.validation_state == "validated"
    assert result.exact_pin_eligible is True
    assert result.reason_code == "SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED"
    assert resolver.fake_geoclient.calls == [
        ("TEST STREET", "FIRST AVENUE", "Brooklyn"),
        ("TEST STREET", "SECOND AVENUE", "Brooklyn"),
    ]


def test_canonical_cross_borough_segment_abstains() -> None:
    display = "TEST STREET between FIRST AVENUE and SECOND AVENUE"
    resolver = RecordingResolver(
        {
            ("TEST STREET", "FIRST AVENUE", "Brooklyn"): (40.772418, -73.963278),
            ("TEST STREET", "SECOND AVENUE", "Brooklyn"): (40.772500, -73.963000),
        }
    )
    result = resolver.resolve(display_location=display, borough="Brooklyn")
    assert result.resolved is False
    assert result.reason_code == "SEGMENT_UNCERTIFIED"
    assert result.exact_pin_eligible is False


def main() -> int:
    tests = (
        test_canonical_required_block_party_segment,
        test_canonical_general_segment_midpoint,
        test_canonical_cross_borough_segment_abstains,
        regression.test_required_event_public_feed_gate,
        regression.test_required_event_aug1_missing_fails_live,
        regression.test_required_event_aug2_real_certificate_passes,
        regression.test_required_event_aug2_missing_and_malformed_fail,
        regression.test_required_event_aug2_top_level_contract_failures,
        regression.test_required_event_aug2_nested_health_failure,
        regression.test_required_event_aug2_page_and_list_checks_are_fail_closed,
        regression.test_required_event_aug2_cross_surface_consistency,
        regression.test_modified_python_files_compile,
        regression.test_required_event_signature_compatible,
    )
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("current live event intake refresh regression tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
