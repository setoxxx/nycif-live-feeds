"""Canonical dated-occurrence identity for Enigma SHADOW-2.

The same source record on different dates or at different start times must not
collapse into one occurrence. This module performs deterministic normalization
only; it does not mutate source records.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Iterable


_DATE_FIELDS = (
    "event_date",
    "date",
    "start_date",
    "start_date_time",
    "start",
    "event_start_date",
)
_TIME_FIELDS = (
    "start_date_time",
    "start",
    "start_time",
    "event_time",
)
_SOURCE_ID_FIELDS = ("source_event_id", "source_record_id", "source_id", "event_id", "id")


@dataclass(frozen=True, slots=True)
class OccurrenceIdentity:
    """Deterministic identity for one dated source occurrence."""

    source_namespace: str
    source_dataset_id: str
    source_record_id: str
    normalized_date: str
    start_time: str | None = None
    timezone: str | None = None

    def _canonical_payload(self) -> dict[str, str]:
        return {
            "normalized_date": self.normalized_date,
            "source_dataset_id": self.source_dataset_id,
            "source_namespace": self.source_namespace,
            "source_record_id": self.source_record_id,
            "start_time": self.start_time or "",
            "timezone": self.timezone or "",
        }

    def canonical_id(self) -> str:
        """Return a full SHA-256 digest over unambiguous canonical JSON."""

        encoded = json.dumps(
            self._canonical_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def composite_key(self) -> str:
        """Return a human-readable key for logs and repair queues."""

        time_suffix = f"T{self.start_time}" if self.start_time else ""
        zone_suffix = f"[{self.timezone}]" if self.timezone else ""
        return (
            f"{self.source_namespace}:{self.source_dataset_id}:"
            f"{self.source_record_id}@{self.normalized_date}{time_suffix}{zone_suffix}"
        )

    def __str__(self) -> str:
        return self.composite_key()


def _nonempty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_date(raw: Any) -> str | None:
    """Normalize supported date or datetime values to a validated ISO date."""

    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()

    text = str(raw).strip()
    if not text:
        return None

    iso_candidate = text
    if iso_candidate.endswith("Z"):
        iso_candidate = f"{iso_candidate[:-1]}+00:00"
    try:
        if "T" in iso_candidate or " " in iso_candidate:
            return datetime.fromisoformat(iso_candidate).date().isoformat()
        return date.fromisoformat(iso_candidate).isoformat()
    except ValueError:
        pass

    for pattern in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_time(raw: Any) -> str | None:
    """Normalize supported time or datetime values to HH:MM:SS."""

    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.time().replace(tzinfo=None).isoformat(timespec="seconds")
    if isinstance(raw, time):
        return raw.replace(tzinfo=None).isoformat(timespec="seconds")

    text = str(raw).strip()
    if not text:
        return None

    iso_candidate = text
    if iso_candidate.endswith("Z"):
        iso_candidate = f"{iso_candidate[:-1]}+00:00"
    if "T" in iso_candidate or re.match(r"^\d{4}-\d{2}-\d{2}\s", iso_candidate):
        try:
            return datetime.fromisoformat(iso_candidate).time().replace(tzinfo=None).isoformat(timespec="seconds")
        except ValueError:
            return None

    for pattern in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(text, pattern).time().isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def _iter_nested_dicts(record: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield record
    for key in ("source", "nycif", "properties"):
        nested = record.get(key)
        if isinstance(nested, dict):
            yield nested


def extract_source_record_id(record: dict[str, Any]) -> str | None:
    """Extract a nonempty source record identifier without inventing one."""

    for candidate in _iter_nested_dicts(record):
        for key in _SOURCE_ID_FIELDS:
            value = _nonempty_text(candidate.get(key))
            if value:
                return value
    return None


def extract_occurrence_date(record: dict[str, Any]) -> str | None:
    for candidate in _iter_nested_dicts(record):
        for key in _DATE_FIELDS:
            normalized = normalize_date(candidate.get(key))
            if normalized:
                return normalized
    return None


def extract_start_time(record: dict[str, Any]) -> str | None:
    for candidate in _iter_nested_dicts(record):
        for key in _TIME_FIELDS:
            normalized = normalize_time(candidate.get(key))
            if normalized:
                return normalized
    return None


def extract_timezone(record: dict[str, Any]) -> str | None:
    for candidate in _iter_nested_dicts(record):
        for key in ("timezone", "time_zone", "tz"):
            value = _nonempty_text(candidate.get(key))
            if value:
                return value
    return None


def build_occurrence_identity(
    record: dict[str, Any],
    source_namespace: str,
    source_dataset_id: str,
) -> OccurrenceIdentity | None:
    """Build an identity, returning ``None`` when required evidence is absent."""

    namespace = _nonempty_text(source_namespace)
    dataset = _nonempty_text(source_dataset_id)
    source_record_id = extract_source_record_id(record)
    normalized_date = extract_occurrence_date(record)
    if not namespace or not dataset or not source_record_id or not normalized_date:
        return None

    return OccurrenceIdentity(
        source_namespace=namespace,
        source_dataset_id=dataset,
        source_record_id=source_record_id,
        normalized_date=normalized_date,
        start_time=extract_start_time(record),
        timezone=extract_timezone(record),
    )
