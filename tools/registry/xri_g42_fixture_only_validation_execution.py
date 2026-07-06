"""XRI-G42 fixture-only validation execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tools.registry.xri_g41_fixture_only_parser_normalizer import (
    ParsedFixtureRecord,
    parse_normalize_fixture_record,
    parse_normalize_fixture_records,
)


class FixtureOnlyValidationExecutionError(ValueError):
    """Raised when fixture-only validation rules fail closed."""


_ID_FIELDS = ("group_key", "display_location", "candidate_identity")
_REQUIRED_NORMALIZED_FIELDS = ("display_location",)


@dataclass(frozen=True)
class FixtureValidationResult:
    group_key: str
    display_location: str
    candidate_identity: str
    valid: bool
    checks: tuple[str, ...]
    normalized: Mapping[str, Any]


def _clean_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _ensure_parsed(record: Mapping[str, Any] | ParsedFixtureRecord) -> ParsedFixtureRecord:
    if isinstance(record, ParsedFixtureRecord):
        return record
    if isinstance(record, Mapping):
        return parse_normalize_fixture_record(record)
    raise FixtureOnlyValidationExecutionError("Fixture validation input must be a mapping or ParsedFixtureRecord")


def validate_fixture_record(record: Mapping[str, Any] | ParsedFixtureRecord) -> FixtureValidationResult:
    parsed = _ensure_parsed(record)

    missing_identity = [
        field
        for field in _ID_FIELDS
        if not _clean_text(getattr(parsed, field))
    ]
    if missing_identity:
        raise FixtureOnlyValidationExecutionError("Missing stable identity fields: " + ", ".join(missing_identity))

    normalized = dict(parsed.normalized)
    missing_normalized = [field for field in _REQUIRED_NORMALIZED_FIELDS if not _clean_text(normalized.get(field, ""))]
    if missing_normalized:
        raise FixtureOnlyValidationExecutionError("Missing normalized fields: " + ", ".join(missing_normalized))

    display = normalized.get("display", {})
    if isinstance(display, Mapping) and "review_rank" in display:
        if display.get("review_rank_identity_use") != "forbidden_display_only":
            raise FixtureOnlyValidationExecutionError("review_rank must be display-only")

    checks = (
        "stable_identity_present",
        "normalized_shape_valid",
        "review_rank_display_only_if_present",
        "deterministic_fixture_only_validation",
    )

    return FixtureValidationResult(
        group_key=parsed.group_key,
        display_location=parsed.display_location,
        candidate_identity=parsed.candidate_identity,
        valid=True,
        checks=checks,
        normalized=normalized,
    )


def validate_fixture_records(records: Mapping[str, Any] | ParsedFixtureRecord | Sequence[Mapping[str, Any] | ParsedFixtureRecord]) -> list[FixtureValidationResult]:
    if isinstance(records, (Mapping, ParsedFixtureRecord)):
        return [validate_fixture_record(records)]
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise FixtureOnlyValidationExecutionError("Fixture validation input must be one record or a sequence")

    parsed_records: list[Mapping[str, Any] | ParsedFixtureRecord] = list(records)
    return [validate_fixture_record(record) for record in parsed_records]


def parse_and_validate_fixture_records(records: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[FixtureValidationResult]:
    parsed = parse_normalize_fixture_records(records)
    return validate_fixture_records(parsed)
