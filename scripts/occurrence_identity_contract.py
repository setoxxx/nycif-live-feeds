#!/usr/bin/env python3
"""Occurrence-identity helpers for Enigma discovery intake.

Source identity and occurrence identity are separate. V2 occurrence identity
uses the exact source occurrence start whenever the source provides it. The
legacy date-key helpers remain temporarily for migration compatibility; new
cross-lane work must use occurrence_key_v2().

Rejection decisions are also occurrence-aware. A legacy rejection is never
silently widened to all recurring occurrences: exact-start evidence defaults to
EXACT_START scope, date-only evidence defaults to DAY scope, and source-wide
suppression requires an explicit SOURCE_ALL_OCCURRENCES scope.
"""

from __future__ import annotations

import re
from typing import Any

SourceKey = tuple[str, str]
OccurrenceKey = tuple[str, str, str]
OccurrenceKeyV2 = tuple[str, str, str]
OccurrenceDayKey = tuple[str, str, str]

REJECTION_SCOPE_EXACT_START = "EXACT_START"
REJECTION_SCOPE_DAY = "DAY"
REJECTION_SCOPE_SOURCE_ALL = "SOURCE_ALL_OCCURRENCES"
VALID_REJECTION_SCOPES = {
    REJECTION_SCOPE_EXACT_START,
    REJECTION_SCOPE_DAY,
    REJECTION_SCOPE_SOURCE_ALL,
}


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value).strip())
    return match.group(1) if match else None


