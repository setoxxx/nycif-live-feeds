#!/usr/bin/env python3
"""Shared schema_version 1.0 projection helpers for NYCIF consumer feeds."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
CATEGORY_VERSION = "categories-v01"
DEFAULT_TIMEZONE = "America/New_York"
NYC = {
    "min_lat": 40.4774,
    "max_lat": 40.9176,
    "min_lng": -74.2591,
    "max_lng": -73.7004,
}

VALID_CATEGORIES = {
    "sports",
    "fitness",
    "parks",
    "arts",
    "market",
    "civic",
    "government",
    "education",
    "family",
    "services",
    "environment",
    "volunteer",
    "jobs",
    "housing",
    "general",
}

CATEGORY_ALIASES = {
    "sports": "sports",
    "fitness": "fitness",
    "fitness and wellness": "fitness",
    "parks": "parks",
    "parks and recreation": "parks",
    "parks & recreation": "parks",
    "arts": "arts",
    "arts and culture": "arts",
    "market": "market",
    "markets and fairs": "market",
    "parade": "civic",
    "civic": "civic",
    "civic and neighborhood": "civic",
    "government": "government",
    "government and hearings": "government",
    "education": "education",
    "education and training": "education",
    "family": "family",
    "kids and family": "family",
    "services": "services",
    "benefits and services": "services",
    "environment": "environment",
    "volunteer": "volunteer",
    "jobs": "jobs",
    "jobs and careers": "jobs",
    "housing": "housing",
    "housing and tenant assistance": "housing",
    "housing and tenant help": "housing",
    "general": "general",
}

BOROUGH_MAP = {
    "mn": "Manhattan",
    "manhattan": "Manhattan",
    "bk": "Brooklyn",
    "brooklyn": "Brooklyn",
    "qn": "Queens",
    "q": "Queens",
    "queens": "Queens",
    "bx": "Bronx",
    "bronx": "Bronx",
    "si": "Staten Island",
    "staten island": "Staten Island",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def borough_label(value: Any) -> str | None:
    raw = value[0] if isinstance(value, list) and value else value
    key = norm_text(raw)
    if key in BOROUGH_MAP:
        return BOROUGH_MAP[key]
    text = str(raw or "").strip()
    return text or None


def valid_nyc_coords(lat: Any, lng: Any) -> tuple[float | None, float | None, bool]:
    if lat is None or lng is None or lat == "" or lng == "":
        return None, None, False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None, None, False
    if lat_f == 0.0 and lng_f == 0.0:
        return None, None, False
    ok = (
        NYC["min_lat"] <= lat_f <= NYC["max_lat"]
        and NYC["min_lng"] <= lng_f <= NYC["max_lng"]
    )
    if not ok:
        return None, None, False
    return lat_f, lng_f, True


def extract_events(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [row for row in events if isinstance(row, dict)]
    return []


def preserve_date(row: dict[str, Any]) -> str | None:
    direct = str(row.get("date") or "").strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", direct):
        return direct
    start = str(row.get("start_date_time") or row.get("start") or "").strip()
    # Prefer calendar date prefix without timezone conversion.
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", start)
    if m:
        return m.group(1)
    return None


def raw_categories(row: dict[str, Any]) -> list[str]:
    cats = row.get("categories")
    if isinstance(cats, list):
        return [str(c) for c in cats if str(c).strip()]
    if isinstance(cats, str) and cats.strip():
        return [cats.strip()]
    if row.get("category") not in (None, ""):
        return [str(row.get("category"))]
    return []


def infer_category(row: dict[str, Any], *, prefer_direct: bool) -> tuple[str, str]:
    direct = CATEGORY_ALIASES.get(norm_text(row.get("category")))
    if prefer_direct and direct:
        return direct, "backend_normalized_category"

    joined = " ".join(raw_categories(row))
    text = norm_text(
        " ".join(
            str(v)
            for v in (
                row.get("category"),
                joined,
                row.get("title"),
                row.get("name"),
                row.get("event_type"),
                row.get("type"),
                row.get("event_agency"),
                row.get("location"),
                row.get("display_location"),
            )
            if v
        )
    )

    # Sports before fitness so competitive athletics stay sports.
    rules = [
        ("jobs", r"job fair|career fair|employment|workforce|hiring", "keyword_jobs"),
        (
            "housing",
            r"tenant|housing|property owner|landlord|homeowner|rent assistance|housing ambassador",
            "keyword_housing",
        ),
        (
            "government",
            r"hearing|public meeting|community board|city government|government office|council meeting",
            "keyword_government",
        ),
        (
            "services",
            r"benefit|resource fair|outreach|clinic|health screening|social service|food assistance|legal help",
            "keyword_services",
        ),
        (
            "education",
            r"education|training|class|workshop|lecture|literacy|school program",
            "keyword_education",
        ),
        (
            "family",
            r"kids and family|kids|children|family|youth program|storytime",
            "keyword_family",
        ),
        ("volunteer", r"volunteer|it's my park|stewardship|service project", "keyword_volunteer"),
        (
            "environment",
            r"environment|ecology|climate|cleanup|compost|recycling|conservation|gardening|nature walk",
            "keyword_environment",
        ),
        (
            "sports",
            r"sport - youth|sport - adult|athletic|softball|baseball|basketball|soccer|football|hockey|tennis|lacrosse|cricket|volleyball|kickball|rugby|marathon|5k|race|criterium|world cup|fifa|fan zone",
            "keyword_sports",
        ),
        (
            "fitness",
            r"yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|barre|spinning|tai chi|qigong|wellness|stretching|shape up nyc|lap swim",
            "keyword_fitness",
        ),
        (
            "arts",
            r"cultural|music|concert|arts?|dance|theater|theatre|film|performance|exhibit|museum|summerstage",
            "keyword_arts",
        ),
        (
            "market",
            r"market|greenmarket|farmers market|vendor|fair|feast|food festival|pop[- ]?up|merchandise",
            "keyword_market",
        ),
        (
            "civic",
            r"parade|march|rally|vigil|ceremony|memorial|street and neighborhood|block party|open street|civic|community event|street event",
            "keyword_civic",
        ),
        (
            "parks",
            r"parks? & recreation|park|playground|pool|recreation|garden|beach",
            "keyword_parks",
        ),
    ]
    for slug, pattern, reason in rules:
        if re.search(pattern, text):
            return slug, reason
    if direct:
        return direct, "aliased_category"
    return "general", "fallback_general"


def _base_stable_id(row: dict[str, Any], *, data_layer: str, index: int) -> str:
    if row.get("id"):
        base = str(row["id"])
        if data_layer == "review_supplemental" and not base.startswith("review_supplemental:"):
            return f"review_supplemental:{base}"
        return base
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = nested.get("dataset") or row.get("source_dataset") or "unknown"
    source_event_id = nested.get("source_event_id") or row.get("source_event_id") or index
    if data_layer == "review_supplemental":
        return f"review_supplemental:{dataset}:{source_event_id}"
    return f"{dataset}:{source_event_id}"


# Occurrence counters keep multi-day permit expansions unique and stable by input order.
_STABLE_ID_SEEN: dict[str, int] = {}


def reset_stable_id_registry() -> None:
    _STABLE_ID_SEEN.clear()


def stable_id(row: dict[str, Any], *, data_layer: str, index: int) -> str:
    """Return a stable unique id.

    Permit feeds expand one source_event_id across many calendar dates while
    reusing the same upstream id. Append `@YYYY-MM-DD` when a valid date exists.
    If that is still a collision within the current projection run, append `#n`.
    """
    base = _base_stable_id(row, data_layer=data_layer, index=index)
    event_day = preserve_date(row)
    candidate = f"{base}@{event_day}" if event_day else base
    seen = _STABLE_ID_SEEN.get(candidate, 0)
    _STABLE_ID_SEEN[candidate] = seen + 1
    if seen == 0:
        return candidate
    return f"{candidate}#{seen + 1}"


def project_event(
    row: dict[str, Any],
    *,
    index: int,
    data_layer: str,
    production_feed: bool,
    major_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prefer_direct = data_layer == "approved_staged"
    category, classification_reason = infer_category(row, prefer_direct=prefer_direct)
    raw_cats = raw_categories(row)
    raw_category = raw_cats[0] if raw_cats else (str(row.get("category")) if row.get("category") else None)

    if data_layer == "review_supplemental":
        lat, lng, map_ready = valid_nyc_coords(
            row.get("latitude") if row.get("latitude") is not None else (
                row.get("lat") if row.get("lat") is not None else row.get("proposed_lat")
            ),
            row.get("longitude") if row.get("longitude") is not None else (
                row.get("lng") if row.get("lng") is not None else row.get("proposed_lng")
            ),
        )
    else:
        lat, lng, map_ready = valid_nyc_coords(
            row.get("latitude") if row.get("latitude") is not None else row.get("lat"),
            row.get("longitude") if row.get("longitude") is not None else row.get("lng"),
        )

    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    source_dataset = nested.get("dataset", row.get("source_dataset"))
    source_event_id = nested.get("source_event_id", row.get("source_event_id"))
    event_id = stable_id(row, data_layer=data_layer, index=index)
    event_date = preserve_date(row)

    major_meta = major_meta or {}
    is_major = bool(major_meta.get("is_major"))
    significance = "major" if is_major else None

    if data_layer == "review_supplemental":
        production_feed = False
        promotion_allowed = False
        manual_review_status = row.get("manual_review_status") or "pending"
        location_cache_modified = bool(row.get("location_cache_modified", False))
        public_map_modified = bool(row.get("public_map_modified", False))
        staged_feed_modified = bool(row.get("staged_feed_modified", False))
        # Review layer is never major/production.
        is_major = False
        significance = None
    else:
        promotion_allowed = None
        manual_review_status = None
        location_cache_modified = False
        public_map_modified = False
        staged_feed_modified = False

    return {
        "id": event_id,
        "title": str(row.get("title") or row.get("name") or row.get("search_label") or "Untitled event"),
        "category": category,
        "start_date_time": row.get("start_date_time") or row.get("start") or None,
        "end_date_time": row.get("end_date_time") or row.get("end") or None,
        "timezone": str(row.get("timezone") or DEFAULT_TIMEZONE),
        "borough": borough_label(row.get("borough") or row.get("event_borough")),
        "location": str(
            row.get("location")
            or row.get("display_location")
            or row.get("address")
            or ""
        )
        or None,
        "latitude": lat,
        "longitude": lng,
        "significance": significance,
        "source": {
            "dataset": str(source_dataset) if source_dataset is not None else None,
            "source_event_id": str(source_event_id) if source_event_id is not None else None,
        },
        "nycif": {
            "data_layer": data_layer,
            "coordinate_status": "map_ready" if map_ready else "list_only",
            "production_feed": bool(production_feed),
            "promotion_allowed": promotion_allowed,
            "manual_review_status": manual_review_status,
            "location_cache_modified": location_cache_modified,
            "public_map_modified": public_map_modified,
            "staged_feed_modified": staged_feed_modified,
            "raw_category": raw_category,
            "raw_categories": raw_cats,
            "category_version": CATEGORY_VERSION,
            "classification_reason": classification_reason,
            "event_date": event_date,
            "event_type": row.get("event_type") or row.get("type"),
            "event_agency": row.get("event_agency"),
            "is_major": is_major,
            "major_score": major_meta.get("major_score"),
            "major_reason": major_meta.get("major_reason"),
            "photo_pick": bool(major_meta.get("photo_pick", row.get("photo_pick"))),
            "field_default": bool(major_meta.get("field_default", row.get("field_default"))),
            "crowd_level": major_meta.get("crowd_level", row.get("crowd_level")),
            "priority_score": major_meta.get("priority_score", row.get("priority_score")),
            "expected_crowd_score": major_meta.get(
                "expected_crowd_score", row.get("expected_crowd_score")
            ),
            "assignment_feed": major_meta.get("assignment_feed", row.get("assignment_feed")),
            "verification_status": major_meta.get(
                "verification_status", row.get("verification_status")
            ),
            "selection_rules": major_meta.get("selection_rules") or [],
        },
    }


def envelope(
    events: list[dict[str, Any]],
    *,
    generated_at_utc: str,
    next_cursor: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc,
        "total": len(events),
        "next_cursor": next_cursor,
        "events": events,
    }


def event_date_key(event: dict[str, Any]) -> str | None:
    nycif = event.get("nycif") or {}
    direct = nycif.get("event_date")
    if isinstance(direct, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", direct):
        return direct
    start = str(event.get("start_date_time") or "")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", start)
    return m.group(1) if m else None


def today_nyc_approx() -> date:
    # Consumer feeds are NYC-local; CI hosts are usually UTC. Use America/New_York when available.
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    except Exception:
        return date.today()
