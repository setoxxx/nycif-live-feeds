"""XRI-G44 fixture-only audit reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tools.registry.xri_g43_fixture_only_manual_review_handoff import (
    ManualReviewHandoffRecord,
    build_manual_review_handoff_record,
    build_manual_review_handoff_records,
)


class FixtureOnlyAuditReportingError(ValueError):
    """Raised when fixture-only audit-reporting rules fail closed."""


_IDENTITY_BASIS = ("group_key", "display_location", "candidate_identity")
_BLOCKED_STATES = {
    "approval",
    "approved",
    "promotion",
    "promoted",
    "publishing",
    "published",
    "geocoded",
    "production_ready",
    "public_runtime_ready",
}


@dataclass(frozen=True)
class FixtureAuditReport:
    schema: str
    phase: str
    fixture_count: int
    ready_for_manual_review_count: int
    stable_identities: tuple[str, ...]
    identity_basis: tuple[str, ...]
    validation_check_summary: Mapping[str, int]
    handoff_status_summary: Mapping[str, int]
    blocked_state_summary: Mapping[str, bool]
    safety_confirmations: Mapping[str, bool]
    raw_fixture_metadata_summary: Mapping[str, int]


def _identity(record: ManualReviewHandoffRecord) -> str:
    return "|".join((record.group_key, record.display_location, record.candidate_identity))


def _ensure_handoff(record: Mapping[str, Any] | ManualReviewHandoffRecord) -> ManualReviewHandoffRecord:
    if isinstance(record, ManualReviewHandoffRecord):
        return record
    if isinstance(record, Mapping):
        return build_manual_review_handoff_record(record)
    raise FixtureOnlyAuditReportingError("Audit input must be a mapping or ManualReviewHandoffRecord")


def _reject_blocked_report_states(records: Sequence[ManualReviewHandoffRecord]) -> None:
    for record in records:
        merged: dict[str, Any] = {}
        merged.update(record.normalized_summary)
        merged.update(record.raw_fixture_metadata)
        for field in _BLOCKED_STATES:
            if bool(merged.get(field)):
                raise FixtureOnlyAuditReportingError("Audit report cannot carry final-state field: " + field)


def build_fixture_audit_report(records: Mapping[str, Any] | ManualReviewHandoffRecord | Sequence[Mapping[str, Any] | ManualReviewHandoffRecord]) -> FixtureAuditReport:
    if isinstance(records, (Mapping, ManualReviewHandoffRecord)):
        handoff_records = [_ensure_handoff(records)]
    elif isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
        handoff_records = [_ensure_handoff(record) for record in records]
    else:
        raise FixtureOnlyAuditReportingError("Audit input must be one record or a sequence")

    _reject_blocked_report_states(handoff_records)

    stable_identities = tuple(sorted(_identity(record) for record in handoff_records))
    validation_check_summary: dict[str, int] = {}
    metadata_key_summary: dict[str, int] = {}
    ready_count = 0

    for record in handoff_records:
        if record.ready_for_manual_review:
            ready_count += 1
        for check in record.validation_checks:
            validation_check_summary[check] = validation_check_summary.get(check, 0) + 1
        for key in record.raw_fixture_metadata:
            metadata_key_summary[key] = metadata_key_summary.get(key, 0) + 1

    handoff_status_summary = {
        "ready_for_manual_review_true": ready_count,
        "ready_for_manual_review_false": len(handoff_records) - ready_count,
    }
    blocked_state_summary = {field: False for field in sorted(_BLOCKED_STATES)}
    safety_confirmations = {
        "fixture_only_inputs": True,
        "deterministic_output": True,
        "production_allowed": False,
        "xri_g45_started": False,
    }

    return FixtureAuditReport(
        schema="nycif.xri_g44.fixture_only_audit_report.v1",
        phase="XRI-G44",
        fixture_count=len(handoff_records),
        ready_for_manual_review_count=ready_count,
        stable_identities=stable_identities,
        identity_basis=_IDENTITY_BASIS,
        validation_check_summary=dict(sorted(validation_check_summary.items())),
        handoff_status_summary=handoff_status_summary,
        blocked_state_summary=blocked_state_summary,
        safety_confirmations=safety_confirmations,
        raw_fixture_metadata_summary=dict(sorted(metadata_key_summary.items())),
    )


def validate_and_build_fixture_audit_report(records: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> FixtureAuditReport:
    handoff_records = build_manual_review_handoff_records(records)
    return build_fixture_audit_report(handoff_records)