def normalize_occurrence_start(value: Any) -> str | None:
    """Normalize source occurrence start without inventing source precision.

    ISO-like timestamps retain exact start precision. Hour/minute timestamps are
    normalized to ``:00`` seconds so equivalent source encodings compare equal.
    Date-only values remain date-only and are explicitly classified as DAY.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    iso = re.match(
        r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?",
        text,
    )
    if not iso:
        return None
    day, hour, minute, second, zone = iso.groups()
    if hour is None or minute is None:
        return day
    second = second or "00"
    if zone and zone != "Z" and re.fullmatch(r"[+-]\d{4}", zone):
        zone = f"{zone[:3]}:{zone[3:]}"
    return f"{day}T{hour}:{minute}:{second}{zone or ''}"


def source_key(row: dict[str, Any]) -> SourceKey:
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = str(
        row.get("source_dataset")
        or row.get("dataset")
        or source.get("dataset")
        or "nyc-open-data"
    ).strip()
    source_event_id = str(
        row.get("source_event_id")
        or row.get("event_id")
        or row.get("id")
        or source.get("source_event_id")
        or "missing"
    ).strip()
    return dataset, source_event_id


def occurrence_start(row: dict[str, Any]) -> str | None:
    for key in (
        "start_date_time",
        "startDate",
        "start",
        "event_start_date",
        "start_date",
        "event_date",
        "date",
    ):
        value = normalize_occurrence_start(row.get(key))
        if value:
            return value
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    for key in ("event_start", "start_date_time", "event_date"):
        value = normalize_occurrence_start(nycif.get(key))
        if value:
            return value
    return None


def identity_precision(row: dict[str, Any]) -> str:
    start = occurrence_start(row)
    if start is None:
        return "AMBIGUOUS"
    return "EXACT_START" if "T" in start else "DAY"


def occurrence_key_v2(row: dict[str, Any]) -> OccurrenceKeyV2:
    dataset, source_event_id = source_key(row)
    start = occurrence_start(row)
    return dataset, source_event_id, start or "identity_ambiguous"


def occurrence_key_v2_set(rows: list[dict[str, Any]]) -> set[OccurrenceKeyV2]:
    return {occurrence_key_v2(row) for row in rows if identity_precision(row) != "AMBIGUOUS"}


def occurrence_key_v2_is_ambiguous(row: dict[str, Any]) -> bool:
    return identity_precision(row) == "AMBIGUOUS"


def occurrence_date(row: dict[str, Any]) -> str | None:
    start = occurrence_start(row)
    return normalize_date(start)


def occurrence_day_key(row: dict[str, Any]) -> OccurrenceDayKey | None:
    dataset, source_event_id = source_key(row)
    day = occurrence_date(row)
    if not day:
        return None
    return dataset, source_event_id, day


def occurrence_key(row: dict[str, Any]) -> OccurrenceKey:
    """Legacy date-key identity retained only for controlled migration."""
    dataset, source_event_id = source_key(row)
    return dataset, source_event_id, occurrence_date(row) or "undated"


def source_key_set(rows: list[dict[str, Any]]) -> set[SourceKey]:
    return {source_key(row) for row in rows}


def occurrence_key_set(rows: list[dict[str, Any]]) -> set[OccurrenceKey]:
    return {occurrence_key(row) for row in rows}


def rejection_scope(row: dict[str, Any]) -> str | None:
    """Return explicit/narrow rejection scope without widening legacy intent."""
    for field in ("rejection_scope", "decision_scope", "review_scope"):
        explicit = str(row.get(field) or "").strip().upper()
        if explicit in VALID_REJECTION_SCOPES:
            return explicit

    precision = identity_precision(row)
    if precision == "EXACT_START":
        return REJECTION_SCOPE_EXACT_START
    if precision == "DAY":
        return REJECTION_SCOPE_DAY
    return None


def is_rejected_decision(row: dict[str, Any]) -> bool:
    disposition = str(row.get("disposition") or "").lower()
    reason = str(row.get("reason") or row.get("approval_decision_reason") or "").lower()
    manual = str(row.get("manual_review_status") or "").lower()
    return disposition in {"rejected", "drop", "invalid"} or "reject" in reason or manual == "rejected"


def rejection_identity_sets(
    rows: list[dict[str, Any]],
) -> tuple[set[OccurrenceKeyV2], set[OccurrenceDayKey], set[SourceKey]]:
    """Build exact/day/source rejection sets with narrow-by-default semantics."""
    exact: set[OccurrenceKeyV2] = set()
    days: set[OccurrenceDayKey] = set()
    sources: set[SourceKey] = set()
    for row in rows:
        if not is_rejected_decision(row):
            continue
        scope = rejection_scope(row)
        if scope == REJECTION_SCOPE_SOURCE_ALL:
            sources.add(source_key(row))
            continue
        if scope == REJECTION_SCOPE_EXACT_START and identity_precision(row) == "EXACT_START":
            exact.add(occurrence_key_v2(row))
            continue
        if scope == REJECTION_SCOPE_DAY:
            day_key = occurrence_day_key(row)
            if day_key is not None:
                days.add(day_key)
    return exact, days, sources


def rejection_matches(
    row: dict[str, Any],
    *,
    rejected_exact: set[OccurrenceKeyV2],
    rejected_days: set[OccurrenceDayKey],
    rejected_sources: set[SourceKey],
) -> bool:
    """Apply rejection precedence: exact start, day, explicit source-wide."""
    if identity_precision(row) != "AMBIGUOUS" and occurrence_key_v2(row) in rejected_exact:
        return True
    day_key = occurrence_day_key(row)
    if day_key is not None and day_key in rejected_days:
        return True
    return source_key(row) in rejected_sources


def overlaps_date_window(row: dict[str, Any], start: str, end: str) -> bool:
    start_day = occurrence_date(row)
    if not start_day:
        return False
    end_day = normalize_date(row.get("end_date_time") or row.get("end")) or start_day
    return start_day <= end and end_day >= start


def classify_open_data_occurrence(
    row: dict[str, Any],
    *,
    staged_source_keys: set[SourceKey],
    staged_occurrence_keys: set[OccurrenceKey],
    rejected_source_keys: set[SourceKey],
    rejected_occurrence_keys: set[OccurrenceKey],
    season_start: str,
    season_end: str,
    matching_mode: str,
) -> str:
    """Legacy migration classifier for source-level or date-level matching."""
    source = source_key(row)
    occurrence = occurrence_key(row)

    if matching_mode not in {"source_id_only", "dated_occurrence"}:
        raise ValueError(f"unsupported matching_mode: {matching_mode}")

    if matching_mode == "source_id_only" and source in staged_source_keys:
        if occurrence not in staged_occurrence_keys and overlaps_date_window(row, season_start, season_end):
            return "in_window_occurrence_hidden_by_source_id_match"
        return "represented_by_staged_source_id"

    if matching_mode == "dated_occurrence" and occurrence in staged_occurrence_keys:
        return "represented_by_staged_occurrence"

    if occurrence in rejected_occurrence_keys or source in rejected_source_keys:
        return "rejected_with_documented_reason"

    if overlaps_date_window(row, season_start, season_end):
        return "accepted_via_occurrence_keyed_unstaged_intake"

    if occurrence_date(row):
        return "excluded_outside_audited_season_window"
    return "excluded_missing_or_unparseable_event_date"


def source_id_only_matching_allowed_for_recurring_event_feeds() -> bool:
    return False
