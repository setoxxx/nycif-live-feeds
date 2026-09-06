"""Normalize public-help rows into culture_calendar_occurrence_v1 staging JSON.

Never invents events, times, or map pins. Publication stays off.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.culture.common import (
    CALENDAR_KINDS,
    nyc_point,
    safety_envelope,
    stable_id,
)

OCCURRENCE_KINDS = (
    "blood_drive",
    "mobile_clinic",
    "job_fair",
    "workshop",
    "pet_mobile",
    "resource_van",
    "worship_service",
    "cultural_festival",
    "aspca_van",
    "community_clinic",
    "other",
)

# occurrence_kind → calendar_kind stored on the SQL row
KIND_TO_CALENDAR = {
    "blood_drive": "blood_drive",
    "mobile_clinic": "mobile_clinic",
    "job_fair": "job_fair",
    "workshop": "workshop",
    "pet_mobile": "pet_mobile",
    "resource_van": "resource_van",
    "worship_service": "worship_service",
    "cultural_festival": "cultural_festival",
    "aspca_van": "pet_mobile",
    "community_clinic": "mobile_clinic",
    "other": "other",
}

HELP_CHIPS = (
    {
        "id": "blood",
        "label": "Blood",
        "emoji": "🩸",
        "occurrence_kinds": ("blood_drive",),
    },
    {
        "id": "mobile_clinic",
        "label": "Mobile clinic",
        "emoji": "🏥",
        "occurrence_kinds": ("mobile_clinic", "resource_van", "community_clinic"),
    },
    {
        "id": "jobs",
        "label": "Jobs",
        "emoji": "💼",
        "occurrence_kinds": ("job_fair", "workshop"),
    },
    {
        "id": "college",
        "label": "College",
        "emoji": "🎓",
        "source_families": ("cuny", "college"),
    },
    {
        "id": "pet",
        "label": "Pet care",
        "emoji": "🐾",
        "occurrence_kinds": ("pet_mobile", "aspca_van"),
    },
)

NYC_REGION_HINTS = (
    "new york city",
    "nyc",
    "manhattan",
    "brooklyn",
    "queens",
    "bronx",
    "staten island",
    "long island city",
    "jamaica, ny",
    "flushing",
    "harlem",
)

ISO_DT_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)(?:[+-]\d{2}:\d{2}|Z)?)?"
)


def chip_for(*, occurrence_kind: str, source_family: str | None = None) -> dict[str, str]:
    family = (source_family or "").strip().lower()
    if family in {"cuny", "college"}:
        return {"chip_id": "college", "chip_label": "College", "emoji": "🎓"}
    for chip in HELP_CHIPS:
        kinds = chip.get("occurrence_kinds") or ()
        if occurrence_kind in kinds:
            return {
                "chip_id": str(chip["id"]),
                "chip_label": str(chip["label"]),
                "emoji": str(chip["emoji"]),
            }
    return {"chip_id": "other", "chip_label": "Culture", "emoji": "📅"}


def is_nyc_region(row: dict[str, Any]) -> bool:
    hay = " ".join(
        str(row.get(key) or "")
        for key in (
            "borough",
            "city",
            "region",
            "location",
            "address",
            "display_location",
            "title",
        )
    ).lower()
    if any(hint in hay for hint in NYC_REGION_HINTS):
        return True
    borough = str(row.get("borough") or "").strip().lower()
    return borough in {
        "manhattan",
        "brooklyn",
        "queens",
        "bronx",
        "staten island",
        "citywide",
    }


def parse_start_at(value: Any) -> tuple[str | None, str]:
    """Return (iso_local_or_offset, precision). Never invents a clock."""
    text = str(value or "").strip()
    if not text:
        return None, "missing"
    match = ISO_DT_RE.match(text)
    if not match:
        return None, "unparsed"
    day = match.group(1)
    clock = match.group(2)
    if clock:
        if len(clock) == 5:
            clock = f"{clock}:00"
        suffix = ""
        if text.endswith("Z"):
            suffix = "Z"
        else:
            tz = re.search(r"([+-]\d{2}:\d{2})$", text)
            suffix = tz.group(1) if tz else ""
        return f"{day}T{clock}{suffix}", "explicit_clock"
    return f"{day}T00:00:00", "date_only"


def normalize_calendar_occurrence(
    *,
    occurrence_kind: str,
    title: str,
    source_name: str,
    source_dataset: str,
    source_event_id: str | None = None,
    start_at: Any = None,
    end_at: Any = None,
    borough: str | None = None,
    display_location: str | None = None,
    address: str | None = None,
    lat: Any = None,
    lng: Any = None,
    zip_codes: list[str] | None = None,
    waitlist_gated: bool = False,
    source_family: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build one staging occurrence. Returns None when title or start is missing."""
    kind = (occurrence_kind or "").strip()
    if kind not in OCCURRENCE_KINDS:
        raise ValueError(f"unsupported occurrence_kind {kind!r}")
    name = (title or "").strip()
    if not name:
        return None
    start_iso, start_precision = parse_start_at(start_at)
    if not start_iso:
        return None
    end_iso, _end_precision = parse_start_at(end_at) if end_at else (None, "missing")
    lat_f, lng_f, in_nyc = nyc_point(lat, lng)
    calendar_kind = KIND_TO_CALENDAR[kind]
    if calendar_kind not in CALENDAR_KINDS:
        raise ValueError(f"calendar_kind {calendar_kind!r} not in CALENDAR_KINDS")
    sid = source_event_id or stable_id(source_dataset, name, start_iso, display_location or address)
    chip = chip_for(occurrence_kind=kind, source_family=source_family)
    pin_policy = "list_only"
    if waitlist_gated:
        pin_policy = "zip_area_only"
    row = {
        "occurrence_id": stable_id("culture-cal", source_dataset, sid),
        "occurrence_kind": kind,
        "calendar_kind": calendar_kind,
        "title": name,
        "start_at": start_iso,
        "end_at": end_iso,
        "timezone": "America/New_York",
        "time_precision": start_precision,
        "borough": borough,
        "display_location": display_location or address,
        "address": address,
        "lat": lat_f if in_nyc else None,
        "lng": lng_f if in_nyc else None,
        "map_ready": False,
        "zip_codes": zip_codes or [],
        "waitlist_gated": waitlist_gated,
        "pin_policy": pin_policy,
        "source_name": source_name,
        "source_dataset": source_dataset,
        "source_event_id": sid,
        "source_family": source_family,
        "review_status": "pending",
        "is_sample": False,
        **chip,
        **safety_envelope(),
    }
    if extra:
        row.update(extra)
    return row


def drop_without_when(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("start_at") and row.get("title")]
