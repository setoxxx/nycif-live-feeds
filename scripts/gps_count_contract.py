#!/usr/bin/env python3
"""Snapshot-bound GPS safe-update count contract (Canonical Milestone 7-B.2).

Derives authoritative counts from diagnostic/adjudication artifact contents and
binds them to staged-feed provenance. Apply validates the contract only after
snapshot preflight passes. Historical constants (for example 204) are never
runtime truth.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

try:
    from scripts.gps_snapshot_provenance import SCHEMA_VERSION as PROVENANCE_SCHEMA_VERSION
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from gps_snapshot_provenance import SCHEMA_VERSION as PROVENANCE_SCHEMA_VERSION

COUNT_CONTRACT_SCHEMA_VERSION = "gps-safe-update-count-contract-v1"
COUNT_RULES_VERSION = "gps-safe-update-count-rules-v1"
ADJUDICATION_PRODUCER_SCRIPT = (
    "scripts/generate_gps_staged_feed_integration_adjudication_summary.py"
)

REGENERATE_COUNT_CONTRACT_NEXT_STEP = (
    "Regenerate diagnostic and adjudication artifacts using the current M7-B.2 "
    "producer."
)

__all__ = [
    "ADJUDICATION_PRODUCER_SCRIPT",
    "COUNT_CONTRACT_SCHEMA_VERSION",
    "COUNT_RULES_VERSION",
    "CountContractValidationResult",
    "build_count_contract",
    "compute_adjudication_self_hash",
    "count_contract_failure_report",
    "derive_counts_from_adjudication_summary",
    "finalize_count_contract_adjudication_hash",
    "validate_count_contract_for_apply",
    "validate_count_contract_internal",
]


@dataclass(frozen=True)
class CountContractValidationResult:
    ok: bool
    failure_type: str | None = None
    message: str | None = None
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _staged_feed_sha256(provenance: Any) -> str | None:
    if not isinstance(provenance, dict):
        return None
    staged_feed = provenance.get("staged_feed")
    if not isinstance(staged_feed, dict):
        return None
    sha = staged_feed.get("sha256")
    return str(sha) if sha else None


def _staged_feed_byte_size(provenance: Any) -> int | None:
    if not isinstance(provenance, dict):
        return None
    staged_feed = provenance.get("staged_feed")
    if not isinstance(staged_feed, dict):
        return None
    byte_size = staged_feed.get("byte_size")
    if byte_size is None:
        return None
    try:
        return int(byte_size)
    except (TypeError, ValueError):
        return None


def _safe_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = summary.get("safe_update_ready_rows")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _unique_safe_identities(rows: list[dict[str, Any]]) -> list[str]:
    identities: list[str] = []
    seen: set[str] = set()
    for row in rows:
        identity = str(row.get("stable_event_identity") or "")
        if not identity:
            continue
        if identity in seen:
            continue
        seen.add(identity)
        identities.append(identity)
    return identities


def _duplicate_safe_identities(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        identity = str(row.get("stable_event_identity") or "")
        if not identity:
            continue
        if identity in seen:
            duplicates.add(identity)
        seen.add(identity)
    return sorted(duplicates)


def _adjudication_category_total(summary: dict[str, Any]) -> int:
    counts = summary.get("adjudication_count_by_type")
    if not isinstance(counts, dict):
        return 0
    total = 0
    for value in counts.values():
        if _is_non_negative_int(value):
            total += int(value)
    return total


def derive_counts_from_adjudication_summary(summary: dict[str, Any]) -> dict[str, int]:
    """Independently recompute authoritative counts from adjudication content."""
    safe_rows = _safe_rows(summary)
    unique_identities = _unique_safe_identities(safe_rows)
    no_safe_match_count = int(summary.get("no_safe_staged_match_promoted_key_count") or 0)
    multi_key_conflict_count = int(summary.get("multi_key_conflict_count") or 0)
    selected_identity_count = int(summary.get("safe_update_ready_count") or 0)
    safe_identity_count = int(summary.get("safe_update_ready_identity_count") or 0)
    category_total = _adjudication_category_total(summary)
    adjudication_row_count = safe_identity_count + no_safe_match_count
    return {
        "selected_identity_count": len(unique_identities),
        "safe_update_ready_identity_count": len(unique_identities),
        "safe_update_ready_row_count": len(safe_rows),
        "no_safe_match_promoted_key_count": no_safe_match_count,
        "multi_key_conflict_count": multi_key_conflict_count,
        "adjudication_row_count": adjudication_row_count,
        "adjudication_category_total": category_total,
        "reported_selected_identity_count": selected_identity_count,
        "reported_safe_update_ready_identity_count": safe_identity_count,
    }


def build_count_contract(
    *,
    staged_feed_provenance: dict[str, Any],
    diagnostic_artifact_sha256: str | None,
    selected_rows: list[dict[str, Any]],
    no_safe_match_count: int,
    multi_key_conflict_count: int,
    adjudication_count_by_type: dict[str, int],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build a versioned count contract from in-memory adjudication data."""
    unique_identities = _unique_safe_identities(selected_rows)
    safe_row_count = len(selected_rows)
    safe_identity_count = len(unique_identities)
    adjudication_row_count = safe_identity_count + int(no_safe_match_count)
    return {
        "schema_version": COUNT_CONTRACT_SCHEMA_VERSION,
        "staged_feed_sha256": _staged_feed_sha256(staged_feed_provenance),
        "staged_feed_byte_size": _staged_feed_byte_size(staged_feed_provenance),
        "diagnostic_artifact_sha256": diagnostic_artifact_sha256,
        "adjudication_artifact_sha256": None,
        "counts": {
            "selected_identity_count": safe_identity_count,
            "safe_update_ready_identity_count": safe_identity_count,
            "safe_update_ready_row_count": safe_row_count,
            "no_safe_match_promoted_key_count": int(no_safe_match_count),
            "multi_key_conflict_count": int(multi_key_conflict_count),
            "adjudication_row_count": adjudication_row_count,
            "adjudication_category_total": sum(
                int(value) for value in adjudication_count_by_type.values()
            ),
        },
        "derivation": {
            "producer_script": ADJUDICATION_PRODUCER_SCRIPT,
            "generated_at_utc": generated_at_utc,
            "rules_version": COUNT_RULES_VERSION,
            "provenance_schema_version": PROVENANCE_SCHEMA_VERSION,
        },
    }


