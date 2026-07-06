"""XRI-G41 fixture-only parser-normalizer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence


class FixtureOnlyParserNormalizerError(ValueError):
    """Raised when fixture-only rules fail closed."""


_BLOCKED_FIELDS = {
    "live_url",
    "source_url",
    "api_url",
    "soda_endpoint",
    "nyc_open_data_endpoint",
    "requires_geocoding",
    "registry_write",
    "registry_import",
    "approval",
    "promotion",
    "publishing",
    "public_map_runtime",
    "public_map_output",
    "wordpress_output",
    "scheduled_workflow",
    "location_cache_access",
    "production_target",
}

_ID_FIELDS = ("group_key", "display_location", "candidate_identity")
_DATE_FIELDS = ("date", "start", "end", "start_date", "end_date", "start_time", "end_time")
_TEXT_FIELDS = ("source_name", "source_type", "event_name", "title", "name")


@dataclass(frozen=True)
class ParsedFixtureRecord:
    group_key: str
    display_location: str
    candidate_identity: str
    normalized: Mapping[str, Any]
    raw: Mapping[str, Any]


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    return bool(value)


def _clean_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _clean_datetime(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return text
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        return text


def _fail_if_blocked(payload: Mapping[str, Any]) -> None:
    blocked = sorted(field for field in _BLOCKED_FIELDS if _truthy(payload.get(field)))
    if blocked:
        raise FixtureOnlyParserNormalizerError("Blocked fixture fields: " + ", ".join(blocked))
    for value in payload.values():
        if isinstance(value, str):
            lowered = value.lower()
            if "://" in lowered or "socrata" in lowered or "open data" in lowered or "/resource/" in lowered:
                raise FixtureOnlyParserNormalizerError("Blocked external source target")


def parse_normalize_fixture_record(payload: Mapping[str, Any]) -> ParsedFixtureRecord:
    if not isinstance(payload, Mapping):
        raise FixtureOnlyParserNormalizerError("Fixture payload must be a mapping")

    _fail_if_blocked(payload)

    missing = [field for field in _ID_FIELDS if not _clean_text(payload.get(field, ""))]
    if missing:
        raise FixtureOnlyParserNormalizerError("Missing stable identity fields: " + ", ".join(missing))

    normalized: dict[str, Any] = {
        "display_location": _clean_text(payload["display_location"]),
    }
    for field in _TEXT_FIELDS:
        if field in payload:
            normalized[field] = _clean_text(payload[field])
    for field in _DATE_FIELDS:
        if field in payload:
            normalized[field] = _clean_datetime(payload[field])

    display = {
        key: payload[key]
        for key in sorted(payload)
        if key not in _ID_FIELDS and key not in _BLOCKED_FIELDS and key not in normalized
    }
    if "review_rank" in payload:
        display["review_rank"] = payload["review_rank"]
        display["review_rank_identity_use"] = "forbidden_display_only"
    normalized["display"] = display

    return ParsedFixtureRecord(
        group_key=_clean_text(payload["group_key"]),
        display_location=_clean_text(payload["display_location"]),
        candidate_identity=_clean_text(payload["candidate_identity"]),
        normalized=normalized,
        raw=dict(payload),
    )


def parse_normalize_fixture_records(payloads: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[ParsedFixtureRecord]:
    if isinstance(payloads, Mapping):
        return [parse_normalize_fixture_record(payloads)]
    if not isinstance(payloads, Sequence) or isinstance(payloads, (str, bytes)):
        raise FixtureOnlyParserNormalizerError("Fixture input must be one mapping or a sequence of mappings")
    return [parse_normalize_fixture_record(payload) for payload in payloads]
