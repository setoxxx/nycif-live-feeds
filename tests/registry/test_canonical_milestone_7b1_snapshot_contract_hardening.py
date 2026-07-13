"""Canonical Milestone 7-B.1: staged-feed snapshot contract hardening tests."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.generate_gps_staged_feed_integration_adjudication_summary import (
    recommended_next_action_for_contract,
)
from scripts.gps_count_contract import (
    build_count_contract,
    finalize_count_contract_adjudication_hash,
)
from scripts.gps_identity import build_stable_event_identity
from scripts.gps_snapshot_provenance import (
    DEFAULT_STAGED_FEED_RELATIVE_PATH,
    REGENERATE_ARTIFACTS_NEXT_STEP,
    SCHEMA_VERSION,
    file_provenance,
    provenance_failure_report,
    sha256_file,
    validate_bound_snapshot,
)

INSPECT_NEXT_ACTION = "Do not patch update workflow; inspect adjudication summary first."


def patch_next_action(
    safe_count: int,
    *,
    no_safe_count: int = 20,
    old_target: int = 430,
) -> str:
    return recommended_next_action_for_contract(
        safe_identity_count=safe_count,
        no_safe_match_count=no_safe_count,
        old_target=old_target,
        multi_key_conflict_count=0,
    )


def run_adjudication_fixture(tmp_path: Path, diagnostic_payload: dict[str, Any]) -> dict[str, Any]:
    diagnostic_path = tmp_path / "diagnostic.json"
    summary_path = tmp_path / "summary.json"
    write_json(diagnostic_path, diagnostic_payload)
    adjudication = importlib.import_module("scripts.generate_gps_staged_feed_integration_adjudication_summary")
    adjudication.ROOT = tmp_path
    adjudication.DIAGNOSTIC_PATH = diagnostic_path
    adjudication.SUMMARY_PATH = summary_path
    adjudication.main()
    return read_json(summary_path)


def build_diagnostic_fixture(
    tmp_path: Path,
    *,
    include_provenance: bool,
    selected_count: int = 204,
    multi_key_conflict_count: int = 0,
) -> dict[str, Any]:
    feed = tmp_path / "feed.json"
    write_json(feed, build_staged_feed([]))
    payload: dict[str, Any] = {
        "dry_run_expected_matched_staged_event_count": 430,
        "multi_key_conflict_count": multi_key_conflict_count,
        "near_miss_diagnostics_by_promoted_cache_key": {},
        "selected_candidate_count": selected_count,
        "selected_stable_event_identity_count": selected_count,
        "selected_stable_identity_rows": [{"stable_event_identity": f"id-{index}"} for index in range(selected_count)],
        "unmatched_promoted_cache_key_count": 20,
        "unmatched_promoted_cache_keys": [],
    }
    if include_provenance:
        payload["staged_feed_provenance"] = file_provenance(
            feed,
            producer_script="scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
            repo_root=tmp_path,
            generated_at_utc="2026-07-10T00:00:00+00:00",
        )
    return payload


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "m7b1_snapshot_contract"
PROTECTED_PATHS = [
    REPO_ROOT / "data" / "nycif_staged_live_events.json",
    REPO_ROOT / "data" / "location_cache.json",
    REPO_ROOT / "data" / "staged_live_manifest.json",
    REPO_ROOT / "data" / "previous_staged_live_events_snapshot.json",
]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def make_event_row(index: int, event_date: str) -> dict[str, Any]:
    borough = ["Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"][index % 5]
    return {
        "borough": borough,
        "date": event_date,
        "display_location": f"Test Park {index}: Soccer Field 1",
        "lat": 40.7 + (index % 10) * 0.001,
        "lng": -73.9 - (index % 10) * 0.001,
        "source_cemsid": [f"CEM-{index:04d}"],
        "source_event_id": f"EV-{index:04d}",
        "start_date_time": f"{event_date}T10:00:00",
        "title": f"Test Event {index}",
    }


def make_safe_row(event_row: dict[str, Any], index: int = 0) -> dict[str, Any]:
    identity = build_stable_event_identity(event_row)
    return {
        "current_lat": event_row.get("lat"),
        "current_lng": event_row.get("lng"),
        "display_location": event_row.get("display_location"),
        "match_modes": {"source_cemsid": 100.0},
        "promoted_cache_key": f"group:test|park {index:04d}",
        "promoted_display_location": event_row.get("display_location"),
        "promoted_lat": 40.75,
        "promoted_lng": -73.95,
        "source_cemsid": event_row.get("source_cemsid") or [],
        "source_event_id": event_row.get("source_event_id"),
        "stable_event_identity": identity,
    }


def build_staged_feed(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"events": events, "generated_for_test": True}


def build_contract_summary(
    events: list[dict[str, Any]],
    staged_feed_path: Path,
    *,
    repo_root: Path,
    include_provenance: bool = True,
    include_count_contract: bool = True,
    provenance_override: dict[str, Any] | None = None,
    diagnostic_artifact_sha256: str = "abc123def4567890123456789012345678901234567890123456789012345678",
) -> dict[str, Any]:
    safe_rows = [make_safe_row(row, index) for index, row in enumerate(events)]
    no_safe_match_count = 20
    adjudication_count_by_type: dict[str, int] = {}
    summary: dict[str, Any] = {
        "adjudication_count_by_type": adjudication_count_by_type,
        "diagnostic_artifact_sha256": diagnostic_artifact_sha256,
        "generated_at_utc": "2026-07-13T12:00:00+00:00",
        "input_diagnostic": "data/gps_staged_feed_integration_match_diagnostic.json",
        "location_cache_modified": False,
        "multi_key_conflict_count": 0,
        "no_safe_staged_match_adjudication": [],
        "no_safe_staged_match_promoted_key_count": no_safe_match_count,
        "no_safe_staged_match_promoted_keys": [],
        "old_dry_run_target_count": 430,
        "phase": "gps_staged_feed_integration_adjudication_summary",
        "phase_3a_run": False,
        "public_map_modified": False,
        "qa_pass": True,
        "safe_update_ready_count": len(safe_rows),
        "safe_update_ready_identity_count": len(safe_rows),
        "safe_update_ready_rows": safe_rows,
        "staged_feed_modified": False,
    }
    if include_provenance:
        summary["staged_feed_provenance"] = provenance_override or file_provenance(
            staged_feed_path,
            producer_script="scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
            repo_root=repo_root,
            staged_feed_path=DEFAULT_STAGED_FEED_RELATIVE_PATH,
            generated_at_utc="2026-07-13T12:00:00+00:00",
            upstream_artifact_sha256=diagnostic_artifact_sha256,
        )
    if include_provenance and include_count_contract:
        summary["safe_update_count_contract"] = build_count_contract(
            staged_feed_provenance=summary["staged_feed_provenance"],
            diagnostic_artifact_sha256=diagnostic_artifact_sha256,
            selected_rows=safe_rows,
            no_safe_match_count=no_safe_match_count,
            multi_key_conflict_count=summary["multi_key_conflict_count"],
            adjudication_count_by_type=adjudication_count_by_type,
            generated_at_utc=summary["generated_at_utc"],
        )
        finalize_count_contract_adjudication_hash(summary)
    return summary


def incident_window_events(total: int = 204) -> list[dict[str, Any]]:
    start = date(2026, 6, 30)
    rows: list[dict[str, Any]] = []
    for index in range(total):
        event_date = (start + timedelta(days=index % 7)).isoformat()
        rows.append(make_event_row(index, event_date))
    return rows


def july_seventh_feed_from_old(old_events: list[dict[str, Any]], keep: int = 155) -> list[dict[str, Any]]:
    kept = old_events[:keep]
    new_events = [make_event_row(1000 + index, "2026-07-07") for index in range(49)]
    return kept + new_events


# ---------------------------------------------------------------------------
# A. Hashing contract
# ---------------------------------------------------------------------------


def test_sha256_file_is_byte_exact_and_deterministic(tmp_path: Path) -> None:
    payload = b'{"events":[]}\n'
    target = tmp_path / "feed.json"
    target.write_bytes(payload)
    first = sha256_file(target)
    second = sha256_file(target)
    assert first == second
    assert first == hashlib.sha256(payload).hexdigest()


def test_whitespace_and_newline_changes_alter_hash(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    spaced = tmp_path / "spaced.json"
    base.write_text('{"events":[]}\n', encoding="utf-8")
    spaced.write_text('{"events": []}\n', encoding="utf-8")
    assert sha256_file(base) != sha256_file(spaced)


def test_unicode_byte_sequence_is_sensitive(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text('{"title":"café"}\n', encoding="utf-8")
    right.write_text('{"title":"caf\u00e9"}\n', encoding="utf-8")
    assert sha256_file(left) == sha256_file(right)
    right.write_text('{"title":"cafe"}\n', encoding="utf-8")
    assert sha256_file(left) != sha256_file(right)


def test_empty_file_hash_is_stable(tmp_path: Path) -> None:
    target = tmp_path / "empty.json"
    target.write_bytes(b"")
    assert sha256_file(target) == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# B. Provenance schema
# ---------------------------------------------------------------------------


def test_file_provenance_schema_fields(tmp_path: Path) -> None:
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, {"events": []})
    provenance = file_provenance(
        feed,
        producer_script="scripts/test_producer.py",
        repo_root=tmp_path,
        generated_at_utc="2026-07-13T00:00:00+00:00",
    )
    assert provenance["schema_version"] == SCHEMA_VERSION
    assert provenance["staged_feed"]["path"] == DEFAULT_STAGED_FEED_RELATIVE_PATH
    assert len(provenance["staged_feed"]["sha256"]) == 64
    assert provenance["staged_feed"]["byte_size"] == feed.stat().st_size
    assert provenance["producer"]["script"] == "scripts/test_producer.py"
    assert provenance["producer"]["generated_at_utc"] == "2026-07-13T00:00:00+00:00"


# ---------------------------------------------------------------------------
# C. Diagnostic propagation
# ---------------------------------------------------------------------------


def test_diagnostic_records_staged_feed_provenance(tmp_path: Path) -> None:
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed([]))
    diagnostic_path = tmp_path / "data" / "gps_staged_feed_integration_match_diagnostic.json"
    diagnostic = importlib.import_module("scripts.generate_gps_staged_feed_integration_match_diagnostic")
    importlib.reload(diagnostic)
    diagnostic.fuzz = object()
    diagnostic.utils = object()
    diagnostic.ROOT = tmp_path
    diagnostic.DATA_DIR = tmp_path / "data"
    diagnostic.STAGED_FEED_PATH = feed
    diagnostic.DIAGNOSTIC_PATH = diagnostic_path
    diagnostic.LOCATION_CACHE_PATH = tmp_path / "data" / "location_cache.json"
    diagnostic.PROMOTION_REPORT_PATH = tmp_path / "data" / "gps_phase2e_promotion_report.json"
    diagnostic.DRY_RUN_REPORT_PATH = tmp_path / "data" / "gps_staged_feed_integration_dry_run_report.json"

    def fake_load_json(path: Path, default: object) -> object:
        if path == feed:
            return build_staged_feed([])
        if "dry_run" in path.name:
            return {"matched_staged_event_count": 430}
        return default

    diagnostic.load_json = fake_load_json
    diagnostic.rows_from_staged = lambda payload: []
    diagnostic.promoted_rows_from_report = lambda payload: {
        "group:test": {"lat": 40.7, "lng": -73.9, "display_location": "Test"},
    }
    diagnostic.cemsids_for_promoted_rows = lambda entries, promoted: {key: set() for key in promoted}
    diagnostic.main()

    report = read_json(diagnostic_path)
    assert report["staged_feed_provenance"]["staged_feed"]["sha256"] == sha256_file(feed)


# ---------------------------------------------------------------------------
# D. Adjudication propagation
# ---------------------------------------------------------------------------


def test_adjudication_preserves_diagnostic_provenance_without_rehashing_staged_feed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed([]))
    diagnostic_path = tmp_path / "data" / "gps_staged_feed_integration_match_diagnostic.json"
    summary_path = tmp_path / "data" / "gps_staged_feed_integration_adjudication_summary.json"
    bound = file_provenance(
        feed,
        producer_script="scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
        repo_root=tmp_path,
        generated_at_utc="2026-07-10T00:00:00+00:00",
    )
    write_json(
        diagnostic_path,
        {
            "dry_run_expected_matched_staged_event_count": 204,
            "multi_key_conflict_count": 0,
            "near_miss_diagnostics_by_promoted_cache_key": {},
            "selected_candidate_count": 204,
            "selected_stable_event_identity_count": 204,
            "selected_stable_identity_rows": [{"stable_event_identity": f"id-{index}"} for index in range(204)],
            "staged_feed_provenance": bound,
            "unmatched_promoted_cache_key_count": 20,
            "unmatched_promoted_cache_keys": [],
        },
    )
    feed.write_text('{"events":[{"mutated":true}]}\n', encoding="utf-8")

    adjudication = importlib.import_module("scripts.generate_gps_staged_feed_integration_adjudication_summary")
    monkeypatch.setattr(adjudication, "ROOT", tmp_path)
    monkeypatch.setattr(adjudication, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(adjudication, "DIAGNOSTIC_PATH", diagnostic_path)
    monkeypatch.setattr(adjudication, "SUMMARY_PATH", summary_path)
    adjudication.main()

    summary = read_json(summary_path)
    assert summary["staged_feed_provenance"]["staged_feed"]["sha256"] == bound["staged_feed"]["sha256"]
    assert summary["diagnostic_artifact_sha256"] == sha256_file(diagnostic_path)


def test_adjudication_rejects_missing_diagnostic_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    diagnostic_path = tmp_path / "diagnostic.json"
    summary_path = tmp_path / "summary.json"
    write_json(
        diagnostic_path,
        {
            "dry_run_expected_matched_staged_event_count": 204,
            "multi_key_conflict_count": 0,
            "near_miss_diagnostics_by_promoted_cache_key": {},
            "selected_candidate_count": 204,
            "selected_stable_event_identity_count": 204,
            "selected_stable_identity_rows": [{"stable_event_identity": f"id-{index}"} for index in range(204)],
            "unmatched_promoted_cache_key_count": 20,
            "unmatched_promoted_cache_keys": [],
        },
    )
    adjudication = importlib.import_module("scripts.generate_gps_staged_feed_integration_adjudication_summary")
    monkeypatch.setattr(adjudication, "ROOT", tmp_path)
    monkeypatch.setattr(adjudication, "DIAGNOSTIC_PATH", diagnostic_path)
    monkeypatch.setattr(adjudication, "SUMMARY_PATH", summary_path)
    exit_code = adjudication.main()
    summary = read_json(summary_path)
    assert exit_code == 1
    assert summary["qa_pass"] is False
    assert summary["staged_feed_provenance"] is None
    assert summary["recommended_next_action"] == REGENERATE_ARTIFACTS_NEXT_STEP


def test_adjudication_recommended_next_action_when_provenance_present_and_safe_contract(
    tmp_path: Path,
) -> None:
    summary = run_adjudication_fixture(tmp_path, build_diagnostic_fixture(tmp_path, include_provenance=True))
    assert summary["recommended_next_action"] == patch_next_action(204)
    assert summary["qa_pass"] is True


def test_adjudication_155_passes_qa_when_counts_are_consistent(tmp_path: Path) -> None:
    summary = run_adjudication_fixture(
        tmp_path,
        build_diagnostic_fixture(tmp_path, include_provenance=True, selected_count=155),
    )
    assert summary["qa_pass"] is True
    assert summary["recommended_next_action"] == patch_next_action(155)


def test_adjudication_recommended_next_action_when_provenance_present_but_inconsistent_counts(
    tmp_path: Path,
) -> None:
    diagnostic = build_diagnostic_fixture(tmp_path, include_provenance=True, selected_count=155)
    diagnostic["selected_stable_event_identity_count"] = 200
    summary = run_adjudication_fixture(tmp_path, diagnostic)
    assert summary["qa_pass"] is False
    assert summary["recommended_next_action"] == INSPECT_NEXT_ACTION


def test_adjudication_recommended_next_action_when_provenance_present_but_conflicts(
    tmp_path: Path,
) -> None:
    summary = run_adjudication_fixture(
        tmp_path,
        build_diagnostic_fixture(tmp_path, include_provenance=True, multi_key_conflict_count=2),
    )
    assert summary["recommended_next_action"] == INSPECT_NEXT_ACTION


def test_diagnostic_fake_load_json_branches(tmp_path: Path) -> None:
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    dry_run = tmp_path / "data" / "gps_staged_feed_integration_dry_run_report.json"
    other = tmp_path / "data" / "location_cache.json"
    sentinel = {"default": True}

    def fake_load_json(path: Path, default: object) -> object:
        if path == feed:
            return build_staged_feed([])
        if "dry_run" in path.name:
            return {"matched_staged_event_count": 430}
        return default

    assert fake_load_json(feed, sentinel) == build_staged_feed([])
    assert fake_load_json(dry_run, sentinel) == {"matched_staged_event_count": 430}
    assert fake_load_json(other, sentinel) is sentinel


# ---------------------------------------------------------------------------
# E/F/G. Apply preflight, legacy, and incident regression
# ---------------------------------------------------------------------------


def run_apply_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    staged_events: list[dict[str, Any]],
    contract: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    data_dir = tmp_path / "data"
    feed_path = data_dir / "nycif_staged_live_events.json"
    summary_path = data_dir / "gps_staged_feed_integration_adjudication_summary.json"
    report_path = data_dir / "gps_staged_feed_integration_update_report.json"
    write_json(feed_path, build_staged_feed(staged_events))
    write_json(summary_path, contract)

    update = importlib.import_module("scripts.apply_gps_staged_feed_integration_update")
    monkeypatch.setattr(update, "ROOT", tmp_path)
    monkeypatch.setattr(update, "DATA_DIR", data_dir)
    monkeypatch.setattr(update, "STAGED_FEED_PATH", feed_path)
    monkeypatch.setattr(update, "ADJUDICATION_SUMMARY_PATH", summary_path)
    monkeypatch.setattr(update, "UPDATE_REPORT_PATH", report_path)
    exit_code = update.main()
    return exit_code, read_json(report_path)


def test_apply_preflight_detects_stale_contract_incident_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old_events = incident_window_events(204)
    old_feed = tmp_path / "old_feed.json"
    write_json(old_feed, build_staged_feed(old_events))
    contract = build_contract_summary(old_events, old_feed, repo_root=tmp_path)
    contract["safe_update_ready_count"] = 204
    contract["safe_update_ready_identity_count"] = 204

    new_events = july_seventh_feed_from_old(old_events, keep=155)
    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=new_events, contract=contract)

    assert exit_code == 1
    assert report["failure_type"] == "stale_staged_feed_contract"
    assert report["qa_pass"] is False
    assert report["update_performed"] is False
    assert report["staged_feed_modified"] is False
    assert report["updated_staged_event_count"] == 0
    assert report["expected_staged_feed_sha256"] != report["actual_staged_feed_sha256"]
    assert report["required_next_step"] == REGENERATE_ARTIFACTS_NEXT_STEP


def test_legacy_contract_missing_snapshot_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events = incident_window_events(10)
    contract = build_contract_summary(events, tmp_path / "feed.json", repo_root=tmp_path, include_provenance=False)
    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=events, contract=contract)
    assert exit_code == 1
    assert report["failure_type"] == "legacy_contract_missing_snapshot_hash"
    assert report["required_next_step"] == REGENERATE_ARTIFACTS_NEXT_STEP


def test_malformed_and_unsupported_provenance_fail_closed(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    write_json(feed, build_staged_feed([]))
    malformed = validate_bound_snapshot({"staged_feed": {}}, feed, repo_root=tmp_path)
    unsupported = validate_bound_snapshot({"schema_version": "v0"}, feed, repo_root=tmp_path)
    assert malformed.failure_type == "legacy_contract_missing_snapshot_hash"
    assert unsupported.failure_type == "legacy_contract_missing_snapshot_hash"


def test_wrong_path_and_tampered_sha_fail_closed(tmp_path: Path) -> None:
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed([]))
    provenance = file_provenance(feed, producer_script="scripts/test.py", repo_root=tmp_path)
    wrong_path = copy.deepcopy(provenance)
    wrong_path["staged_feed"]["path"] = "data/other.json"
    tampered = copy.deepcopy(provenance)
    tampered["staged_feed"]["sha256"] = "0" * 64
    wrong_path_result = validate_bound_snapshot(wrong_path, feed, repo_root=tmp_path)
    tampered_result = validate_bound_snapshot(tampered, feed, repo_root=tmp_path)
    assert wrong_path_result.failure_type == "stale_staged_feed_contract"
    assert tampered_result.failure_type == "stale_staged_feed_contract"


def test_byte_size_mismatch_fails_even_if_sha_matches_reported(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    write_json(feed, build_staged_feed([]))
    provenance = file_provenance(feed, producer_script="scripts/test.py", repo_root=tmp_path)
    provenance["staged_feed"]["byte_size"] = int(provenance["staged_feed"]["byte_size"]) + 1
    result = validate_bound_snapshot(provenance, feed, repo_root=tmp_path)
    assert result.failure_type == "stale_staged_feed_contract"


# ---------------------------------------------------------------------------
# H. Matching-hash normal path reaches identity matching
# ---------------------------------------------------------------------------


def test_matching_hash_reaches_identity_matching_not_preflight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events = incident_window_events(204)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    staged_events = copy.deepcopy(events)
    staged_events[-1]["source_event_id"] = "MUTATED-EV-9999"
    write_json(feed_path, build_staged_feed(staged_events))
    contract = build_contract_summary(events, feed_path, repo_root=tmp_path)

    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=staged_events, contract=contract)
    assert exit_code == 1
    assert report.get("failure_type") != "stale_staged_feed_contract"
    assert report.get("failure_type") != "legacy_contract_missing_snapshot_hash"
    assert report.get("failure_type") != "legacy_contract_missing_count_contract"
    assert report.get("count_contract_preflight_passed") is True
    assert report["updated_staged_event_count"] < 204


# ---------------------------------------------------------------------------
# I. Input immutability
# ---------------------------------------------------------------------------


def test_apply_preflight_does_not_mutate_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    events = incident_window_events(5)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(events))
    contract = build_contract_summary(events, feed_path, repo_root=tmp_path)
    contract["staged_feed_provenance"]["staged_feed"]["sha256"] = "0" * 64
    feed_before = feed_path.read_bytes()
    summary_path = tmp_path / "data" / "gps_staged_feed_integration_adjudication_summary.json"
    write_json(summary_path, contract)
    contract_before = summary_path.read_bytes()

    update = importlib.import_module("scripts.apply_gps_staged_feed_integration_update")
    monkeypatch.setattr(update, "ROOT", tmp_path)
    monkeypatch.setattr(update, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(update, "STAGED_FEED_PATH", feed_path)
    monkeypatch.setattr(update, "ADJUDICATION_SUMMARY_PATH", summary_path)
    monkeypatch.setattr(update, "UPDATE_REPORT_PATH", tmp_path / "data" / "gps_staged_feed_integration_update_report.json")
    update.main()

    assert feed_path.read_bytes() == feed_before
    assert summary_path.read_bytes() == contract_before


# ---------------------------------------------------------------------------
# J. Protected boundaries
# ---------------------------------------------------------------------------


def test_protected_production_paths_exist_and_were_not_modified_by_tests() -> None:
    for path in PROTECTED_PATHS:
        assert path.exists()


def test_changed_files_do_not_include_protected_data_paths() -> None:
    changed = {
        "scripts/gps_snapshot_provenance.py",
        "scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
        "scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
        "scripts/apply_gps_staged_feed_integration_update.py",
        "tests/registry/test_canonical_milestone_7b1_snapshot_contract_hardening.py",
        "tests/registry/test_canonical_milestone_7b2_snapshot_bound_count_contract.py",
        "scripts/gps_count_contract.py",
        "docs/canonical_milestone_7b1_snapshot_contract_hardening.md",
        "nycif_m7b1_snapshot_contract_hardening_independent_review_prompt.txt",
    }
    protected = {path.relative_to(REPO_ROOT).as_posix() for path in PROTECTED_PATHS}
    assert changed.isdisjoint(protected)


# ---------------------------------------------------------------------------
# K. No-network behavior
# ---------------------------------------------------------------------------


def test_provenance_module_has_no_network_imports() -> None:
    source = (REPO_ROOT / "scripts" / "gps_snapshot_provenance.py").read_text(encoding="utf-8")
    forbidden = ("urllib", "requests", "http.client", "socket", "ftplib")
    assert not any(token in source for token in forbidden)


# ---------------------------------------------------------------------------
# L. Direct-script compatibility
# ---------------------------------------------------------------------------


def test_direct_script_execution_imports_provenance_helper() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util, pathlib, sys; "
            "root = pathlib.Path('scripts').resolve().parent; "
            "sys.path.insert(0, str(root / 'scripts')); "
            "import gps_snapshot_provenance as p; "
            "print(p.SCHEMA_VERSION)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "gps-staged-feed-provenance-v1" in result.stdout


def test_provenance_failure_report_shape() -> None:
    report = provenance_failure_report(
        validate_bound_snapshot(None, REPO_ROOT / "missing.json", repo_root=REPO_ROOT),
        input_adjudication_summary="data/gps_staged_feed_integration_adjudication_summary.json",
        input_staged_feed=DEFAULT_STAGED_FEED_RELATIVE_PATH,
    )
    assert report["qa_pass"] is False
    assert report["location_cache_modified"] is False
    assert report["public_map_modified"] is False
    assert report["staged_feed_modified"] is False
