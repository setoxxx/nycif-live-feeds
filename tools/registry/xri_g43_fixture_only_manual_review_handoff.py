"""XRI-G43 fixture-only manual-review handoff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tools.registry.xri_g42_fixture_only_validation_execution import (
    FixtureValidationResult,
    validate_fixture_record,
    validate_fixture_records,
)


class FixtureOnlyManualReviewHandoffError(ValueError):
    """Raised when fixture-only manual-review handoff rules fail closed."""


_ID_FIELDS = ("group_key", "display_location", "candidate_identity")
_FORBIDDEN_STATE_FIELDS = {
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
class ManualReviewHandoffRecord:
    group_key: str
    display_location: str
    candidate_identity: str
    ready_for_manual_review: bool
    review_required_reason: str
    normalized_summary: Mapping[str, Any]
    validation_checks: tuple[str, ...]
    raw_fixture_metadata: Mapping[str, Any]


def _clean_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _reject_forbidden_states(mapping: Mapping[str, Any]) -> None:
    for field in _FORBIDDEN_STATE_FIELDS:
        if bool(mapping.get(field)):
            raise FixtureOnlyManualReviewHandoffError("Manual-review handoff cannot carry final-state field: " + field)


def _ensure_validation_result(record: Mapping[str, Any] | FixtureValidationResult) -> FixtureValidationResult:
    if isinstance(record, FixtureValidationResult):
        _reject_forbidden_states(record.normalized)
        return record
    if isinstance(record, Mapping):
        _reject_forbidden_states(record)
        return validate_fixture_record(record)
    raise FixtureOnlyManualReviewHandoffError("Manual-review handoff input must be a mapping or FixtureValidationResult")


def build_manual_review_handoff_record(record: Mapping[str, Any] | FixtureValidationResult) -> ManualReviewHandoffRecord:
    validation = _ensure_validation_result(record)

    missing_identity = [
        field
        for field in _ID_FIELDS
        if not _clean_text(getattr(validation, field))
    ]
    if missing_identity:
        raise FixtureOnlyManualReviewHandoffError("Missing stable identity fields: " + ", ".join(missing_identity))

    normalized = dict(validation.normalized)
    display = normalized.get("display", {})
    if isinstance(display, Mapping) and "review_rank" in display:
        if display.get("review_rank_identity_use") != "forbidden_display_only":
            raise FixtureOnlyManualReviewHandoffError("review_rank must remain display-only")

    summary = {
        "display_location": validation.display_location,
        "source_name": normalized.get("source_name"),
        "event_name": normalized.get("event_name") or normalized.get("title") or normalized.get("name"),
        "start": normalized.get("start") or normalized.get("start_date") or normalized.get("date"),
        "end": normalized.get("end") or normalized.get("end_date"),
    }

    raw_fixture_metadata = dict(normalized.get("display", {}))
    raw_fixture_metadata["fixture_only"] = True

    return ManualReviewHandoffRecord(
        group_key=validation.group_key,
        display_location=validation.display_location,
        candidate_identity=validation.candidate_identity,
        ready_for_manual_review=True,
        review_required_reason="fixture_validated_requires_human_review",
        normalized_summary=summary,
        validation_checks=validation.checks,
        raw_fixture_metadata=raw_fixture_metadata,
    )


def build_manual_review_handoff_records(records: Mapping[str, Any] | FixtureValidationResult | Sequence[Mapping[str, Any] | FixtureValidationResult]) -> list[ManualReviewHandoffRecord]:
    if isinstance(records, (Mapping, FixtureValidationResult)):
        return [build_manual_review_handoff_record(records)]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise FixtureOnlyManualReviewHandoffError("Manual-review handoff input must be one record or a sequence")
    return [build_manual_review_handoff_record(record) for record in records]


def validate_and_build_manual_review_handoff_records(records: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[ManualReviewHandoffRecord]:
    validation_results = validate_fixture_records(records)
    return build_manual_review_handoff_records(validation_results)
