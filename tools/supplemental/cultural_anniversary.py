"""Detect cultural anniversary signals in supplemental event titles."""

from __future__ import annotations

import re
from typing import Any

STORY_PLACEHOLDER = (
    "Story pending — add cultural history for this recurring event so facts "
    "return each year when it appears on the calendar."
)

PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+annual\b", re.IGNORECASE), "ordinal_annual"),
    (re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+year\b", re.IGNORECASE), "ordinal_year"),
    (re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+anniversary\b", re.IGNORECASE), "ordinal_anniversary"),
    (re.compile(r"\bannual\b", re.IGNORECASE), "annual_unnumbered"),
)


def detect_anniversary(title: str) -> dict[str, Any] | None:
    text = str(title or "").strip()
    if not text:
        return None
    for pattern, detection_pattern in PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        anniversary_number = None
        if match.lastindex and match.group(1):
            try:
                anniversary_number = int(match.group(1))
            except ValueError:
                anniversary_number = None
        if anniversary_number is not None and not (1 <= anniversary_number <= 300):
            continue
        return {
            "cultural_anniversary": True,
            "anniversary_number": anniversary_number,
            "edition_year": None,
            "detection_pattern": detection_pattern,
            "story_placeholder": STORY_PLACEHOLDER,
        }
    return None


def anniversary_row_from_event(row: dict[str, Any]) -> dict[str, Any] | None:
    detected = detect_anniversary(str(row.get("title") or ""))
    if not detected:
        return None
    overlap_key = row.get("overlap_key") or row.get("id")
    if not overlap_key:
        return None
    return {
        "overlap_key": overlap_key,
        "title": row.get("title") or "",
        "date": row.get("date") or "",
        "borough": row.get("borough") or "",
        "display_location": row.get("display_location") or row.get("displayLocation") or "",
        **detected,
        "manual_review_status": "pending",
        "manual_review_notes": "",
        "manual_reviewer": None,
        "manual_reviewed_at_utc": None,
        "approval_decision_reason": None,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "production_feed": False,
    }
