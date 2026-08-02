#!/usr/bin/env python3
"""Regression tests for the scheduled live-event intake refresh."""

from __future__ import annotations

import inspect
import json
import pathlib
import py_compile
import sys
import tempfile
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_daily_data_health import (  # noqa: E402
    REQUIRED_EVENT_CERTIFICATE,
    required_event_status,
)
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


def valid_event_certificate() -> dict:
    return {
        "approved_list_match_count": 1,
        "approved_manifest_total": 36364,
        "approved_page": "page-0008.json",
        "approved_page_match_count": 1,
        "artifact_type": "nycif_stage7_completion_certificate",
        "failures": [],
        "health_event_check": {
            "approved_pages_scanned": 49,
            "borough": "Brooklyn",
            "coordinate_status": "map_ready",
            "event_id": "tvpp-9vvx:923896@2026-08-01",
            "failures": [],
            "latitude": 40.618,
            "location": "EAST   74 STREET between AVENUE U and AVENUE T",
            "longitude": -73.905,
            "match_count": 1,
            "name": "Required Brooklyn block party 923896",
            "operating_rule": (
                "Event 923896 must appear exactly once in the approved public feed on 2026-08-01 "
                "with the East 74 Street / Avenue U / Avenue T Brooklyn segment pin."
            ),
            "page": "page-0008.json",
            "qa_pass": True,
            "required_date": "2026-08-01",
            "source_event_id": "923896",
            "start": "2026-08-01T11:00:00.000",
        },
        "health_schema_version": "1.4.0",
        "health_status": "READY",
        "list_check": {
            "borough": "Brooklyn",
            "coordinate_status": "map_ready",
            "event_id": "tvpp-9vvx:923896@2026-08-01",
            "failures": [],
            "latitude": 40.618,
            "location": "EAST   74 STREET between AVENUE U and AVENUE T",
            "longitude": -73.905,
            "start": "2026-08-01T11:00:00.000",
            "surface": "approved list",
        },
        "page_check": {
            "borough": "Brooklyn",
            "coordinate_status": "map_ready",
            "event_id": "tvpp-9vvx:923896@2026-08-01",
            "failures": [],
            "latitude": 40.618,
            "location": "EAST   74 STREET between AVENUE U and AVENUE T",
            "longitude": -73.905,
            "start": "2026-08-01T11:00:00.000",
            "surface": "approved page page-0008.json",
        },
        "qa_pass": True,
        "required_date": "2026-08-01",
        "schema_version": "1.0.0",
        "source_event_id": "923896",
        "strict_reconciliation": True,
    }


def write_certificate(path: pathlib.Path, certificate: dict) -> None:
    path.write_text(json.dumps(certificate), encoding="utf-8")


def archived_result(certificate: dict) -> dict:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        temporary = pathlib.Path(directory)
        pages = temporary / "pages"
        pages.mkdir()
        certificate_path = temporary / "event_923896_snapshot_recovery_certificate.json"
        write_certificate(certificate_path, certificate)
        return required_event_status(
            pages,
            current_date=date(2026, 8, 2),
            certificate_path=certificate_path,
        )


def test_required_event_public_feed_gate() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        write_page(pages, "page-0001.json", [valid_required_event()])
        result = required_event_status(pages, current_date=date(2026, 8, 1))
        assert result["qa_pass"] is True
        assert result["match_count"] == 1
        assert result["latitude"] == 40.618
        assert result["longitude"] == -73.905
        assert result["validation_mode"] == "live_occurrence"
        assert result["evaluated_date"] == "2026-08-01"

    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        write_page(pages, "page-0001.json", [valid_required_event(lat=40.772418, lng=-73.963278)])
        result = required_event_status(pages, current_date=date(2026, 8, 1))
        assert result["qa_pass"] is False
        assert any("latitude" in failure or "longitude" in failure for failure in result["failures"])

    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        event = valid_required_event()
        write_page(pages, "page-0001.json", [event])
        write_page(pages, "page-0002.json", [dict(event)])
        result = required_event_status(pages, current_date=date(2026, 8, 1))
        assert result["qa_pass"] is False
        assert result["match_count"] == 2


def test_required_event_aug1_missing_fails_live() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        write_page(pages, "page-0001.json", [])
        result = required_event_status(pages, current_date=date(2026, 8, 1))
        assert result["qa_pass"] is False
        assert result["match_count"] == 0
        assert result["validation_mode"] == "live_occurrence"


def test_required_event_aug1_real_approved_pages_pass() -> None:
    result = required_event_status(current_date=date(2026, 8, 1))
    assert result["validation_mode"] == "live_occurrence"
    assert result["qa_pass"] is True, result["failures"]
    assert result["match_count"] == 1
    page_name = str(result["page"] or "")
    assert page_name.startswith("page-") and page_name.endswith(".json")
    assert (
        ROOT / "data" / "schema-v1-discovery" / "approved" / "pages" / page_name
    ).is_file()
    assert result["evaluated_date"] == "2026-08-01"


