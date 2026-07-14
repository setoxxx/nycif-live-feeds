#!/usr/bin/env python3
"""Project staged + supplemental event feeds into schema_version 1.0 envelopes.

Does not modify protected location_cache or staged feed files in place.
Writes separate schema projection artifacts and a validation report.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_TIMEZONE = "America/New_York"
NYC = {
    "min_lat": 40.4774,
    "max_lat": 40.9176,
    "min_lng": -74.2591,
    "max_lng": -73.7004,
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

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGED_PATH = REPO_ROOT / "data" / "nycif_staged_live_events.json"
SUPPLEMENTAL_PATH = REPO_ROOT / "data" / "supplemental_events_staging_feed.json"
OUT_STAGED = REPO_ROOT / "data" / "events_schema_v1_staged.json"
OUT_SUPP = REPO_ROOT / "data" / "events_schema_v1_supplemental_review.json"
OUT_REPORT = REPO_ROOT / "data" / "events_schema_v1_validation_report.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def borough_label(value: Any) -> str | None:
    raw = value[0] if isinstance(value, list) and value else value
    key = norm_text(raw)
    mapping = {
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
    if key in mapping:
        return mapping[key]
    text = str(raw or "").strip()
    return text or None


def valid_nyc_coords(lat: Any, lng: Any) -> tuple[float | None, float | None, bool]:
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None, None, False
    ok = (
        NYC["min_lat"] <= lat_f <= NYC["max_lat"]
        and NYC["min_lng"] <= lng_f <= NYC["max_lng"]
    )
    if not ok:
        return None, None, False
    return lat_f, lng_f, True


def infer_category(row: dict[str, Any], *, prefer_direct: bool) -> str:
    direct = CATEGORY_ALIASES.get(norm_text(row.get("category")))
    if prefer_direct and direct:
        return direct

    categories = row.get("categories")
    if isinstance(categories, list):
        joined = " ".join(str(c) for c in categories)
    else:
        joined = str(categories or "")

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

    if re.search(r"job fair|career fair|employment|workforce|hiring", text):
        return "jobs"
    if re.search(
        r"tenant|housing|property owner|landlord|homeowner|rent assistance|housing ambassador",
        text,
    ):
        return "housing"
    if re.search(
        r"hearing|public meeting|community board|city government|government office|council meeting",
        text,
    ):
        return "government"
    if re.search(
        r"benefit|resource fair|outreach|clinic|health screening|social service|food assistance|legal help",
        text,
    ):
        return "services"
    if re.search(r"education|training|class|workshop|lecture|literacy|school program", text):
        return "education"
    if re.search(r"kids and family|kids|children|family|youth program|storytime", text):
        return "family"
    if re.search(r"volunteer|it's my park|stewardship|service project", text):
        return "volunteer"
    if re.search(
        r"environment|ecology|climate|cleanup|compost|recycling|conservation|gardening|nature walk",
        text,
    ):
        return "environment"
    if re.search(
        r"yoga|zumba|pilates|fitness|workout|aerobics|exercise|calisthenics|boot camp|barre|spinning|tai chi|qigong|wellness|stretching|shape up nyc|lap swim",
        text,
    ):
        return "fitness"
    if re.search(
        r"athletic|softball|baseball|basketball|soccer|football|hockey|tennis|lacrosse|cricket|volleyball|kickball|rugby|marathon|5k|race|sport",
        text,
    ):
        return "sports"
    if re.search(
        r"cultural|music|concert|arts?|dance|theater|theatre|film|performance|exhibit|museum|summerstage",
        text,
    ):
        return "arts"
    if re.search(r"market|greenmarket|vendor|fair|feast|food festival|pop[- ]?up", text):
        return "market"
    if re.search(
        r"parade|march|rally|vigil|ceremony|memorial|street and neighborhood|block party|open street|civic|community event",
        text,
    ):
        return "civic"
    if re.search(r"parks? & recreation|park|playground|pool|recreation|garden|beach", text):
        return "parks"
    return direct or "general"


def extract_events(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [row for row in events if isinstance(row, dict)]
    return []


def project_event(
    row: dict[str, Any],
    *,
    index: int,
    data_layer: str,
    production_feed: bool,
) -> dict[str, Any]:
    prefer_direct = data_layer == "approved_staged"
    category = infer_category(row, prefer_direct=prefer_direct)

    if data_layer == "review_supplemental":
        lat, lng, map_ready = valid_nyc_coords(
            row.get("lat") if row.get("lat") is not None else row.get("proposed_lat"),
            row.get("lng") if row.get("lng") is not None else row.get("proposed_lng"),
        )
        # Prefer explicit latitude/longitude aliases when present.
        if not map_ready:
            lat, lng, map_ready = valid_nyc_coords(
                row.get("latitude") if row.get("latitude") is not None else row.get("proposed_lat"),
                row.get("longitude")
                if row.get("longitude") is not None
                else row.get("proposed_lng"),
            )
    else:
        lat, lng, map_ready = valid_nyc_coords(
            row.get("latitude") if row.get("latitude") is not None else row.get("lat"),
            row.get("longitude") if row.get("longitude") is not None else row.get("lng"),
        )

    source_dataset = row.get("source_dataset")
    source_event_id = row.get("source_event_id")
    nested = row.get("source")
    if isinstance(nested, dict):
        source_dataset = nested.get("dataset", source_dataset)
        source_event_id = nested.get("source_event_id", source_event_id)

    event_id = row.get("id")
    if not event_id:
        event_id = f"{data_layer}:{source_dataset or 'unknown'}:{source_event_id or index}"

    if data_layer == "review_supplemental":
        production_feed = False
        promotion_allowed = False
        manual_review_status = row.get("manual_review_status") or "pending"
        location_cache_modified = bool(row.get("location_cache_modified", False))
        public_map_modified = bool(row.get("public_map_modified", False))
        staged_feed_modified = bool(row.get("staged_feed_modified", False))
    else:
        # Approved/staged rows are already in the staged consumer feed.
        # GPS promotion flags do not apply; keep them null.
        promotion_allowed = None
        manual_review_status = None
        location_cache_modified = False
        public_map_modified = False
        staged_feed_modified = False

    return {
        "id": str(event_id),
        "title": str(row.get("title") or row.get("name") or "Untitled event"),
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
        "significance": row.get("significance", None),
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


def validate_event(event: dict[str, Any], errors: list[str], prefix: str) -> None:
    required = [
        "id",
        "title",
        "category",
        "start_date_time",
        "end_date_time",
        "timezone",
        "borough",
        "location",
        "latitude",
        "longitude",
        "significance",
        "source",
    ]
    for key in required:
        if key not in event:
            errors.append(f"{prefix}: missing field {key}")
    if event.get("timezone") != DEFAULT_TIMEZONE and not event.get("timezone"):
        errors.append(f"{prefix}: empty timezone")
    source = event.get("source")
    if not isinstance(source, dict) or "dataset" not in source or "source_event_id" not in source:
        errors.append(f"{prefix}: source must include dataset and source_event_id")
    lat, lng = event.get("latitude"), event.get("longitude")
    if (lat is None) != (lng is None):
        errors.append(f"{prefix}: latitude/longitude must both be set or both null")
    if lat is not None and lng is not None:
        _, _, ok = valid_nyc_coords(lat, lng)
        if not ok:
            errors.append(f"{prefix}: coordinates outside NYC bounds")
    nycif = event.get("nycif") or {}
    if nycif.get("promotion_allowed") is True and nycif.get("data_layer") == "review_supplemental":
        errors.append(f"{prefix}: supplemental row marked promotion_allowed")
    if nycif.get("coordinate_status") == "list_only" and lat is not None:
        errors.append(f"{prefix}: list_only row has coordinates")
    if nycif.get("coordinate_status") == "map_ready" and lat is None:
        errors.append(f"{prefix}: map_ready row missing coordinates")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-write-feeds", action="store_true")
    args = parser.parse_args()

    generated_at = utc_now()
    staged_payload = json.loads(STAGED_PATH.read_text(encoding="utf-8"))
    supplemental_payload = json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8"))

    staged_rows = extract_events(staged_payload)
    supplemental_rows = extract_events(supplemental_payload)

    staged_events = [
        project_event(row, index=i, data_layer="approved_staged", production_feed=True)
        for i, row in enumerate(staged_rows)
    ]
    supplemental_events = [
        project_event(row, index=i, data_layer="review_supplemental", production_feed=False)
        for i, row in enumerate(supplemental_rows)
    ]

    staged_env = envelope(staged_events, generated_at_utc=generated_at, next_cursor=None)
    supp_env = envelope(supplemental_events, generated_at_utc=generated_at, next_cursor=None)

    errors: list[str] = []
    for i, event in enumerate(staged_events[:50] + staged_events[-50:]):
        validate_event(event, errors, f"staged[{i}]")
    for i, event in enumerate(supplemental_events):
        validate_event(event, errors, f"supplemental[{i}]")

    # Full structural checks without printing every event.
    for label, events in (("staged", staged_events), ("supplemental", supplemental_events)):
        for i, event in enumerate(events):
            if event.get("schema_version"):
                errors.append(f"{label}[{i}]: event must not carry schema_version")
            if not isinstance(event.get("source"), dict):
                errors.append(f"{label}[{i}]: bad source")
            if "lat" in event or "lng" in event:
                errors.append(f"{label}[{i}]: legacy lat/lng leaked into schema event")

    map_ready_supp = sum(
        1 for e in supplemental_events if e["nycif"]["coordinate_status"] == "map_ready"
    )
    list_only_supp = len(supplemental_events) - map_ready_supp

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "qa_pass": len(errors) == 0,
        "error_count": len(errors),
        "errors_sample": errors[:25],
        "staged": {
            "input_path": str(STAGED_PATH.relative_to(REPO_ROOT)),
            "output_path": str(OUT_STAGED.relative_to(REPO_ROOT)),
            "input_count": len(staged_rows),
            "output_total": staged_env["total"],
            "map_ready_count": sum(
                1 for e in staged_events if e["nycif"]["coordinate_status"] == "map_ready"
            ),
            "sample_event": staged_events[0] if staged_events else None,
        },
        "supplemental_review": {
            "input_path": str(SUPPLEMENTAL_PATH.relative_to(REPO_ROOT)),
            "output_path": str(OUT_SUPP.relative_to(REPO_ROOT)),
            "input_count": len(supplemental_rows),
            "output_total": supp_env["total"],
            "map_ready_count": map_ready_supp,
            "list_only_count": list_only_supp,
            "promotion_allowed_any": any(
                e["nycif"]["promotion_allowed"] for e in supplemental_events
            ),
            "production_feed_any": any(e["nycif"]["production_feed"] for e in supplemental_events),
            "sample_event": supplemental_events[0] if supplemental_events else None,
        },
        "safety": {
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "protected_files_rewritten": False,
            "promotion_allowed": False,
        },
        "envelope_contract": {
            "schema_version": SCHEMA_VERSION,
            "required_top_level": [
                "schema_version",
                "generated_at_utc",
                "total",
                "next_cursor",
                "events",
            ],
            "required_event_fields": [
                "id",
                "title",
                "category",
                "start_date_time",
                "end_date_time",
                "timezone",
                "borough",
                "location",
                "latitude",
                "longitude",
                "significance",
                "source",
            ],
        },
    }

    if not args.skip_write_feeds:
        write_json(OUT_STAGED, staged_env)
        write_json(OUT_SUPP, supp_env)
    write_json(OUT_REPORT, report)

    print(json.dumps({"qa_pass": report["qa_pass"], "report": str(OUT_REPORT)}, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
