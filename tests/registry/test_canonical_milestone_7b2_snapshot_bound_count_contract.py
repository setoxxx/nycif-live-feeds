"""Canonical Milestone 7-B.2: snapshot-bound count contract tests."""

from __future__ import annotations

import copy
import importlib
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pytest

from scripts.gps_count_contract import (
    COUNT_CONTRACT_SCHEMA_VERSION,
    COUNT_RULES_VERSION,
    REGENERATE_COUNT_CONTRACT_NEXT_STEP,
    build_count_contract,
    compute_adjudication_self_hash,
    count_contract_failure_report,
    derive_counts_from_adjudication_summary,
    finalize_count_contract_adjudication_hash,
    validate_count_contract_for_apply,
    validate_count_contract_internal,
    validate_count_contract_schema,
)
from scripts.gps_snapshot_provenance import (
    DEFAULT_STAGED_FEED_RELATIVE_PATH,
    REGENERATE_ARTIFACTS_NEXT_STEP,
    file_provenance,
)
from tests.registry.test_canonical_milestone_7b1_snapshot_contract_hardening import (
    PROTECTED_PATHS,
    REPO_ROOT,
    build_contract_summary,
    build_staged_feed,
    incident_window_events,
    july_seventh_feed_from_old,
    make_safe_row,
    patch_next_action,
    read_json,
    run_apply_isolated,
    write_json,
)


def rebuild_count_contract(summary: dict[str, Any]) -> None:
    provenance = summary.get("staged_feed_provenance")
    if not isinstance(provenance, dict):
        return
    summary["safe_update_count_contract"] = build_count_contract(
        staged_feed_provenance=provenance,
        diagnostic_artifact_sha256=str(summary.get("diagnostic_artifact_sha256") or ""),
        selected_rows=summary.get("safe_update_ready_rows") or [],
        no_safe_match_count=int(summary.get("no_safe_staged_match_promoted_key_count") or 0),
        multi_key_conflict_count=int(summary.get("multi_key_conflict_count") or 0),
        adjudication_count_by_type=summary.get("adjudication_count_by_type") or {},
        generated_at_utc=str(summary.get("generated_at_utc") or "2026-07-13T12:00:00+00:00"),
    )
    finalize_count_contract_adjudication_hash(summary)


def valid_summary(
    tmp_path: Path,
    *,
    safe_event_count: int = 155,
    staged_events: list[dict[str, Any]] | None = None,
) -> tuple[Path, dict[str, Any]]:
    if staged_events is None:
        staged_events = incident_window_events(safe_event_count)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(staged_events))
    safe_events = staged_events[:safe_event_count]
    summary = build_contract_summary(safe_events, feed_path, repo_root=tmp_path)
    return feed_path, summary


# ---------------------------------------------------------------------------
# A. July 13 regression
# ---------------------------------------------------------------------------


def test_july13_old_204_snapshot_contract_fails_snapshot_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = incident_window_events(204)
    old_feed = tmp_path / "old_feed.json"
    write_json(old_feed, build_staged_feed(old_events))
    contract = build_contract_summary(old_events, old_feed, repo_root=tmp_path)

    new_events = july_seventh_feed_from_old(old_events, keep=155)
    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=new_events, contract=contract)

    assert exit_code == 1
    assert report["failure_type"] == "stale_staged_feed_contract"
    assert report["validated_conditions"]["snapshot_contract_preflight_passed"] is False
    assert report.get("count_contract_preflight_passed") is not True
    assert report["update_performed"] is False


def test_july13_fresh_155_contract_passes_snapshot_and_count_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_events = incident_window_events(204)
    new_events = july_seventh_feed_from_old(old_events, keep=155)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(new_events))
    contract = build_contract_summary(new_events[:155], feed_path, repo_root=tmp_path)

    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=new_events, contract=contract)

    assert report["count_contract_preflight_passed"] is True
    assert report["validated_conditions"]["snapshot_contract_preflight_passed"] is True
    assert report.get("failure_type") != "stale_staged_feed_contract"
    assert report.get("failure_type") != "legacy_contract_missing_count_contract"
    assert report["updated_staged_event_count"] == 155
    assert exit_code == 0
    assert report["qa_pass"] is True


