#!/usr/bin/env python3
"""Occurrence-identity helpers for Enigma discovery intake.

These helpers keep source-level identity separate from dated occurrence identity.
Recurring event feeds must use occurrence keys for representation checks so a
single source ID cannot suppress another valid date.
"""

from __future__ import annotations

import re
from typing import Any

SourceKey = tuple[str, str]
OccurrenceKey = tuple[str, str, str]


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value).strip())
    return match.group(1) if match else None


def source_key(row: dict[str, Any]) -> SourceKey:
    dataset = str(
        row.get("source_dataset")
        or row.get("dataset")
        or (row.get("source") or {}).get("dataset")
        or "nyc-open-data"
    ).strip()
    source_event_id = str(
        row.get("source_event_id")
        or row.get("event_id")
        or row.get("id")
        or (row.get("source") or {}).get("source_event_id")
        or "missing"
    ).strip()
    return dataset, source_event_id


def occurrence_date(row: dict[str, Any]) -> str | None:
    for key in (
        "event_date",
        "date",
        "start_date",
        "start_date_time",
        "start",
        "event_start_date",
    ):
        day = normalize_date(row.get(key))
        if day:
            return day
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return normalize_date(nycif.get("event_date"))


def occurrence_key(row: dict[str, Any]) -> OccurrenceKey:
    dataset, source_event_id = source_key(row)
    return dataset, source_event_id, occurrence_date(row) or "undated"


def source_key_set(rows: list[dict[str, Any]]) -> set[SourceKey]:
    return {source_key(row) for row in rows}


def occurrence_key_set(rows: list[dict[str, Any]]) -> set[OccurrenceKey]:
    return {occurrence_key(row) for row in rows}


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
    """Classify a raw Open Data row under source-level or occurrence-level matching."""
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