def compute_adjudication_self_hash(summary: dict[str, Any]) -> str:
    """Hash adjudication payload excluding the self-referential count-contract hash."""
    payload = copy.deepcopy(summary)
    contract = payload.get("safe_update_count_contract")
    if isinstance(contract, dict):
        contract["adjudication_artifact_sha256"] = None
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def finalize_count_contract_adjudication_hash(summary: dict[str, Any]) -> None:
    contract = summary.get("safe_update_count_contract")
    if not isinstance(contract, dict):
        return
    contract["adjudication_artifact_sha256"] = compute_adjudication_self_hash(summary)


def _contract_counts(contract: dict[str, Any]) -> dict[str, Any] | None:
    counts = contract.get("counts")
    return counts if isinstance(counts, dict) else None


def validate_count_contract_schema(contract: Any) -> CountContractValidationResult:
    if not isinstance(contract, dict):
        return CountContractValidationResult(
            ok=False,
            failure_type="missing_count_contract",
            message="Adjudication summary is missing safe_update_count_contract",
        )
    if contract.get("schema_version") != COUNT_CONTRACT_SCHEMA_VERSION:
        return CountContractValidationResult(
            ok=False,
            failure_type="unsupported_count_contract_schema",
            message=f"Unsupported count contract schema_version: {contract.get('schema_version')!r}",
        )
    derivation = contract.get("derivation")
    if not isinstance(derivation, dict) or not derivation.get("rules_version"):
        return CountContractValidationResult(
            ok=False,
            failure_type="unsupported_count_contract_schema",
            message="Count contract derivation.rules_version is mandatory",
        )
    counts = _contract_counts(contract)
    if counts is None:
        return CountContractValidationResult(
            ok=False,
            failure_type="unsupported_count_contract_schema",
            message="Count contract is missing counts section",
        )
    required_fields = (
        "selected_identity_count",
        "safe_update_ready_identity_count",
        "safe_update_ready_row_count",
        "no_safe_match_promoted_key_count",
        "multi_key_conflict_count",
        "adjudication_row_count",
    )
    for field in required_fields:
        value = counts.get(field)
        if value is None:
            return CountContractValidationResult(
                ok=False,
                failure_type="unsupported_count_contract_schema",
                message=f"Count contract counts.{field} is required",
            )
        if not _is_non_negative_int(value):
            return CountContractValidationResult(
                ok=False,
                failure_type="unsupported_count_contract_schema",
                message=f"Count contract counts.{field} must be a non-negative integer",
            )
    if not contract.get("staged_feed_sha256") or contract.get("staged_feed_byte_size") is None:
        return CountContractValidationResult(
            ok=False,
            failure_type="unsupported_count_contract_schema",
            message="Count contract is missing staged-feed binding fields",
        )
    if not contract.get("diagnostic_artifact_sha256"):
        return CountContractValidationResult(
            ok=False,
            failure_type="unsupported_count_contract_schema",
            message="Count contract is missing diagnostic_artifact_sha256",
        )
    return CountContractValidationResult(ok=True)


