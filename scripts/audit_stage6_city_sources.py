#!/usr/bin/env python3
"""Audit MOME, DOB and DOT candidates without modifying production feeds.

Stage 6 is an evidence gate, not an ingestion shortcut. The audit records source
freshness, schema fitness, current/future coverage, location capability and
possible overlap with the approved occurrence feed. Every candidate receives an
explicit disposition. No public or review feed is written by this script.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "stage6_city_source_candidates.json"
REPORT_PATH = ROOT / "data" / "reports" / "stage6_city_source_shadow_audit.json"
SUMMARY_PATH = ROOT / "data" / "reports" / "stage6_city_source_shadow_audit.md"
APPROVED_MANIFEST = ROOT / "data" / "schema-v1-discovery" / "approved" / "manifest.json"
API_ROOT = "https://data.cityofnewyork.us"
TODAY = date.today().isoformat()
USER_AGENT = "NYCInFocus-Stage6-Shadow-Audit/1.0"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def fetch_json(url: str, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - exercised by live workflow
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {attempts} attempts: {url}: {last_error}")


def resource_query(dataset_id: str, params: dict[str, str]) -> Any:
    query = urllib.parse.urlencode(params, safe="(),*' ")
    return fetch_json(f"{API_ROOT}/resource/{dataset_id}.json?{query}")


def normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def date_key(value: Any) -> str:
    text = str(value or "")
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else ""


def unix_iso(value: Any) -> str | None:
    try:
        stamp = float(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def age_days(iso_value: str | None) -> float | None:
    if not iso_value:
        return None
    try:
        moment = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((datetime.now(timezone.utc) - moment).total_seconds() / 86400, 2)


def count_value(payload: Any) -> int | None:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return None
    for key in ("count", "row_count", "total"):
        if key in payload[0]:
            try:
                return int(float(payload[0][key]))
            except (TypeError, ValueError):
                return None
    return None


def metadata_columns(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in metadata.get("columns", []) if isinstance(item, dict)]


def field_names(metadata: dict[str, Any]) -> set[str]:
    return {
        str(item.get("fieldName") or "").strip()
        for item in metadata_columns(metadata)
        if str(item.get("fieldName") or "").strip()
    }


def calendar_fields(metadata: dict[str, Any]) -> list[str]:
    return [
        str(item.get("fieldName"))
        for item in metadata_columns(metadata)
        if item.get("dataTypeName") in {"calendar_date", "floating_timestamp"}
        and item.get("fieldName")
    ]


def geometry_fields(metadata: dict[str, Any]) -> list[str]:
    geometry_types = {"point", "multipoint", "line", "multiline", "polygon", "multipolygon"}
    result = []
    for item in metadata_columns(metadata):
        field = str(item.get("fieldName") or "")
        data_type = str(item.get("dataTypeName") or "").lower()
        if field and (data_type in geometry_types or field in {"latitude", "longitude", "lat", "lng", "the_geom"}):
            result.append(field)
    return result


def resolve_first(fields: set[str], configured: list[Any]) -> str | None:
    for value in configured:
        candidate = str(value or "").strip()
        if candidate and candidate in fields:
            return candidate
    return None


def max_date_for_field(dataset_id: str, field: str) -> str | None:
    try:
        payload = resource_query(dataset_id, {"$select": f"max({field}) as max_value", "$limit": "1"})
    except Exception:
        return None
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return str(payload[0].get("max_value") or "") or None
    return None


def approved_events() -> list[dict[str, Any]]:
    manifest = load_json(APPROVED_MANIFEST, {})
    rows: list[dict[str, Any]] = []
    for page in manifest.get("pages", []) if isinstance(manifest, dict) else []:
        name = page.get("page") if isinstance(page, dict) else page
        if not name:
            continue
        payload = load_json(APPROVED_MANIFEST.parent / str(name), {})
        if isinstance(payload, list):
            rows.extend(item for item in payload if isinstance(item, dict))
        elif isinstance(payload, dict):
            rows.extend(item for item in payload.get("events", []) if isinstance(item, dict))
    return rows


def approved_indexes(rows: list[dict[str, Any]]) -> tuple[set[str], set[tuple[str, str, str]]]:
    source_ids: set[str] = set()
    semantic: set[tuple[str, str, str]] = set()
    for row in rows:
        source = row.get("source") if isinstance(row.get("source"), dict) else {}
        for value in (
            row.get("source_event_id"),
            row.get("event_id"),
            row.get("id"),
            source.get("source_event_id"),
        ):
            text = str(value or "").strip()
            if text:
                source_ids.add(text)
        semantic.add(
            (
                date_key(row.get("start_date_time") or row.get("date")),
                normalized(row.get("borough") or row.get("event_borough")),
                normalized(row.get("location") or row.get("display_location") or row.get("event_location")),
            )
        )
    semantic.discard(("", "", ""))
    return source_ids, semantic


def current_rows(dataset_id: str, primary_date: str | None, limit: int = 5000) -> tuple[list[dict[str, Any]], str | None]:
    if not primary_date:
        return [], "no_primary_date_field"
    where = f"{primary_date} >= '{TODAY}T00:00:00.000'"
    try:
        payload = resource_query(
            dataset_id,
            {"$where": where, "$order": primary_date, "$limit": str(limit)},
        )
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"
    if not isinstance(payload, list):
        return [], "response_not_list"
    return [item for item in payload if isinstance(item, dict)], None


def current_count(dataset_id: str, primary_date: str | None) -> tuple[int | None, str | None]:
    if not primary_date:
        return None, "no_primary_date_field"
    where = f"{primary_date} >= '{TODAY}T00:00:00.000'"
    try:
        payload = resource_query(dataset_id, {"$select": "count(*) as count", "$where": where})
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return count_value(payload), None


def candidate_semantic_key(row: dict[str, Any], candidate: dict[str, Any]) -> tuple[str, str, str]:
    date_field = candidate.get("resolved_primary_date_field")
    borough_field = candidate.get("resolved_borough_field")
    location_fields = candidate.get("location_fields") or []
    location = " ".join(str(row.get(field) or "") for field in location_fields)
    return (
        date_key(row.get(date_field)) if date_field else "",
        normalized(row.get(borough_field)) if borough_field else "",
        normalized(location),
    )


def classify(
    candidate: dict[str, Any],
    *,
    metadata_age: float | None,
    missing_required: list[str],
    current_future_count: int | None,
    current_error: str | None,
    has_location: bool,
    has_direct_geometry: bool,
    overlap_source_ids: int,
    overlap_semantic: int,
) -> tuple[str, list[str]]:
    role = str(candidate.get("role") or "")
    reasons: list[str] = []
    if missing_required:
        reasons.append(f"missing required fields: {', '.join(missing_required)}")
    if metadata_age is not None and metadata_age > 90:
        reasons.append(f"source metadata/data update is {metadata_age} days old")
    if current_error:
        reasons.append(f"current/future query unavailable: {current_error}")
    if current_future_count == 0:
        reasons.append("no current or future rows")
    if not has_location:
        reasons.append("no usable location fields")
    if has_location and not has_direct_geometry:
        reasons.append("location text requires borough-safe resolution before mapping")
    if overlap_source_ids or overlap_semantic:
        reasons.append(
            f"approved-feed overlap observed: {overlap_source_ids} source-ID and {overlap_semantic} semantic matches"
        )

    if role == "infrastructure_corroboration":
        return "infrastructure_context_only_not_public_event_feed", reasons or [
            "permit lifecycle rows describe infrastructure work, not public events"
        ]
    if role == "advisory_candidate":
        if metadata_age is None or metadata_age > 30 or current_future_count in (None, 0):
            return "blocked_stale_or_non_current_advisory_source", reasons
        return "extended_shadow_only_pending_event_normalization", reasons
    if role == "event_candidate":
        if missing_required:
            return "blocked_schema_incomplete", reasons
        if metadata_age is not None and metadata_age > 30:
            return "blocked_source_stale", reasons
        if current_future_count in (None, 0):
            return "blocked_no_current_future_rows", reasons
        if not has_location:
            return "blocked_no_location", reasons
        if not has_direct_geometry:
            return "extended_shadow_only_pending_location_resolution_and_dedupe", reasons
        return "extended_shadow_only_pending_editorial_approval", reasons
    return "blocked_unknown_source_role", reasons


def audit_candidate(
    raw_candidate: dict[str, Any],
    approved_source_ids: set[str],
    approved_semantic: set[tuple[str, str, str]],
) -> dict[str, Any]:
    candidate = dict(raw_candidate)
    dataset_id = str(candidate["dataset_id"])
    metadata = fetch_json(f"{API_ROOT}/api/views/{dataset_id}")
    if not isinstance(metadata, dict):
        raise RuntimeError(f"{dataset_id}: metadata response was not an object")
    fields = field_names(metadata)
    primary_candidates = [candidate.get("primary_date_field")] + list(candidate.get("primary_date_field_candidates") or [])
    borough_candidates = [candidate.get("borough_field")] + list(candidate.get("borough_field_candidates") or [])
    primary_date = resolve_first(fields, primary_candidates)
    borough_field = resolve_first(fields, borough_candidates)
    candidate["resolved_primary_date_field"] = primary_date
    candidate["resolved_borough_field"] = borough_field

    try:
        total_rows = count_value(resource_query(dataset_id, {"$select": "count(*) as count"}))
        count_error = None
    except Exception as exc:
        total_rows = None
        count_error = f"{type(exc).__name__}: {exc}"

    date_maxima = {
        field: value
        for field in calendar_fields(metadata)[:12]
        if (value := max_date_for_field(dataset_id, field))
    }
    current_future_count, future_count_error = current_count(dataset_id, primary_date)
    sample, sample_error = current_rows(dataset_id, primary_date)
    current_error = future_count_error or sample_error

    source_id_field = str(candidate.get("source_id_field") or "")
    source_overlap = 0
    semantic_overlap = 0
    for row in sample:
        source_id = str(row.get(source_id_field) or "").strip() if source_id_field else ""
        if source_id and source_id in approved_source_ids:
            source_overlap += 1
        key = candidate_semantic_key(row, candidate)
        if key != ("", "", "") and key in approved_semantic:
            semantic_overlap += 1

    location_fields = [field for field in candidate.get("location_fields", []) if field in fields]
    direct_geometry = geometry_fields(metadata)
    missing_required = sorted(set(candidate.get("required_fields") or []) - fields)
    updated_at = unix_iso(metadata.get("rowsUpdatedAt") or metadata.get("viewLastModified"))
    updated_age = age_days(updated_at)
    disposition, reasons = classify(
        candidate,
        metadata_age=updated_age,
        missing_required=missing_required,
        current_future_count=current_future_count,
        current_error=current_error,
        has_location=bool(location_fields or direct_geometry),
        has_direct_geometry=bool(direct_geometry),
        overlap_source_ids=source_overlap,
        overlap_semantic=semantic_overlap,
    )
    return {
        "id": candidate.get("id"),
        "dataset_id": dataset_id,
        "dataset_name": metadata.get("name"),
        "agency": metadata.get("attribution") or candidate.get("agency"),
        "official_provenance": metadata.get("provenance") == "official",
        "publication_stage": metadata.get("publicationStage"),
        "source_url": f"{API_ROOT}/resource/{dataset_id}.json",
        "metadata_url": f"{API_ROOT}/api/views/{dataset_id}",
        "role": candidate.get("role"),
        "promotion_policy": candidate.get("promotion_policy"),
        "row_count": total_rows,
        "row_count_error": count_error,
        "updated_at_utc": updated_at,
        "update_age_days": updated_age,
        "field_count": len(fields),
        "fields": sorted(fields),
        "missing_required_fields": missing_required,
        "calendar_fields": calendar_fields(metadata),
        "date_maxima": date_maxima,
        "primary_date_field": primary_date,
        "current_future_count": current_future_count,
        "current_future_query_error": current_error,
        "current_future_sample_count": len(sample),
        "borough_field": borough_field,
        "location_fields": location_fields,
        "direct_geometry_fields": direct_geometry,
        "approved_overlap_source_id_count": source_overlap,
        "approved_overlap_semantic_count": semantic_overlap,
        "disposition": disposition,
        "disposition_reasons": reasons,
        "production_promotion_allowed": False,
        "production_feeds_modified": False,
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Stage 6 city-source shadow audit",
        "",
        f"Generated: `{report['generated_at_utc']}`",
        "",
        f"Overall result: **{report['status']}**",
        "",
        "No production feed was modified. Each source remains shadow-only unless a separate promotion review is approved.",
        "",
    ]
    for source in report["sources"]:
        lines.extend(
            [
                f"## {source['dataset_name']} (`{source['dataset_id']}`)",
                "",
                f"- Role: `{source['role']}`",
                f"- Rows: `{source['row_count']}`",
                f"- Updated: `{source['updated_at_utc']}`",
                f"- Current/future rows: `{source['current_future_count']}`",
                f"- Direct geometry fields: `{', '.join(source['direct_geometry_fields']) or 'none'}`",
                f"- Location fields: `{', '.join(source['location_fields']) or 'none'}`",
                f"- Approved overlap: source IDs `{source['approved_overlap_source_id_count']}`, semantic `{source['approved_overlap_semantic_count']}`",
                f"- Disposition: **{source['disposition']}**",
            ]
        )
        for reason in source["disposition_reasons"]:
            lines.append(f"  - {reason}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--summary", type=Path, default=SUMMARY_PATH)
    args = parser.parse_args()

    config = load_json(args.config, {})
    candidates = config.get("candidates", []) if isinstance(config, dict) else []
    if not candidates:
        raise RuntimeError("Stage 6 candidate configuration is empty")

    approved = approved_events()
    approved_source_ids, approved_semantic = approved_indexes(approved)
    sources: list[dict[str, Any]] = []
    errors: list[str] = []
    for candidate in candidates:
        try:
            sources.append(audit_candidate(candidate, approved_source_ids, approved_semantic))
        except Exception as exc:
            dataset_id = candidate.get("dataset_id") if isinstance(candidate, dict) else "unknown"
            errors.append(f"{dataset_id}: {type(exc).__name__}: {exc}")

    valid_dispositions = all(source.get("disposition") for source in sources)
    no_promotions = all(not source.get("production_promotion_allowed") for source in sources)
    qa_pass = not errors and len(sources) == len(candidates) and valid_dispositions and no_promotions
    report = {
        "artifact_type": "nycif_stage6_city_source_shadow_audit",
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "today_nyc_date": TODAY,
        "mode": "shadow_only",
        "status": "PASS" if qa_pass else "BLOCKED",
        "qa_pass": qa_pass,
        "production_feeds_modified": False,
        "production_promotion_default": False,
        "operating_rule": config.get("operating_rule"),
        "approved_events_indexed": len(approved),
        "source_count": len(sources),
        "errors": errors,
        "sources": sources,
    }
    write_json(args.report, report)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if qa_pass else 1


if __name__ == "__main__":
    sys.exit(main())
