#!/usr/bin/env python3
"""Deterministic temporal-quality classification for NYCIF event records.

This module never invents duration, rolls dates forward, or mutates source truth.
It only classifies whether an existing start/end pair is safe for downstream
canonical temporal projection.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

CONTRACT_VERSION = "TemporalQualityV1"

VALID = "valid"
MISSING_END = "missing_end"
NONPOSITIVE_INTERVAL = "nonpositive_interval"
PARSE_ERROR = "parse_error"
MISSING_START = "missing_start"


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def classify_temporal_quality(
    *,
    source_start_raw: Any,
    source_end_raw: Any,
    normalized_start: Any = None,
    normalized_end: Any = None,
) -> dict[str, Any]:
    """Return a non-authoritative TemporalQualityV1 disposition.

    Normalized values, when supplied, are the values evaluated for downstream
    temporal safety. Raw source values are preserved as evidence.
    """
    source_start = _clean(source_start_raw)
    source_end = _clean(source_end_raw)
    start = _clean(normalized_start) or source_start
    end = _clean(normalized_end) or source_end

    result: dict[str, Any] = {
        "temporal_quality_version": CONTRACT_VERSION,
        "source_start_raw": source_start,
        "source_end_raw": source_end,
        "normalized_start": start,
        "normalized_end": end,
        "source_supports_end": source_end is not None,
        "repair_applied": False,
        "repair_rule_version": None,
        "review_required": False,
        "quality_state": VALID,
        "reason_code": "ordered_interval",
        "authority_effect": "none",
    }

    if start is None:
        result.update(
            quality_state=MISSING_START,
            reason_code="start_date_time_missing",
            review_required=True,
        )
        return result

    if end is None:
        result.update(
            quality_state=MISSING_END,
            reason_code=(
                "missing_end_source" if source_end is None else "missing_end_normalizer"
            ),
            review_required=True,
        )
        return result

    try:
        start_dt = _parse(start)
        end_dt = _parse(end)
    except (TypeError, ValueError):
        result.update(
            quality_state=PARSE_ERROR,
            reason_code="temporal_parse_error",
            review_required=True,
        )
        return result

    if start_dt.tzinfo is None and end_dt.tzinfo is not None:
        result.update(
            quality_state=PARSE_ERROR,
            reason_code="mixed_timezone_awareness",
            review_required=True,
        )
        return result
    if start_dt.tzinfo is not None and end_dt.tzinfo is None:
        result.update(
            quality_state=PARSE_ERROR,
            reason_code="mixed_timezone_awareness",
            review_required=True,
        )
        return result

    if end_dt <= start_dt:
        source_reason = "source_invalid_interval"
        if source_start and source_end:
            try:
                source_start_dt = _parse(source_start)
                source_end_dt = _parse(source_end)
                if source_end_dt > source_start_dt:
                    source_reason = "normalizer_interval_defect"
            except (TypeError, ValueError):
                source_reason = "other_temporal_contradiction"
        result.update(
            quality_state=NONPOSITIVE_INTERVAL,
            reason_code=source_reason,
            review_required=True,
        )
        return result

    return result


def is_temporally_projectable(result: dict[str, Any]) -> bool:
    """Only valid ordered intervals may enter Maya temporal buckets."""
    return (
        result.get("temporal_quality_version") == CONTRACT_VERSION
        and result.get("quality_state") == VALID
        and result.get("review_required") is False
        and result.get("repair_applied") is False
    )
