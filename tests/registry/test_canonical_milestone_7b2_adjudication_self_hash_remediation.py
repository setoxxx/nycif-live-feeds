"""Canonical Milestone 7-B.2 adjudication self-hash remediation tests."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pytest

from scripts.gps_count_contract import (
    ADJUDICATION_ARTIFACT_HASH_SCHEMA,
    adjudication_artifact_hash_payload,
    build_count_contract,
    canonical_json_bytes,
    canonicalize_adjudication_summary,
    compute_adjudication_artifact_sha256,
    finalize_count_contract_adjudication_hash,
    validate_adjudication_artifact_sha256,
    validate_count_contract_for_apply,
)
from scripts.gps_snapshot_provenance import sha256_file
from tests.registry.test_canonical_milestone_7b1_snapshot_contract_hardening import (
    build_contract_summary,
    build_staged_feed,
    incident_window_events,
    make_safe_row,
    read_json,
    run_apply_isolated,
    write_json,
)


def finalize_complete_summary(summary: dict[str, Any]) -> None:
    canonical = canonicalize_adjudication_summary(summary)
    summary.clear()
    summary.update(canonical)
    finalize_count_contract_adjudication_hash(summary)
    assert validate_count_contract_for_apply(summary).ok


def test_old_finalization_order_fails_after_post_fields_added(tmp_path: Path) -> None:
    events = incident_window_events(5)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path, include_count_contract=False)
    contract = build_count_contract(
        staged_feed_provenance=summary["staged_feed_provenance"],
        diagnostic_artifact_sha256=summary["diagnostic_artifact_sha256"],
        selected_rows=summary["safe_update_ready_rows"],
        no_safe_match_count=summary["no_safe_staged_match_promoted_key_count"],
        multi_key_conflict_count=0,
        adjudication_count_by_type={},
        generated_at_utc=summary["generated_at_utc"],
    )
    summary["safe_update_count_contract"] = contract
    finalize_count_contract_adjudication_hash(summary)
    summary["validated_conditions"] = {"qa_pass_true": True}
    summary["recommended_next_action"] = "changed after hash"
    result = validate_adjudication_artifact_sha256(summary)
    assert result.ok is False
    assert result.failure_type == "adjudication_artifact_hash_mismatch"


def test_complete_summary_finalization_passes(tmp_path: Path) -> None:
    events = incident_window_events(5)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    assert validate_adjudication_artifact_sha256(summary).ok


def test_compute_does_not_mutate_input(tmp_path: Path) -> None:
    events = incident_window_events(3)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    before = copy.deepcopy(summary)
    compute_adjudication_artifact_sha256(summary)
    assert summary == before


def test_canonical_hash_is_deterministic(tmp_path: Path) -> None:
    events = incident_window_events(3)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    first = compute_adjudication_artifact_sha256(summary)
    second = compute_adjudication_artifact_sha256(summary)
    assert first == second
    assert first == summary["safe_update_count_contract"]["adjudication_artifact_sha256"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("qa_pass", False),
        ("recommended_next_action", "tampered"),
        ("blocking_issues", ["tampered"]),
    ],
)
def test_tampering_covered_fields_invalidates_hash(
    tmp_path: Path, field: str, value: Any
) -> None:
    events = incident_window_events(3)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    summary[field] = value
    result = validate_adjudication_artifact_sha256(summary)
    assert result.ok is False
    assert result.failure_type == "adjudication_artifact_hash_mismatch"


def test_changing_only_stored_hash_fails_comparison(tmp_path: Path) -> None:
    events = incident_window_events(3)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    summary["safe_update_count_contract"]["adjudication_artifact_sha256"] = "a" * 64
    result = validate_adjudication_artifact_sha256(summary)
    assert result.failure_type == "adjudication_artifact_hash_mismatch"


def test_excluded_hash_field_normalized_to_null_for_payload(tmp_path: Path) -> None:
    events = incident_window_events(2)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    payload = adjudication_artifact_hash_payload(summary)
    assert payload["safe_update_count_contract"]["adjudication_artifact_sha256"] is None


def test_canonical_json_matches_save_json_format(tmp_path: Path) -> None:
    events = incident_window_events(2)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    target = tmp_path / "saved.json"
    write_json(target, adjudication_artifact_hash_payload(summary))
    assert sha256_file(target) == hashlib.sha256(canonical_json_bytes(adjudication_artifact_hash_payload(summary))).hexdigest()


def test_unicode_and_reordered_dict_hash_stable(tmp_path: Path) -> None:
    events = incident_window_events(2)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    summary["recommended_next_action"] = "café résumé"
    ordered = OrderedDict(sorted(summary.items(), reverse=True))
    summary_from_ordered = dict(ordered)
    finalize_complete_summary(summary)
    finalize_count_contract_adjudication_hash(summary_from_ordered)
    assert compute_adjudication_artifact_sha256(summary) == compute_adjudication_artifact_sha256(summary_from_ordered)


def test_missing_hash_schema_fails() -> None:
    summary = {"safe_update_count_contract": {"adjudication_artifact_sha256": "a" * 64, "derivation": {}}}
    result = validate_adjudication_artifact_sha256(summary)
    assert result.failure_type == "missing_adjudication_artifact_hash"


def test_unsupported_hash_schema_fails(tmp_path: Path) -> None:
    events = incident_window_events(2)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    summary["safe_update_count_contract"]["derivation"]["adjudication_artifact_hash_schema"] = "v0"
    result = validate_adjudication_artifact_sha256(summary)
    assert result.failure_type == "unsupported_adjudication_artifact_hash_schema"


def test_uppercase_digest_rejected(tmp_path: Path) -> None:
    events = incident_window_events(2)
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed, build_staged_feed(events))
    summary = build_contract_summary(events, feed, repo_root=tmp_path)
    finalize_complete_summary(summary)
    digest = summary["safe_update_count_contract"]["adjudication_artifact_sha256"]
    summary["safe_update_count_contract"]["adjudication_artifact_sha256"] = digest.upper()
    result = validate_adjudication_artifact_sha256(summary)
    assert result.failure_type == "malformed_adjudication_artifact_hash"


def test_producer_save_reload_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    feed = tmp_path / "data" / "nycif_staged_live_events.json"
    events = incident_window_events(155)
    write_json(feed, build_staged_feed(events))
    diagnostic_path = tmp_path / "data" / "gps_staged_feed_integration_match_diagnostic.json"
    summary_path = tmp_path / "data" / "gps_staged_feed_integration_adjudication_summary.json"
    from scripts.gps_snapshot_provenance import file_provenance

    write_json(
        diagnostic_path,
        {
            "dry_run_expected_matched_staged_event_count": 430,
            "multi_key_conflict_count": 0,
            "near_miss_diagnostics_by_promoted_cache_key": {},
            "selected_candidate_count": 155,
            "selected_stable_event_identity_count": 155,
            "selected_stable_identity_rows": [
                make_safe_row(row, index) for index, row in enumerate(events)
            ],
            "staged_feed_provenance": file_provenance(
                feed,
                producer_script="scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
                repo_root=tmp_path,
            ),
            "unmatched_promoted_cache_key_count": 20,
            "unmatched_promoted_cache_keys": [],
        },
    )
    adjudication = importlib.import_module("scripts.generate_gps_staged_feed_integration_adjudication_summary")
    monkeypatch.setattr(adjudication, "ROOT", tmp_path)
    monkeypatch.setattr(adjudication, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(adjudication, "DIAGNOSTIC_PATH", diagnostic_path)
    monkeypatch.setattr(adjudication, "SUMMARY_PATH", summary_path)
    assert adjudication.main() == 0
    reloaded = read_json(summary_path)
    assert validate_count_contract_for_apply(reloaded).ok
    assert reloaded["safe_update_count_contract"]["derivation"]["adjudication_artifact_hash_schema"] == ADJUDICATION_ARTIFACT_HASH_SCHEMA


def test_apply_preflight_passes_with_producer_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = incident_window_events(155)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(events))
    summary = build_contract_summary(events, feed_path, repo_root=tmp_path)
    finalize_complete_summary(summary)
    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=events, contract=summary)
    assert report.get("count_contract_preflight_passed") is True
    assert report.get("adjudication_artifact_hash_preflight_passed") is True
    assert report.get("snapshot_contract_preflight_passed") is True
    assert report.get("failure_type") != "adjudication_artifact_hash_mismatch"


def test_self_hash_mismatch_fails_before_identity_matching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = incident_window_events(155)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(events))
    summary = build_contract_summary(events, feed_path, repo_root=tmp_path)
    finalize_complete_summary(summary)
    summary["safe_update_count_contract"]["adjudication_artifact_sha256"] = "b" * 64
    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=events, contract=summary)
    assert exit_code == 1
    assert report["failure_type"] == "adjudication_artifact_hash_mismatch"
    assert report["updated_staged_event_count"] == 0


def test_diagnostic_exact_byte_hash_unchanged(tmp_path: Path) -> None:
    payload = {"selected_candidate_count": 1, "staged_feed_provenance": {"schema_version": "gps-staged-feed-provenance-v1"}}
    target = tmp_path / "diagnostic.json"
    write_json(target, payload)
    assert sha256_file(target) == hashlib.sha256(target.read_bytes()).hexdigest()
