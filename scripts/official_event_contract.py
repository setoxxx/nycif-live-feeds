"""Shared Rung 8 + reader-map contract for official city datasets.

Every official dataset must emit the same shape the phone already reads:
event_reader_rolling_v1 via nycif_apply_staging_event_batch. Pin rules stay
dataset-specific so the map never invents a dot.
"""

from __future__ import annotations

import math
import re
from typing import Any

DATASET_TVPP = "tvpp-9vvx"
DATASET_PARKS = "nyc-parks-bigapps-events"
DATASET_CALENDAR = "nyc-citywide-events-calendar-api"
DATASET_FEAST = "nyc-projected-feast-reference"
OFFICIAL_DATASETS = (DATASET_TVPP, DATASET_PARKS, DATASET_CALENDAR, DATASET_FEAST)

# TVPP and projected-feast streets may pin only with official NYC evidence
# (Parks facilities, Geoclient, LION, GeoSearch). Parks requires official
# source evidence. Calendar may pin from snapshot coords or the same official
# resolver. Borough-only / citywide / multi-site rows stay list-only.
PIN_NEVER: frozenset[str] = frozenset()
PIN_TVPP_RESOLVED = frozenset({DATASET_TVPP, DATASET_FEAST})
PIN_OFFICIAL_EVIDENCE = frozenset({DATASET_PARKS})
PIN_SNAPSHOT_COORDS = frozenset({DATASET_CALENDAR})
PIN_RESOLVED_OFFICIAL = PIN_TVPP_RESOLVED
BOROUGH_ONLY_LOCATIONS = frozenset(
    {"manhattan", "brooklyn", "queens", "bronx", "staten island", "citywide", ""}
)
CITYWIDE_NO_SITE_RE = re.compile(
    r"citywide|all five boroughs|check website|locations across",
    flags=re.IGNORECASE,
)

NYC_LAT_RANGE = (40.4, 41.1)
NYC_LNG_RANGE = (-74.35, -73.65)
TIMEZONE = "America/New_York"
OCCURRENCE_ID_RE = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_TOP_LEVEL = (
    "occurrence_id",
    "title",
    "start_at",
    "timezone",
    "display_location",
    "map_ready",
    "status",
    "source_active",
    "metadata",
    "source",
)
REQUIRED_READER = (
    "event_role",
    "certified_pin",
    "map_eligibility_state",
    "display_disposition",
    "location_authority",
    "source_dataset",
    "source_event_id",
)
REQUIRED_SOURCE = (
    "source_name",
    "source_dataset",
    "source_event_id",
    "source_active",
)


class OfficialEventContractError(ValueError):
    """Raised when a dataset row is not safe to send to Supabase."""


