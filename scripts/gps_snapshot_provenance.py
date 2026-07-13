#!/usr/bin/env python3
"""Staged-feed snapshot provenance and hash-contract validation.

Canonical Milestone 7-B.1 foundation module. Binds GPS diagnostic,
adjudication, and apply stages to the exact byte content of the staged-feed
snapshot they were derived from.

Hash contract: SHA-256 over the exact on-disk file bytes (UTF-8 is expected
for JSON text, but the digest is byte-for-byte — newline, whitespace, key
order, and Unicode code-unit sequences are all sensitivity factors). The file
path is recorded for human audit but is excluded from the digest itself.
Timestamps are informational only and never authorize a contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "gps-staged-feed-provenance-v1"
DEFAULT_STAGED_FEED_RELATIVE_PATH = "data/nycif_staged_live_events.json"

REGENERATE_ARTIFACTS_NEXT_STEP = (
    "Regenerate the GPS staged-feed integration diagnostic and adjudication "
    "summary against the current staged feed before retrying the update."
)

__all__ = [
    "DEFAULT_STAGED_FEED_RELATIVE_PATH",
    "REGENERATE_ARTIFACTS_NEXT_STEP",
    "SCHEMA_VERSION",
    "SnapshotValidationResult",
    "file_provenance",
    "normalize_repo_relative_path",
    "provenance_failure_report",
    "sha256_file",
    "validate_bound_snapshot",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_repo_relative_path(path: Path | str, *, repo_root: Path | None = None) -> str:
    """Return a forward-slash repo-relative path when possible."""
    candidate = Path(path)
    if repo_root is not None:
        try:
            return candidate.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    return candidate.as_posix()


def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of the exact file bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_provenance(
    path: Path,
    *,
    producer_script: str,
    source_commit_sha: str | None = None,
    upstream_artifact_sha256: str | None = None,
    generated_at_utc: str | None = None,
    repo_root: Path | None = None,
    staged_feed_path: str | None = None,
) -> dict[str, Any]:
    """Build a versioned provenance object for a staged-feed snapshot file."""
    if not path.exists():
        raise FileNotFoundError(path)
    stat = path.stat()
    return {
        "schema_version": SCHEMA_VERSION,
        "staged_feed": {
            "path": staged_feed_path or normalize_repo_relative_path(path, repo_root=repo_root),
            "sha256": sha256_file(path),
            "byte_size": int(stat.st_size),
            "git_blob_sha": None,
            "commit_sha": source_commit_sha,
        },
        "producer": {
            "script": producer_script,
            "generated_at_utc": generated_at_utc or utc_now(),
            "upstream_artifact_sha256": upstream_artifact_sha256,
        },
    }


@dataclass(frozen=True)
class SnapshotValidationResult:
    ok: bool
    failure_type: str | None = None
    message: str | None = None
    expected_staged_feed_sha256: str | None = None
    actual_staged_feed_sha256: str | None = None
    expected_staged_feed_byte_size: int | None = None
    actual_staged_feed_byte_size: int | None = None
    expected_staged_feed_path: str | None = None
    actual_staged_feed_path: str | None = None
    contract_generated_at_utc: str | None = None
    contract_source: str | None = None


def _staged_feed_section(contract_provenance: Any) -> dict[str, Any] | None:
    if not isinstance(contract_provenance, dict):
        return None
    staged_feed = contract_provenance.get("staged_feed")
    return staged_feed if isinstance(staged_feed, dict) else None


def validate_bound_snapshot(
    contract_provenance: Any,
    current_path: Path,
    *,
    repo_root: Path | None = None,
    contract_source: str | None = None,
) -> SnapshotValidationResult:
    """Fail closed unless the current staged feed matches the bound snapshot."""
    producer = contract_provenance.get("producer") if isinstance(contract_provenance, dict) else None
    generated_at = producer.get("generated_at_utc") if isinstance(producer, dict) else None
    source = contract_source or (
        producer.get("script") if isinstance(producer, dict) else None
    )

    if not isinstance(contract_provenance, dict):
        return SnapshotValidationResult(
            ok=False,
            failure_type="legacy_contract_missing_snapshot_hash",
            message="Contract is missing staged_feed_provenance",
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    schema_version = contract_provenance.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        return SnapshotValidationResult(
            ok=False,
            failure_type="legacy_contract_missing_snapshot_hash",
            message=f"Unsupported or missing provenance schema_version: {schema_version!r}",
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    staged_feed = _staged_feed_section(contract_provenance)
    if staged_feed is None:
        return SnapshotValidationResult(
            ok=False,
            failure_type="legacy_contract_missing_snapshot_hash",
            message="Contract provenance is missing staged_feed section",
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    expected_path = staged_feed.get("path")
    expected_sha = staged_feed.get("sha256")
    expected_size = staged_feed.get("byte_size")
    if not expected_path or not expected_sha or expected_size is None:
        return SnapshotValidationResult(
            ok=False,
            failure_type="legacy_contract_missing_snapshot_hash",
            message="Contract provenance is missing mandatory staged_feed path, sha256, or byte_size",
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    actual_path = normalize_repo_relative_path(current_path, repo_root=repo_root)
    if str(expected_path) != actual_path:
        return SnapshotValidationResult(
            ok=False,
            failure_type="stale_staged_feed_contract",
            message="Staged-feed path does not match bound contract path",
            expected_staged_feed_sha256=str(expected_sha),
            actual_staged_feed_sha256=None,
            expected_staged_feed_byte_size=int(expected_size),
            actual_staged_feed_byte_size=None,
            expected_staged_feed_path=str(expected_path),
            actual_staged_feed_path=actual_path,
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    if not current_path.exists():
        return SnapshotValidationResult(
            ok=False,
            failure_type="stale_staged_feed_contract",
            message="Current staged feed file does not exist",
            expected_staged_feed_sha256=str(expected_sha),
            actual_staged_feed_sha256=None,
            expected_staged_feed_byte_size=int(expected_size),
            actual_staged_feed_byte_size=None,
            expected_staged_feed_path=str(expected_path),
            actual_staged_feed_path=actual_path,
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    actual_size = int(current_path.stat().st_size)
    actual_sha = sha256_file(current_path)

    if actual_sha != str(expected_sha) or actual_size != int(expected_size):
        return SnapshotValidationResult(
            ok=False,
            failure_type="stale_staged_feed_contract",
            message="Current staged feed bytes do not match bound contract snapshot",
            expected_staged_feed_sha256=str(expected_sha),
            actual_staged_feed_sha256=actual_sha,
            expected_staged_feed_byte_size=int(expected_size),
            actual_staged_feed_byte_size=actual_size,
            expected_staged_feed_path=str(expected_path),
            actual_staged_feed_path=actual_path,
            contract_generated_at_utc=generated_at,
            contract_source=source,
        )

    return SnapshotValidationResult(ok=True, contract_generated_at_utc=generated_at, contract_source=source)


def provenance_failure_report(
    validation: SnapshotValidationResult,
    *,
    input_adjudication_summary: str,
    input_staged_feed: str,
    phase: str = "gps_staged_feed_integration_update",
) -> dict[str, Any]:
    """Build a fail-closed update report for snapshot provenance failures."""
    failure_type = validation.failure_type or "legacy_contract_missing_snapshot_hash"
    report: dict[str, Any] = {
        "blocking_issues": [validation.message or "Staged-feed snapshot contract validation failed"],
        "conflict_count": 0,
        "contract_generated_at_utc": validation.contract_generated_at_utc,
        "contract_source": validation.contract_source,
        "failure_type": failure_type,
        "generated_at_utc": utc_now(),
        "input_adjudication_summary": input_adjudication_summary,
        "input_staged_feed": input_staged_feed,
        "location_cache_modified": False,
        "next_required_step": REGENERATE_ARTIFACTS_NEXT_STEP,
        "phase": phase,
        "phase_3a_run": False,
        "public_map_modified": False,
        "qa_pass": False,
        "required_next_step": REGENERATE_ARTIFACTS_NEXT_STEP,
        "safe_update_contract_count": 0,
        "safe_update_ready_identity_count": 0,
        "skipped_count": 0,
        "staged_feed_modified": False,
        "update_performed": False,
        "updated_staged_event_count": 0,
        "validated_conditions": {
            "adjudication_summary_qa_pass_true": False,
            "conflict_count_is_0": True,
            "location_cache_modified_false": True,
            "phase_3a_run_false": True,
            "public_map_modified_false": True,
            "qa_pass_true": False,
            "snapshot_contract_preflight_passed": False,
            "staged_feed_modified_true": False,
            "update_performed_true": False,
        },
    }
    if failure_type == "stale_staged_feed_contract":
        report.update(
            {
                "actual_staged_feed_byte_size": validation.actual_staged_feed_byte_size,
                "actual_staged_feed_sha256": validation.actual_staged_feed_sha256,
                "expected_staged_feed_byte_size": validation.expected_staged_feed_byte_size,
                "expected_staged_feed_sha256": validation.expected_staged_feed_sha256,
            }
        )
    return report
