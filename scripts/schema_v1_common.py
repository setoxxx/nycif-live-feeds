#!/usr/bin/env python3
"""Shared schema_version 1.0 projection helpers for NYCIF consumer feeds."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
CATEGORY_VERSION = "categories-v01"
DEFAULT_TIMEZONE = "America/New_York"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")

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

# (slug, regex, reason) — sports before fitness; civic marches before vague walks.
KEYWORD_CATEGORY_RULES: list[tuple[str, str, str]] = [
    ("jobs", r"job fair|career fair|employment|workforce|hiring", "keyword_jobs"),
    (
        "housing",
        r"\btenant\b|housing ambassador|rent assistance|landlord|homeowner|property owner clinic",
        "keyword_housing",
    ),
    (
        "government",
        r"hearing|public meeting|community board|city government|government office|council meeting",
        "keyword_government",
    ),
    (
        "sports",
        r"sport - youth|sport - adult|athletic race|triathlon|duathlon|softball|baseball|basketball|soccer|football|hockey|tennis|lacrosse|cricket|volleyball|kickball|rugby|marathon|\b5k\b|\b10k\b|criterium|world cup|fifa|fan zone",
        "keyword_sports",
    ),
    (
        "fitness",
        r"yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|barre|spinning|tai chi|qigong|wellness|stretching|shape up nyc|lap swim",
        "keyword_fitness",
    ),
    (
        "civic",
        r"\bparade\b|\bmarch\b|\brally\b|\bvigil\b|\bceremony\b|\bprocession\b|baraat|street and neighborhood|block party|open street|\bcivic\b|unity walk",
        "keyword_civic",
    ),
    (
        "services",
        r"benefit|resource fair|outreach|clinic|health screening|social service|food assistance|legal help",
        "keyword_services",
    ),
    (
        "education",
        r"education|training|workshop|lecture|literacy|school program|\bclass\b",
        "keyword_education",
    ),
    (
        "family",
        r"kids and family|\bkids\b|children|youth program|storytime",
        "keyword_family",
    ),
    ("volunteer", r"volunteer|it's my park|stewardship|service project", "keyword_volunteer"),
    (
        "environment",
        r"environment|ecology|climate|cleanup|compost|recycling|conservation|gardening|nature walk",
        "keyword_environment",
    ),
    (
        "arts",
        r"cultural|music|concert|\barts?\b|dance|theater|theatre|film|performance|exhibit|museum|summerstage|feast",
        "keyword_arts",
    ),
    (
        "market",
        r"market|greenmarket|farmers market|vendor|fair|food festival|pop[- ]?up|merchandise",
        "keyword_market",
    ),
    (
        "parks",
        r"parks? & recreation|\bpark\b|playground|pool|recreation|garden|beach",
        "keyword_parks",
    ),
]

EVENT_TYPE_CATEGORY = {
    "parade": ("civic", "event_type_parade"),
    "athletic race / tour": ("sports", "event_type_athletic_race"),
    "farmers market": ("market", "event_type_farmers_market"),
    "block party": ("civic", "event_type_block_party"),
    "street event": ("civic", "event_type_street_event"),
    "religious event": ("civic", "event_type_religious_event"),
    "sport - youth": ("sports", "event_type_sport_youth"),
    "sport - adult": ("sports", "event_type_sport_adult"),
}

_STABLE_ID_SEEN: dict[str, int] = {}


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


def is_zero_coord_pair(lat_f: float, lng_f: float) -> bool:
    return abs(lat_f) < 1e-12 and abs(lng_f) < 1e-12


def valid_nyc_coords(lat: Any, lng: Any) -> tuple[float | None, float | None, bool]:
    if lat is None or lng is None or lat == "" or lng == "":
        return None, None, False
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None, None, False
    if is_zero_coord_pair(lat_f, lng_f):
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
    if ISO_DATE_RE.fullmatch(direct):
        return direct
    start = str(row.get("start_date_time") or row.get("start") or "").strip()
    match = ISO_DATE_PREFIX_RE.match(start)
    if match:
        return match.group(1)
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


def classification_text(row: dict[str, Any]) -> str:
    return norm_text(
        " ".join(
            str(v)
            for v in (
                row.get("category"),
                " ".join(raw_categories(row)),
                row.get("title"),
                row.get("name"),
                row.get("event_type"),
                row.get("type"),
                row.get("event_agency"),
                row.get("street_closure_type"),
                row.get("location"),
                row.get("display_location"),
            )
            if v
        )
    )


def refine_from_event_type(row: dict[str, Any]) -> tuple[str, str] | None:
    event_type = norm_text(row.get("event_type") or row.get("type"))
    mapped = EVENT_TYPE_CATEGORY.get(event_type)
    return mapped


def refine_from_keywords(text: str) -> tuple[str, str] | None:
    for slug, pattern, reason in KEYWORD_CATEGORY_RULES:
        if re.search(pattern, text):
            return slug, reason
    return None


def infer_category(row: dict[str, Any], *, prefer_direct: bool) -> tuple[str, str]:
    """Prefer specific backend categories; refine `general` with deterministic rules."""
    direct = CATEGORY_ALIASES.get(norm_text(row.get("category")))
    if prefer_direct and direct and direct != "general":
        return direct, "backend_normalized_category"

    by_type = refine_from_event_type(row)
    if by_type:
        return by_type

    by_keyword = refine_from_keywords(classification_text(row))
    if by_keyword:
        return by_keyword

    if direct and direct != "general":
        return direct, "aliased_category"
    return "general", "fallback_general_no_documented_rule"


def reset_stable_id_registry() -> None:
    _STABLE_ID_SEEN.clear()


def _review_supplemental_id_prefix(base: str) -> str:
    if base.startswith("review_supplemental:"):
        return base
    return f"review_supplemental:{base}"


def _base_stable_id_from_row_id(row: dict[str, Any], *, data_layer: str) -> str:
    base = str(row["id"])
    if data_layer == "review_supplemental":
        return _review_supplemental_id_prefix(base)
    return base


def _base_stable_id_from_source(row: dict[str, Any], *, data_layer: str, index: int) -> str:
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = nested.get("dataset") or row.get("source_dataset") or "unknown"
    source_event_id = nested.get("source_event_id") or row.get("source_event_id") or index
    base = f"{dataset}:{source_event_id}"
    if data_layer == "review_supplemental":
        return _review_supplemental_id_prefix(base)
    return base


def _base_stable_id(row: dict[str, Any], *, data_layer: str, index: int) -> str:
    if row.get("id"):
        return _base_stable_id_from_row_id(row, data_layer=data_layer)
    return _base_stable_id_from_source(row, data_layer=data_layer, index=index)


def stable_id(row: dict[str, Any], *, data_layer: str, index: int) -> str:
    base = _base_stable_id(row, data_layer=data_layer, index=index)
    event_day = preserve_date(row)
    candidate = f"{base}@{event_day}" if event_day else base
    seen = _STABLE_ID_SEEN.get(candidate, 0)
    _STABLE_ID_SEEN[candidate] = seen + 1
    if seen == 0:
        return candidate
    return f"{candidate}#{seen + 1}"


def _first_coord_pair(row: dict[str, Any], keys_lat: list[str], keys_lng: list[str]):
    lat = next((row.get(k) for k in keys_lat if row.get(k) is not None), None)
    lng = next((row.get(k) for k in keys_lng if row.get(k) is not None), None)
    return valid_nyc_coords(lat, lng)


def resolve_coords(row: dict[str, Any], *, data_layer: str):
    if data_layer == "review_supplemental":
        return _first_coord_pair(
            row,
            ["latitude", "lat", "proposed_lat"],
            ["longitude", "lng", "proposed_lng"],
        )
    return _first_coord_pair(row, ["latitude", "lat"], ["longitude", "lng"])


def resolve_source(row: dict[str, Any]) -> tuple[Any, Any]:
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    return nested.get("dataset", row.get("source_dataset")), nested.get(
        "source_event_id", row.get("source_event_id")
    )


def layer_safety_fields(row: dict[str, Any], *, data_layer: str) -> dict[str, Any]:
    if data_layer == "review_supplemental":
        return {
            "production_feed": False,
            "promotion_allowed": False,
            "manual_review_status": row.get("manual_review_status") or "pending",
            "location_cache_modified": bool(row.get("location_cache_modified", False)),
            "public_map_modified": bool(row.get("public_map_modified", False)),
            "staged_feed_modified": bool(row.get("staged_feed_modified", False)),
        }
    return {
        "production_feed": True,
        "promotion_allowed": None,
        "manual_review_status": None,
        "location_cache_modified": False,
        "public_map_modified": False,
        "staged_feed_modified": False,
    }


def resolve_title(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("name") or row.get("search_label") or "Untitled event")


def resolve_location(row: dict[str, Any]) -> str | None:
    text = str(row.get("location") or row.get("display_location") or row.get("address") or "")
    return text or None


def resolve_major_flags(
    data_layer: str,
    major_meta: dict[str, Any] | None,
) -> tuple[bool, str | None, bool]:
    meta = major_meta or {}
    is_major = bool(meta.get("is_major"))
    significance = "major" if is_major else None
    production_feed = True
    if data_layer == "review_supplemental":
        is_major = False
        significance = None
        production_feed = False
    return is_major, significance, production_feed


def build_source_block(source_dataset: Any, source_event_id: Any) -> dict[str, Any]:
    return {
        "dataset": str(source_dataset) if source_dataset is not None else None,
        "source_event_id": str(source_event_id) if source_event_id is not None else None,
    }


def build_nycif_block(
    row: dict[str, Any],
    *,
    data_layer: str,
    classification_reason: str,
    raw_cats: list[str],
    raw_category: str | None,
    map_ready: bool,
    event_date: str | None,
    safety: dict[str, Any],
    production_feed: bool,
    is_major: bool,
    major_meta: dict[str, Any],
) -> dict[str, Any]:
    return {
        "data_layer": data_layer,
        "coordinate_status": "map_ready" if map_ready else "list_only",
        "production_feed": bool(production_feed),
        "promotion_allowed": safety["promotion_allowed"],
        "manual_review_status": safety["manual_review_status"],
        "location_cache_modified": safety["location_cache_modified"],
        "public_map_modified": safety["public_map_modified"],
        "staged_feed_modified": safety["staged_feed_modified"],
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
        "major_source": major_meta.get("major_source"),
    }


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
    raw_category = raw_cats[0] if raw_cats else None
    lat, lng, map_ready = resolve_coords(row, data_layer=data_layer)
    source_dataset, source_event_id = resolve_source(row)
    event_id = stable_id(row, data_layer=data_layer, index=index)
    event_date = preserve_date(row)
    meta = major_meta or {}
    is_major, significance, production_feed = resolve_major_flags(data_layer, meta)
    safety = layer_safety_fields(row, data_layer=data_layer)

    return {
        "id": event_id,
        "title": resolve_title(row),
        "category": category,
        "start_date_time": row.get("start_date_time") or row.get("start") or None,
        "end_date_time": row.get("end_date_time") or row.get("end") or None,
        "timezone": str(row.get("timezone") or DEFAULT_TIMEZONE),
        "borough": borough_label(row.get("borough") or row.get("event_borough")),
        "location": resolve_location(row),
        "latitude": lat,
        "longitude": lng,
        "significance": significance,
        "source": build_source_block(source_dataset, source_event_id),
        "nycif": build_nycif_block(
            row,
            data_layer=data_layer,
            classification_reason=classification_reason,
            raw_cats=raw_cats,
            raw_category=raw_category,
            map_ready=map_ready,
            event_date=event_date,
            safety=safety,
            production_feed=production_feed,
            is_major=is_major,
            major_meta=meta,
        ),
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
    if isinstance(direct, str) and ISO_DATE_RE.fullmatch(direct):
        return direct
    start = str(event.get("start_date_time") or "")
    match = ISO_DATE_PREFIX_RE.match(start)
    return match.group(1) if match else None


def today_nyc_approx() -> date:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    except Exception:
        return date.today()


def safe_write_json(path, payload, *, root) -> None:
    """Write JSON only when the resolved path stays under repository root."""
    from pathlib import Path
    import json

    root_path = Path(root).resolve()
    out_path = Path(path).resolve()
    if not out_path.is_relative_to(root_path):
        raise ValueError(f"refusing to write outside repository root: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