def _finite_coord(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def in_nyc_bounds(lat: float | None, lng: float | None) -> bool:
    if lat is None or lng is None:
        return False
    return NYC_LAT_RANGE[0] <= lat <= NYC_LAT_RANGE[1] and NYC_LNG_RANGE[0] <= lng <= NYC_LNG_RANGE[1]


def is_borough_only_location(display: str) -> bool:
    return str(display or "").strip().casefold() in BOROUGH_ONLY_LOCATIONS


def is_citywide_no_site(display: str, borough: str | None = None) -> bool:
    if str(borough or "").strip().casefold() == "citywide":
        return True
    return bool(CITYWIDE_NO_SITE_RE.search(f"{display or ''} {borough or ''}"))


def is_multi_site_location(display: str) -> bool:
    text = str(display or "")
    if " between " in text.casefold():
        return False
    return text.count(",") >= 3


def native_map_row_visible(
    display: str,
    borough: str | None = None,
    source_dataset: str | None = None,
) -> bool:
    """Hide leftover borough-only TVPP and citywide/multi-site rows from Pending."""
    if is_borough_only_location(display):
        return False
    if is_citywide_no_site(display, borough):
        return False
    if source_dataset == DATASET_PARKS and is_multi_site_location(display):
        return False
    return True


def official_pin_evidence(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    return evidence.get("exact_pin_eligible") is True or evidence.get(
        "reason_code"
    ) == "OFFICIAL_SOURCE_COORDINATE_SITE_VALIDATED"


def apply_pin_policy(
    dataset: str,
    lat: Any,
    lng: Any,
    evidence: Any = None,
) -> tuple[float | None, float | None, bool]:
    parsed_lat = _finite_coord(lat)
    parsed_lng = _finite_coord(lng)
    if dataset in PIN_NEVER or not in_nyc_bounds(parsed_lat, parsed_lng):
        return None, None, False
    if dataset in PIN_TVPP_RESOLVED:
        if official_pin_evidence(evidence):
            return parsed_lat, parsed_lng, True
        return None, None, False
    if dataset in PIN_OFFICIAL_EVIDENCE and not official_pin_evidence(evidence):
        return None, None, False
    if dataset in PIN_SNAPSHOT_COORDS or dataset in PIN_OFFICIAL_EVIDENCE:
        return parsed_lat, parsed_lng, True
    return None, None, False


def reader_blob(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    reader = metadata.get("reader") if isinstance(metadata.get("reader"), dict) else {}
    return reader


def apply_reader_display(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    dataset = str(source.get("source_dataset") or "")
    evidence = None
    raw = source.get("raw_record") if isinstance(source.get("raw_record"), dict) else {}
    if isinstance(raw.get("location_evidence"), dict):
        evidence = raw.get("location_evidence")
    lat, lng, map_ready = apply_pin_policy(dataset, event.get("lat"), event.get("lng"), evidence)
    event["lat"] = lat
    event["lng"] = lng
    event["map_ready"] = map_ready
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    reader = metadata.get("reader") if isinstance(metadata.get("reader"), dict) else {}
    reader["certified_pin"] = map_ready
    reader["map_eligibility_state"] = "MAP_READY" if map_ready else "LIST_ONLY"
    reader["display_disposition"] = "MAP" if map_ready else "LIST_ONLY"
    reader["source_dataset"] = dataset
    reader["source_event_id"] = str(source.get("source_event_id") or reader.get("source_event_id") or "")
    if "event_role" not in reader:
        reader["event_role"] = "public_event"
    metadata["reader"] = reader
    event["metadata"] = metadata
    quality = event.get("quality") if isinstance(event.get("quality"), dict) else {}
    quality["public_display_status"] = "FULL_TIME" if map_ready else "LIST_ONLY"
    event["quality"] = quality
    return event


def assert_rung8_event(event: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise OfficialEventContractError("official event must be an object")
    for key in REQUIRED_TOP_LEVEL:
        if key not in event:
            raise OfficialEventContractError(f"official event missing {key}")
    occurrence_id = str(event.get("occurrence_id") or "")
    if not OCCURRENCE_ID_RE.fullmatch(occurrence_id):
        raise OfficialEventContractError("occurrence_id must be OccurrenceIdentityV2 SHA-256")
    if not str(event.get("title") or "").strip():
        raise OfficialEventContractError("title is required")
    if not event.get("start_at"):
        raise OfficialEventContractError("start_at is required")
    if str(event.get("timezone") or "") != TIMEZONE:
        raise OfficialEventContractError("timezone must be America/New_York")
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    for key in REQUIRED_SOURCE:
        if not source.get(key) and source.get(key) is not False:
            raise OfficialEventContractError(f"source.{key} is required")
    if source.get("source_name") != "nyc_open_data":
        raise OfficialEventContractError("source_name must be nyc_open_data")
    dataset = str(source.get("source_dataset") or "")
    if dataset not in OFFICIAL_DATASETS:
        raise OfficialEventContractError(f"unsupported official dataset: {dataset}")
    reader = reader_blob(event)
    for key in REQUIRED_READER:
        if reader.get(key) in (None, ""):
            raise OfficialEventContractError(f"metadata.reader.{key} is required")
    if reader.get("source_dataset") != dataset:
        raise OfficialEventContractError("reader.source_dataset must match source.source_dataset")
    if str(reader.get("source_event_id") or "") != str(source.get("source_event_id") or ""):
        raise OfficialEventContractError("reader.source_event_id must match source.source_event_id")
    map_ready = event.get("map_ready") is True
    lat = _finite_coord(event.get("lat"))
    lng = _finite_coord(event.get("lng"))
    if map_ready:
        if not in_nyc_bounds(lat, lng):
            raise OfficialEventContractError("map_ready rows need in-bounds lat/lng")
        if reader.get("certified_pin") is not True:
            raise OfficialEventContractError("map_ready rows must set certified_pin")
        if reader.get("map_eligibility_state") != "MAP_READY":
            raise OfficialEventContractError("map_ready rows must be MAP_READY")
        if dataset in PIN_NEVER:
            raise OfficialEventContractError(f"{dataset} must stay list-only")
    else:
        if event.get("lat") is not None or event.get("lng") is not None:
            raise OfficialEventContractError("list-only rows must not carry coordinates")
        if reader.get("certified_pin") is True:
            raise OfficialEventContractError("list-only rows cannot be certified pins")
        if reader.get("map_eligibility_state") != "LIST_ONLY":
            raise OfficialEventContractError("list-only rows must be LIST_ONLY")
    return event


def assert_official_batch(rows: list[dict[str, Any]], dataset: str) -> list[dict[str, Any]]:
    if not rows:
        raise OfficialEventContractError(f"no official rows normalized for {dataset}")
    seen: set[str] = set()
    checked: list[dict[str, Any]] = []
    for row in rows:
        apply_reader_display(row)
        assert_rung8_event(row)
        if row["source"]["source_dataset"] != dataset:
            raise OfficialEventContractError(f"row dataset {row['source']['source_dataset']} != {dataset}")
        occurrence_id = row["occurrence_id"]
        if occurrence_id in seen:
            continue
        seen.add(occurrence_id)
        checked.append(row)
    if dataset in PIN_NEVER and any(row.get("map_ready") is True for row in checked):
        raise OfficialEventContractError(f"{dataset} batch must stay list-only")
    return checked