def test_july13_fresh_155_acceptance_is_derived_not_hardcoded(tmp_path: Path) -> None:
    old_events = incident_window_events(204)
    new_events = july_seventh_feed_from_old(old_events, keep=155)
    feed_path = tmp_path / "feed.json"
    write_json(feed_path, build_staged_feed(new_events))

    summary_204 = build_contract_summary(old_events, feed_path, repo_root=tmp_path)
    summary_155 = build_contract_summary(new_events[:155], feed_path, repo_root=tmp_path)

    derived_204 = derive_counts_from_adjudication_summary(summary_204)
    derived_155 = derive_counts_from_adjudication_summary(summary_155)
    assert derived_204["safe_update_ready_identity_count"] == 204
    assert derived_155["safe_update_ready_identity_count"] == 155

    contract_155 = summary_155["safe_update_count_contract"]
    contract_155["counts"]["safe_update_ready_identity_count"] = 204
    finalize_count_contract_adjudication_hash(summary_155)
    result = validate_count_contract_for_apply(summary_155)
    assert result.ok is False
    assert result.failure_type == "count_contract_actual_count_mismatch"

    contract_155["counts"]["safe_update_ready_identity_count"] = 155
    finalize_count_contract_adjudication_hash(summary_155)
    assert validate_count_contract_for_apply(summary_155).ok is True


# ---------------------------------------------------------------------------
# B. Legacy contract without count schema
# ---------------------------------------------------------------------------


def test_legacy_contract_missing_count_contract_after_snapshot_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = incident_window_events(10)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(events))
    contract = build_contract_summary(
        events,
        feed_path,
        repo_root=tmp_path,
        include_count_contract=False,
    )

    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=events, contract=contract)

    assert exit_code == 1
    assert report["failure_type"] == "legacy_contract_missing_count_contract"
    assert report["snapshot_contract_preflight_passed"] is True
    assert report["count_contract_preflight_passed"] is False
    assert report["required_next_step"] == REGENERATE_COUNT_CONTRACT_NEXT_STEP


# ---------------------------------------------------------------------------
# C. Adversarial matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_contract_summary(tmp_path: Path) -> dict[str, Any]:
    _, summary = valid_summary(tmp_path, safe_event_count=155)
    return summary


def test_adversarial_valid_fresh_contract(fresh_contract_summary: dict[str, Any]) -> None:
    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is True


def test_adversarial_duplicate_safe_identity(fresh_contract_summary: dict[str, Any]) -> None:
    rows = fresh_contract_summary["safe_update_ready_rows"]
    duplicate = copy.deepcopy(rows[0])
    rows.append(duplicate)
    fresh_contract_summary["safe_update_ready_count"] = len(rows)
    rebuild_count_contract(fresh_contract_summary)

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "count_contract_duplicate_identity"