def test_required_event_aug2_real_certificate_passes() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        pages = pathlib.Path(directory)
        result = required_event_status(
            pages,
            current_date=date(2026, 8, 2),
            certificate_path=REQUIRED_EVENT_CERTIFICATE,
        )
        assert result["qa_pass"] is True
        assert result["validation_mode"] == "archived_certification"
        assert result["certificate_schema_version"] == "1.0.0"
        assert result["approved_pages_scanned"] == 49
        assert result["match_count"] == 1
        assert result["evaluated_date"] == "2026-08-02"
        assert result["certificate_artifact"] == (
            "data/reports/event_923896_snapshot_recovery_certificate.json"
        )


def test_required_event_aug2_missing_and_malformed_fail() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        temporary = pathlib.Path(directory)
        pages = temporary / "pages"
        pages.mkdir()

        missing = temporary / "missing.json"
        result = required_event_status(
            pages,
            current_date=date(2026, 8, 2),
            certificate_path=missing,
        )
        assert result["qa_pass"] is False
        assert result["validation_mode"] == "archived_certification"
        assert "missing" in result["failures"][0].lower()

        malformed = temporary / "malformed.json"
        malformed.write_text("not json", encoding="utf-8")
        result = required_event_status(
            pages,
            current_date=date(2026, 8, 2),
            certificate_path=malformed,
        )
        assert result["qa_pass"] is False
        assert "malformed" in result["failures"][0].lower()


def test_required_event_aug2_top_level_contract_failures() -> None:
    certificate = valid_event_certificate()
    certificate["qa_pass"] = False
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("qa_pass" in failure for failure in result["failures"])

    for count_field in ("approved_page_match_count", "approved_list_match_count"):
        certificate = valid_event_certificate()
        certificate[count_field] = 0
        result = archived_result(certificate)
        assert result["qa_pass"] is False
        assert any(count_field in failure for failure in result["failures"])

    certificate = valid_event_certificate()
    certificate["strict_reconciliation"] = False
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("strict_reconciliation" in failure for failure in result["failures"])


def test_required_event_aug2_nested_health_failure() -> None:
    certificate = valid_event_certificate()
    certificate["health_event_check"]["match_count"] = 2
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("health_event_check.match_count" in failure for failure in result["failures"])

    certificate = valid_event_certificate()
    certificate["health_event_check"]["longitude"] = -73.9524
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("health_event_check.longitude" in failure for failure in result["failures"])


def test_required_event_aug2_page_and_list_checks_are_fail_closed() -> None:
    certificate = valid_event_certificate()
    certificate["page_check"]["event_id"] = "wrong-event"
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("page_check.event_id" in failure for failure in result["failures"])

    certificate = valid_event_certificate()
    certificate["list_check"]["longitude"] = -73.9524
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("list_check.longitude" in failure for failure in result["failures"])

    for missing_check in ("page_check", "list_check"):
        certificate = valid_event_certificate()
        del certificate[missing_check]
        result = archived_result(certificate)
        assert result["qa_pass"] is False
        assert any(missing_check in failure for failure in result["failures"])


def test_required_event_aug2_cross_surface_consistency() -> None:
    certificate = valid_event_certificate()
    certificate["health_event_check"]["page"] = "page-9999.json"
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any("does not match approved_page" in failure for failure in result["failures"])

    certificate = valid_event_certificate()
    certificate["list_check"]["start"] = "2026-08-01T12:00:00.000"
    result = archived_result(certificate)
    assert result["qa_pass"] is False
    assert any(
        "list_check.start does not match health_event_check" in failure
        for failure in result["failures"]
    )


def test_modified_python_files_compile() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT) as directory:
        output = pathlib.Path(directory)
        for source in (
            ROOT / "scripts" / "build_daily_data_health.py",
            ROOT / "scripts" / "test_live_event_intake_refresh.py",
        ):
            py_compile.compile(
                str(source),
                cfile=str(output / f"{source.stem}.pyc"),
                doraise=True,
            )


def test_required_event_signature_compatible() -> None:
    signature = inspect.signature(required_event_status)
    parameters = list(signature.parameters.values())
    assert parameters[0].default is not inspect.Parameter.empty
    for parameter in parameters[1:]:
        if parameter.kind == inspect.Parameter.KEYWORD_ONLY:
            assert parameter.default is not inspect.Parameter.empty


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
    test_required_event_aug1_missing_fails_live()
    test_required_event_aug1_real_approved_pages_pass()
    test_required_event_aug2_real_certificate_passes()
    test_required_event_aug2_missing_and_malformed_fail()
    test_required_event_aug2_top_level_contract_failures()
    test_required_event_aug2_nested_health_failure()
    test_required_event_aug2_page_and_list_checks_are_fail_closed()
    test_required_event_aug2_cross_surface_consistency()
    test_modified_python_files_compile()
    test_required_event_signature_compatible()
    test_refresh_workflow_contract()
    print("live event intake refresh regression tests passed")