def validate_count_contract_bindings(
    contract: dict[str, Any],
    summary: dict[str, Any],
) -> CountContractValidationResult:
    provenance = summary.get("staged_feed_provenance")
    expected_feed_sha = _staged_feed_sha256(provenance)
    expected_feed_size = _staged_feed_byte_size(provenance)
    if contract.get("staged_feed_sha256") != expected_feed_sha:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_provenance_mismatch",
            message="Count contract staged_feed_sha256 does not match adjudication provenance",
            expected={"staged_feed_sha256": expected_feed_sha},
            actual={"staged_feed_sha256": contract.get("staged_feed_sha256")},
        )
    if int(contract.get("staged_feed_byte_size") or -1) != int(expected_feed_size or -2):
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_provenance_mismatch",
            message="Count contract staged_feed_byte_size does not match adjudication provenance",
            expected={"staged_feed_byte_size": expected_feed_size},
            actual={"staged_feed_byte_size": contract.get("staged_feed_byte_size")},
        )
    if contract.get("diagnostic_artifact_sha256") != summary.get("diagnostic_artifact_sha256"):
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_provenance_mismatch",
            message="Count contract diagnostic_artifact_sha256 does not match adjudication summary",
            expected={"diagnostic_artifact_sha256": summary.get("diagnostic_artifact_sha256")},
            actual={"diagnostic_artifact_sha256": contract.get("diagnostic_artifact_sha256")},
        )
    expected_adj_hash = compute_adjudication_self_hash(summary)
    if contract.get("adjudication_artifact_sha256") != expected_adj_hash:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_provenance_mismatch",
            message="Count contract adjudication_artifact_sha256 does not match adjudication summary",
            expected={"adjudication_artifact_sha256": expected_adj_hash},
            actual={"adjudication_artifact_sha256": contract.get("adjudication_artifact_sha256")},
        )
    return CountContractValidationResult(ok=True)