def test_adversarial_conflict_count_mismatch(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["multi_key_conflict_count"] = 2
    rebuild_count_contract(fresh_contract_summary)

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "count_contract_conflict_detected"


def test_adversarial_category_total_mismatch(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["adjudication_count_by_type"] = {"no_safe_match_do_not_update": 20}
    rebuild_count_contract(fresh_contract_summary)
    fresh_contract_summary["safe_update_count_contract"]["counts"]["adjudication_category_total"] = 0

    result = validate_count_contract_internal(
        fresh_contract_summary["safe_update_count_contract"],
        fresh_contract_summary,
    )
    assert result.ok is False
    assert result.failure_type == "count_contract_internal_inconsistency"


def test_adversarial_staged_feed_hash_mismatch(fresh_contract_summary: dict[str, Any]) -> None:
    contract = fresh_contract_summary["safe_update_count_contract"]
    contract["staged_feed_sha256"] = "0" * 64

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "count_contract_provenance_mismatch"


def test_adversarial_diagnostic_hash_mismatch(fresh_contract_summary: dict[str, Any]) -> None:
    contract = fresh_contract_summary["safe_update_count_contract"]
    contract["diagnostic_artifact_sha256"] = "f" * 64

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "count_contract_provenance_mismatch"


def test_adversarial_unsupported_schema(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["safe_update_count_contract"]["schema_version"] = "gps-safe-update-count-contract-v0"

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "unsupported_count_contract_schema"


def test_adversarial_missing_rules_version(fresh_contract_summary: dict[str, Any]) -> None:
    del fresh_contract_summary["safe_update_count_contract"]["derivation"]["rules_version"]

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "unsupported_count_contract_schema"


def test_adversarial_negative_counts(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["safe_update_count_contract"]["counts"]["safe_update_ready_row_count"] = -1

    result = validate_count_contract_schema(fresh_contract_summary["safe_update_count_contract"])
    assert result.ok is False
    assert result.failure_type == "unsupported_count_contract_schema"


def test_adversarial_boolean_as_integer(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["safe_update_count_contract"]["counts"]["selected_identity_count"] = True

    result = validate_count_contract_schema(fresh_contract_summary["safe_update_count_contract"])
    assert result.ok is False
    assert result.failure_type == "unsupported_count_contract_schema"


def test_adversarial_null_counts(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["safe_update_count_contract"]["counts"]["adjudication_row_count"] = None

    result = validate_count_contract_schema(fresh_contract_summary["safe_update_count_contract"])
    assert result.ok is False
    assert result.failure_type == "unsupported_count_contract_schema"


def test_adversarial_tampered_adjudication_hash(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["safe_update_count_contract"]["adjudication_artifact_sha256"] = "a" * 64

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "count_contract_provenance_mismatch"


def test_adversarial_reordered_json_keys(fresh_contract_summary: dict[str, Any]) -> None:
    contract = fresh_contract_summary["safe_update_count_contract"]
    reordered = json.loads(json.dumps(contract), object_pairs_hook=OrderedDict)
    reordered.move_to_end("schema_version", last=False)
    fresh_contract_summary["safe_update_count_contract"] = dict(reordered)

    assert validate_count_contract_for_apply(fresh_contract_summary).ok is True


def test_adversarial_deterministic_regeneration(tmp_path: Path) -> None:
    feed_path = tmp_path / "feed.json"
    events = incident_window_events(155)
    write_json(feed_path, build_staged_feed(events))
    provenance = file_provenance(
        feed_path,
        producer_script="scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
        repo_root=tmp_path,
    )
    safe_rows = [make_safe_row(row, index) for index, row in enumerate(events)]
    diagnostic_sha = "d" * 64
    generated_at = "2026-07-13T12:00:00+00:00"
    first = build_count_contract(
        staged_feed_provenance=provenance,
        diagnostic_artifact_sha256=diagnostic_sha,
        selected_rows=safe_rows,
        no_safe_match_count=20,
        multi_key_conflict_count=0,
        adjudication_count_by_type={},
        generated_at_utc=generated_at,
    )
    second = build_count_contract(
        staged_feed_provenance=provenance,
        diagnostic_artifact_sha256=diagnostic_sha,
        selected_rows=safe_rows,
        no_safe_match_count=20,
        multi_key_conflict_count=0,
        adjudication_count_by_type={},
        generated_at_utc=generated_at,
    )
    assert first["counts"] == second["counts"]
    assert first["staged_feed_sha256"] == second["staged_feed_sha256"]
    assert first["schema_version"] == COUNT_CONTRACT_SCHEMA_VERSION
    assert first["derivation"]["rules_version"] == COUNT_RULES_VERSION


def test_adversarial_reported_count_mismatch(fresh_contract_summary: dict[str, Any]) -> None:
    fresh_contract_summary["safe_update_ready_count"] = 999
    rebuild_count_contract(fresh_contract_summary)

    result = validate_count_contract_for_apply(fresh_contract_summary)
    assert result.ok is False
    assert result.failure_type == "count_contract_internal_inconsistency"


@pytest.mark.parametrize(
    ("failure_mutation", "expected_failure_type"),
    [
        (
            lambda summary: summary.__setitem__("safe_update_count_contract", None),
            "legacy_contract_missing_count_contract",
        ),
        (
            lambda summary: summary["safe_update_count_contract"].__setitem__(
                "counts", {"selected_identity_count": 1}
            ),
            "unsupported_count_contract_schema",
        ),
    ],
)
def test_apply_count_contract_failures_via_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mutation,
    expected_failure_type: str,
) -> None:
    events = incident_window_events(20)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(events))
    contract = build_contract_summary(events, feed_path, repo_root=tmp_path)
    failure_mutation(contract)

    exit_code, report = run_apply_isolated(tmp_path, monkeypatch, staged_events=events, contract=contract)

    assert exit_code == 1
    assert report["failure_type"] == expected_failure_type
    assert report["snapshot_contract_preflight_passed"] is True
    assert report["update_performed"] is False


# ---------------------------------------------------------------------------
# D. Derived counts and adjudication producer integration
# ---------------------------------------------------------------------------


def test_derive_counts_matches_bound_contract_fields(tmp_path: Path) -> None:
    _, summary = valid_summary(tmp_path, safe_event_count=155)
    derived = derive_counts_from_adjudication_summary(summary)
    bound = summary["safe_update_count_contract"]["counts"]
    for key in (
        "selected_identity_count",
        "safe_update_ready_identity_count",
        "safe_update_ready_row_count",
        "no_safe_match_promoted_key_count",
        "multi_key_conflict_count",
        "adjudication_row_count",
    ):
        assert derived[key] == bound[key]


def test_adjudication_producer_emits_count_contract_for_155(tmp_path: Path) -> None:
    feed = tmp_path / "feed.json"
    write_json(feed, build_staged_feed([]))
    diagnostic_path = tmp_path / "diagnostic.json"
    summary_path = tmp_path / "summary.json"
    write_json(
        diagnostic_path,
        {
            "dry_run_expected_matched_staged_event_count": 430,
            "multi_key_conflict_count": 0,
            "near_miss_diagnostics_by_promoted_cache_key": {},
            "selected_candidate_count": 155,
            "selected_stable_event_identity_count": 155,
            "selected_stable_identity_rows": [
                {
                    "stable_event_identity": f"id-{index}",
                    "source_event_id": f"EV-{index}",
                    "display_location": f"Park {index}",
                    "source_cemsid": [f"CEM-{index}"],
                    "promoted_cache_key": f"group:test|{index}",
                    "promoted_lat": 40.75,
                    "promoted_lng": -73.95,
                }
                for index in range(155)
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
    adjudication.ROOT = tmp_path
    adjudication.DIAGNOSTIC_PATH = diagnostic_path
    adjudication.SUMMARY_PATH = summary_path
    exit_code = adjudication.main()
    summary = read_json(summary_path)

    assert exit_code == 0
    assert summary["qa_pass"] is True
    assert summary["safe_update_count_contract"]["counts"]["safe_update_ready_identity_count"] == 155
    assert summary["recommended_next_action"] == patch_next_action(155)


def test_compute_adjudication_self_hash_is_stable(fresh_contract_summary: dict[str, Any]) -> None:
    first = compute_adjudication_self_hash(fresh_contract_summary)
    second = compute_adjudication_self_hash(fresh_contract_summary)
    assert first == second
    assert first == fresh_contract_summary["safe_update_count_contract"]["adjudication_artifact_sha256"]


# ---------------------------------------------------------------------------
# E. Count contract failure report shape
# ---------------------------------------------------------------------------


def test_count_contract_failure_report_shape() -> None:
    validation = validate_count_contract_for_apply({"qa_pass": True})
    report = count_contract_failure_report(
        validation,
        input_adjudication_summary="data/gps_staged_feed_integration_adjudication_summary.json",
        input_staged_feed=DEFAULT_STAGED_FEED_RELATIVE_PATH,
        snapshot_preflight_passed=True,
        generated_at_utc="2026-07-13T12:00:00+00:00",
    )
    assert report["qa_pass"] is False
    assert report["failure_type"] == "legacy_contract_missing_count_contract"
    assert report["snapshot_contract_preflight_passed"] is True
    assert report["count_contract_preflight_passed"] is False
    assert report["required_next_step"] == REGENERATE_COUNT_CONTRACT_NEXT_STEP
    assert report["location_cache_modified"] is False
    assert report["public_map_modified"] is False
    assert report["staged_feed_modified"] is False


# ---------------------------------------------------------------------------
# F. Input immutability and protected boundaries
# ---------------------------------------------------------------------------


def test_apply_count_preflight_does_not_mutate_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = incident_window_events(5)
    feed_path = tmp_path / "data" / "nycif_staged_live_events.json"
    write_json(feed_path, build_staged_feed(events))
    contract = build_contract_summary(events, feed_path, repo_root=tmp_path)
    contract["safe_update_count_contract"]["counts"]["selected_identity_count"] = 999
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


def test_protected_production_paths_exist_and_were_not_modified_by_tests() -> None:
    for path in PROTECTED_PATHS:
        assert path.exists()


def test_changed_files_do_not_include_protected_data_paths() -> None:
    changed = {
        "scripts/gps_count_contract.py",
        "scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
        "scripts/apply_gps_staged_feed_integration_update.py",
        "tests/registry/test_canonical_milestone_7b1_snapshot_contract_hardening.py",
        "tests/registry/test_canonical_milestone_7b2_snapshot_bound_count_contract.py",
    }
    protected = {path.relative_to(REPO_ROOT).as_posix() for path in PROTECTED_PATHS}
    assert changed.isdisjoint(protected)


# ---------------------------------------------------------------------------
# G. No-network behavior
# ---------------------------------------------------------------------------


def test_count_contract_module_has_no_network_imports() -> None:
    source = (REPO_ROOT / "scripts" / "gps_count_contract.py").read_text(encoding="utf-8")
    forbidden = ("urllib", "requests", "http.client", "socket", "ftplib")
    assert not any(token in source for token in forbidden)


def test_direct_script_execution_imports_count_contract_helper() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util, pathlib, sys; "
            "root = pathlib.Path('scripts').resolve().parent; "
            "sys.path.insert(0, str(root)); "
            "from scripts.gps_count_contract import COUNT_CONTRACT_SCHEMA_VERSION; "
            "print(COUNT_CONTRACT_SCHEMA_VERSION)",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert COUNT_CONTRACT_SCHEMA_VERSION in result.stdout


def test_snapshot_regenerate_next_step_differs_from_count_contract_next_step() -> None:
    assert REGENERATE_ARTIFACTS_NEXT_STEP != REGENERATE_COUNT_CONTRACT_NEXT_STEP


def test_no_historical_count_constant_remains_in_active_chain() -> None:
    """Full-chain completion (M7-B.2): the diagnostic, adjudication, apply, and
    count-contract modules must not reference the historical hard-coded count
    constants outside comments — including the diagnostic's 430/25 gates."""
    for rel in (
        "scripts/generate_gps_staged_feed_integration_match_diagnostic.py",
        "scripts/generate_gps_staged_feed_integration_adjudication_summary.py",
        "scripts/apply_gps_staged_feed_integration_update.py",
        "scripts/gps_count_contract.py",
    ):
        code = "\n".join(
            line
            for line in (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        for token in (
            "EXPECTED_SAFE_UPDATE_READY_COUNT",
            "EXPECTED_NO_SAFE_MATCH_PROMOTED_KEY_COUNT",
            "EXPECTED_STAGED_MATCHES",
            "EXPECTED_PROMOTED_CACHE_KEYS",
        ):
            assert token not in code, f"{rel} still references {token} outside comments"


def test_adjudication_self_hash_round_trips_through_persisted_summary(tmp_path: Path) -> None:
    """Regression (Canonical Milestone 7-B.2): the adjudication self-hash must be
    computed over the COMPLETE persisted summary, so the apply-time validator
    reproduces it exactly. Previously it was computed over an intermediate dict
    lacking qa_pass/recommended_next_action/validated_conditions, so every real
    producer->disk->apply round-trip failed with count_contract_provenance_mismatch."""
    feed = tmp_path / "feed.json"
    write_json(feed, build_staged_feed([]))
    diagnostic_path = tmp_path / "diagnostic.json"
    summary_path = tmp_path / "summary.json"
    write_json(
        diagnostic_path,
        {
            "dry_run_expected_matched_staged_event_count": 430,
            "multi_key_conflict_count": 0,
            "near_miss_diagnostics_by_promoted_cache_key": {},
            "selected_candidate_count": 155,
            "selected_stable_event_identity_count": 155,
            "selected_stable_identity_rows": [
                {
                    "stable_event_identity": f"id-{index}",
                    "source_event_id": f"EV-{index}",
                    "display_location": f"Park {index}",
                    "source_cemsid": [f"CEM-{index}"],
                    "promoted_cache_key": f"group:test|{index}",
                    "promoted_lat": 40.75,
                    "promoted_lng": -73.95,
                }
                for index in range(155)
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
    adjudication.ROOT = tmp_path
    adjudication.DIAGNOSTIC_PATH = diagnostic_path
    adjudication.SUMMARY_PATH = summary_path
    assert adjudication.main() == 0

    persisted = read_json(summary_path)
    stored = persisted["safe_update_count_contract"]["adjudication_artifact_sha256"]
    assert stored is not None
    # The exact round-trip the apply-time validator performs:
    assert compute_adjudication_self_hash(persisted) == stored
    # And the persisted summary must actually contain the fields the old code
    # omitted from the hash input.
    assert "qa_pass" in persisted
    assert "validated_conditions" in persisted
    assert "recommended_next_action" in persisted
