#!/usr/bin/env python3
"""Build a protected City Engine staging GeoJSON feed from NYCIF staged events.

This script reads the protected staged feed but never modifies it. The generated
artifact is review-only and deliberately marks every record as not authorized for
public display.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

NYC_LATITUDE = (40.45, 40.95)
NYC_LONGITUDE = (-74.30, -73.65)
DATASET_ID = re.compile(r"^[a-z0-9]{4}-[a-z0-9]{4}$")
BOROUGHS = {
    "manhattan": "Manhattan",
    "brooklyn": "Brooklyn",
    "queens": "Queens",
    "bronx": "Bronx",
    "staten island": "Staten Island",
    "citywide": "Citywide",
}
CATEGORY_MAP = {
    "arts": "Arts & Culture",
    "arts & culture": "Arts & Culture",
    "culture": "Arts & Culture",
    "music": "Arts & Culture",
    "civic": "Civic / Public Meeting",
    "public meeting": "Civic / Public Meeting",
    "festival": "Festival / Street Fair",
    "market": "Festival / Street Fair",
    "street fair": "Festival / Street Fair",
    "parade": "Parade / March / Procession",
    "march": "Parade / March / Procession",
    "procession": "Parade / March / Procession",
    "parks": "Parks / Outdoors",
    "park": "Parks / Outdoors",
    "outdoors": "Parks / Outdoors",
    "photo": "Photo Opportunity",
    "sports": "Sports Culture",
    "sport": "Sports Culture",
    "transit": "Transit / Street Closure",
    "street closure": "Transit / Street Closure",
    "family": "Family",
    "jobs": "Jobs",
    "job": "Jobs",
}


class FeedBuildError(RuntimeError):
    """Raised when the staging feed cannot be built safely."""


@dataclass(frozen=True)
class BuildWindow:
    start: date
    end: date

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end


@dataclass
class Counters:
    input: int = 0
    included: int = 0
    outside_window: int = 0
    not_staged: int = 0
    not_production_ready: int = 0
    needs_review: int = 0
    invalid_identity: int = 0
    invalid_date: int = 0
    invalid_coordinates: int = 0

    def as_dict(self) -> dict[str, int]:
        return dict(vars(self))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-days", type=int, default=8)
    parser.add_argument("--max-source-age-hours", type=int, default=36)
    parser.add_argument("--reviewed-at", help="ISO-8601 timestamp; defaults to current UTC time")
    parser.add_argument("--report-only", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FeedBuildError(f"Required input is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FeedBuildError(f"Invalid JSON in {path}: {exc}") from exc


def parse_iso_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FeedBuildError(f"{field} must be a non-empty ISO-8601 timestamp")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise FeedBuildError(f"{field} is not a valid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_date_value(value: Any) -> date | None:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def parse_time_from_datetime(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return ""
    return parsed.strftime("%H:%M")


def source_url(event: dict[str, Any]) -> str:
    for key in ("official_source_url", "source_url"):
        value = event.get(key)
        if isinstance(value, str):
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                return value

    dataset = str(event.get("source_dataset") or "").strip().lower()
    if DATASET_ID.fullmatch(dataset):
        return f"https://data.cityofnewyork.us/resource/{dataset}.json"
    return "https://data.cityofnewyork.us/"


def normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in CATEGORY_MAP:
        return CATEGORY_MAP[text]
    for key, normalized in CATEGORY_MAP.items():
        if key in text:
            return normalized
    return "Other"


def normalize_borough(value: Any) -> str:
    return BOROUGHS.get(str(value or "").strip().lower(), "Unspecified")


def valid_coordinates(lat: Any, lng: Any) -> bool:
    return (
        isinstance(lat, (int, float))
        and not isinstance(lat, bool)
        and isinstance(lng, (int, float))
        and not isinstance(lng, bool)
        and NYC_LATITUDE[0] <= float(lat) <= NYC_LATITUDE[1]
        and NYC_LONGITUDE[0] <= float(lng) <= NYC_LONGITUDE[1]
    )


def feature_from_event(event: dict[str, Any], last_checked: str) -> dict[str, Any]:
    event_id = str(event["id"]).strip()
    title = str(event["title"]).strip()
    event_date = parse_date_value(event.get("date"))
    if event_date is None:
        raise FeedBuildError(f"Eligible event {event_id} has an invalid date")

    lat = float(event["lat"])
    lng = float(event["lng"])
    start_time = parse_time_from_datetime(event.get("start_date_time"))
    end_time = parse_time_from_datetime(event.get("end_date_time"))
    end_date = ""
    if isinstance(event.get("end_date_time"), str):
        try:
            end_date = datetime.fromisoformat(event["end_date_time"].replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            end_date = ""

    description = str(event.get("description") or event.get("event_type") or "").strip()
    location = str(event.get("display_location") or event.get("location") or "").strip()
    agency = str(event.get("event_agency") or "NYC Open Data").strip()
    official_url = source_url(event)

    properties: dict[str, Any] = {
        "event_id": event_id,
        "title": title,
        "description": description,
        "category": normalize_category(event.get("category")),
        "start_date": event_date.isoformat(),
        "start_time": start_time,
        "end_date": end_date,
        "end_time": end_time,
        "borough": normalize_borough(event.get("borough")),
        "neighborhood": str(event.get("neighborhood") or "").strip(),
        "address": location,
        "venue_name": location,
        "latitude": lat,
        "longitude": lng,
        "source_name": agency,
        "source_url": official_url,
        "official_source_url": official_url,
        "last_checked": last_checked,
        "status": "confirmed",
        "public_display_eligible": False,
        "staging_display_eligible": True,
        "review_status": "protected-staging",
        "source_dataset": str(event.get("source_dataset") or "").strip(),
        "source_event_id": str(event.get("source_event_id") or "").strip(),
        "street_closure_type": str(event.get("street_closure_type") or "").strip(),
    }

    return {
        "type": "Feature",
        "id": event_id,
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": properties,
    }


def build_feed(
    payload: Any,
    *,
    window: BuildWindow,
    last_checked: str,
) -> tuple[dict[str, Any], Counters]:
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise FeedBuildError("Input must be an object containing an events array")

    counters = Counters(input=len(payload["events"]))
    features: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for raw_event in payload["events"]:
        if not isinstance(raw_event, dict):
            counters.invalid_identity += 1
            continue
        if raw_event.get("staged_feed") is not True:
            counters.not_staged += 1
            continue
        if raw_event.get("production_ready") is not True:
            counters.not_production_ready += 1
            continue
        if raw_event.get("needs_review") is not False:
            counters.needs_review += 1
            continue

        event_id = raw_event.get("id")
        title = raw_event.get("title")
        if not isinstance(event_id, str) or not event_id.strip() or not isinstance(title, str) or len(title.strip()) < 3:
            counters.invalid_identity += 1
            continue

        event_date = parse_date_value(raw_event.get("date"))
        if event_date is None:
            counters.invalid_date += 1
            continue
        if not window.contains(event_date):
            counters.outside_window += 1
            continue

        if not valid_coordinates(raw_event.get("lat"), raw_event.get("lng")):
            counters.invalid_coordinates += 1
            continue

        normalized_id = event_id.strip()
        if normalized_id in seen_ids:
            raise FeedBuildError(f"Duplicate eligible event id: {normalized_id}")
        seen_ids.add(normalized_id)
        features.append(feature_from_event(raw_event, last_checked))

    features.sort(key=lambda item: (
        item["properties"]["start_date"],
        item["properties"]["start_time"],
        item["properties"]["title"].casefold(),
        item["properties"]["event_id"],
    ))
    counters.included = len(features)

    feed = {
        "type": "FeatureCollection",
        "name": "NYCIF City Engine Protected Staging Feed",
        "metadata": {
            "review_only": True,
            "public_authorized": False,
            "window_start": window.start.isoformat(),
            "window_end": window.end.isoformat(),
            "event_count": len(features),
            "last_checked": last_checked,
        },
        "features": features,
    }
    return feed, counters


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.window_days < 1 or args.window_days > 31:
        raise FeedBuildError("window-days must be between 1 and 31")
    if args.max_source_age_hours < 1:
        raise FeedBuildError("max-source-age-hours must be positive")

    try:
        window_start = date.fromisoformat(args.window_start)
    except ValueError as exc:
        raise FeedBuildError("window-start must use YYYY-MM-DD") from exc
    window = BuildWindow(window_start, window_start + timedelta(days=args.window_days - 1))

    metadata = load_json(args.metadata)
    if not isinstance(metadata, dict):
        raise FeedBuildError("Metadata input must be an object")
    source_generated = parse_iso_datetime(metadata.get("generated_at_utc"), "generated_at_utc")
    reviewed_at = parse_iso_datetime(args.reviewed_at, "reviewed-at") if args.reviewed_at else datetime.now(timezone.utc)
    source_age_hours = (reviewed_at - source_generated).total_seconds() / 3600
    source_fresh = 0 <= source_age_hours <= args.max_source_age_hours

    payload = load_json(args.input)
    feed, counters = build_feed(payload, window=window, last_checked=source_generated.isoformat())
    ready = source_fresh and counters.included > 0

    report = {
        "schema_version": "1",
        "review_only": True,
        "public_authorized": False,
        "input_file": str(args.input),
        "input_sha256": sha256_file(args.input),
        "metadata_file": str(args.metadata),
        "metadata_sha256": sha256_file(args.metadata),
        "source_generated_at_utc": source_generated.isoformat(),
        "reviewed_at_utc": reviewed_at.isoformat(),
        "source_age_hours": round(source_age_hours, 3),
        "max_source_age_hours": args.max_source_age_hours,
        "source_fresh": source_fresh,
        "window_start": window.start.isoformat(),
        "window_end": window.end.isoformat(),
        "counts": counters.as_dict(),
        "ready_for_protected_staging": ready,
        "feed_written": False,
        "blocking_reasons": [],
    }
    if not source_fresh:
        report["blocking_reasons"].append("source feed is stale")
    if counters.included == 0:
        report["blocking_reasons"].append("no eligible events in the requested window")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "city-engine-staging-feed-report.json"

    if ready and not args.report_only:
        feed_path = args.output_dir / "city-engine-staging-feed.geojson"
        write_json(feed_path, feed)
        report["feed_written"] = True
        report["feed_sha256"] = sha256_file(feed_path)

    write_json(report_path, report)

    print(json.dumps({
        "report": str(report_path),
        "ready_for_protected_staging": ready,
        "feed_written": report["feed_written"],
        "event_count": counters.included,
        "blocking_reasons": report["blocking_reasons"],
    }, sort_keys=True))
    return 0 if ready or args.report_only else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FeedBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