def validate_count_contract_internal(
    contract: dict[str, Any],
    summary: dict[str, Any],
) -> CountContractValidationResult:
    counts = _contract_counts(contract)
    if counts is None:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_internal_inconsistency",
            message="Count contract counts section is missing",
        )

    derived = derive_counts_from_adjudication_summary(summary)
    safe_rows = _safe_rows(summary)
    duplicates = _duplicate_safe_identities(safe_rows)

    if duplicates:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_duplicate_identity",
            message="Duplicate stable_event_identity values detected in safe_update_ready_rows",
            actual={"duplicate_identities": duplicates},
        )

    if int(counts["multi_key_conflict_count"]) != 0 or derived["multi_key_conflict_count"] != 0:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_conflict_detected",
            message="Multi-key conflicts must remain zero for safe-update contracts",
            expected={"multi_key_conflict_count": 0},
            actual={"multi_key_conflict_count": derived["multi_key_conflict_count"]},
        )

    arithmetic_checks = {
        "selected_identity_count": derived["selected_identity_count"],
        "safe_update_ready_identity_count": derived["safe_update_ready_identity_count"],
        "safe_update_ready_row_count": derived["safe_update_ready_row_count"],
        "no_safe_match_promoted_key_count": derived["no_safe_match_promoted_key_count"],
        "multi_key_conflict_count": derived["multi_key_conflict_count"],
        "adjudication_row_count": derived["adjudication_row_count"],
    }
    contract_checks = {key: int(counts[key]) for key in arithmetic_checks}
    mismatches = {
        key: {"expected": contract_checks[key], "actual": arithmetic_checks[key]}
        for key in arithmetic_checks
        if contract_checks[key] != arithmetic_checks[key]
    }
    if mismatches:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_actual_count_mismatch",
            message="Recomputed adjudication counts do not match count contract",
            expected=contract_checks,
            actual=arithmetic_checks,
        )

    if derived["reported_selected_identity_count"] != derived["selected_identity_count"]:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_internal_inconsistency",
            message="safe_update_ready_count does not match unique safe identities",
            expected={"safe_update_ready_count": derived["selected_identity_count"]},
            actual={"safe_update_ready_count": derived["reported_selected_identity_count"]},
        )
    if derived["reported_safe_update_ready_identity_count"] != derived["safe_update_ready_identity_count"]:
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_internal_inconsistency",
            message="safe_update_ready_identity_count does not match unique safe identities",
            expected={
                "safe_update_ready_identity_count": derived["safe_update_ready_identity_count"]
            },
            actual={
                "safe_update_ready_identity_count": derived["reported_safe_update_ready_identity_count"]
            },
        )
    if derived["adjudication_row_count"] != int(counts["adjudication_row_count"]):
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_internal_inconsistency",
            message="adjudication_row_count does not reconcile safe and no-safe-match totals",
        )
    if derived["adjudication_category_total"] != int(counts.get("adjudication_category_total") or 0):
        return CountContractValidationResult(
            ok=False,
            failure_type="count_contract_internal_inconsistency",
            message="adjudication_category_total does not match adjudication_count_by_type sum",
        )
    return CountContractValidationResult(ok=True)


def validate_count_contract_for_apply(summary: dict[str, Any]) -> CountContractValidationResult:
    contract = summary.get("safe_update_count_contract")
    if contract is None:
        return CountContractValidationResult(
            ok=False,
            failure_type="legacy_contract_missing_count_contract",
            message="Provenance-valid adjudication artifact has no versioned count contract",
        )

    schema_result = validate_count_contract_schema(contract)
    if not schema_result.ok:
        return schema_result

    binding_result = validate_count_contract_bindings(contract, summary)
    if not binding_result.ok:
        return binding_result

    internal_result = validate_count_contract_internal(contract, summary)
    if not internal_result.ok:
        return internal_result

    return CountContractValidationResult(ok=True)


def count_contract_failure_report(
    validation: CountContractValidationResult,
    *,
    input_adjudication_summary: str,
    input_staged_feed: str,
    snapshot_preflight_passed: bool,
    phase: str = "gps_staged_feed_integration_update",
    generated_at_utc: str,
) -> dict[str, Any]:
    failure_type = validation.failure_type or "count_contract_internal_inconsistency"
    return {
        "blocking_issues": [validation.message or "Count contract validation failed"],
        "conflict_count": 0,
        "count_contract_actual": validation.actual,
        "count_contract_expected": validation.expected,
        "count_contract_preflight_passed": False,
        "failure_type": failure_type,
        "generated_at_utc": generated_at_utc,
        "input_adjudication_summary": input_adjudication_summary,
        "input_staged_feed": input_staged_feed,
        "location_cache_modified": False,
        "next_required_step": REGENERATE_COUNT_CONTRACT_NEXT_STEP,
        "phase": phase,
        "phase_3a_run": False,
        "public_map_modified": False,
        "qa_pass": False,
        "required_next_step": REGENERATE_COUNT_CONTRACT_NEXT_STEP,
        "safe_update_contract_count": 0,
        "safe_update_ready_identity_count": 0,
        "skipped_count": 0,
        "snapshot_contract_preflight_passed": snapshot_preflight_passed,
        "staged_feed_modified": False,
        "update_performed": False,
        "updated_staged_event_count": 0,
        "validated_conditions": {
            "adjudication_summary_qa_pass_true": True,
            "conflict_count_is_0": True,
            "count_contract_preflight_passed": False,
            "location_cache_modified_false": True,
            "phase_3a_run_false": True,
            "public_map_modified_false": True,
            "qa_pass_true": False,
            "snapshot_contract_preflight_passed": snapshot_preflight_passed,
            "staged_feed_modified_true": False,
            "update_performed_true": False,
        },
    }
