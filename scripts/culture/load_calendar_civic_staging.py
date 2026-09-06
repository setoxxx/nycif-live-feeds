#!/usr/bin/env python3
"""Upsert Culture help-calendar + civic staging into live Supabase tables.

Reads JSON written by the existing pullers under data/culture/staging/.
Default is dry-run. --write upserts into culture_calendar_occurrence_v1 and
culture_civic_facility_v1 on the approved staging project.

Safety:
- Never updates culture_reader_settings (gates stay whatever they are).
- Never writes event_occurrences, location_cache, WordPress, or
  culture_place_beta_v1.
- New rows stay review_status=pending, promotion_allowed=false,
  map_ready=false, map_eligible=false.
- Existing ACCEPTED / promotion_allowed / reviewer fields are preserved
  so a later daily pull does not undo Howard's review.
- Does not invent events or places. Missing title/start or facility
  identity ⇒ row dropped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.culture.common import (  # noqa: E402
    CALENDAR_KINDS,
    REPORT_DIR,
    STAGING_DIR,
    default_reader_gates,
    load_json,
    nyc_point,
    save_json,
    utc_now,
)

ET = ZoneInfo("America/New_York")
APPROVED_PROJECT_REF = "oggwpvdirkrnzoolparx"
APPROVED_SUPABASE_URL = f"https://{APPROVED_PROJECT_REF}.supabase.co"
SETTINGS_ID = "v1"

CALENDAR_TABLE = "culture_calendar_occurrence_v1"
CIVIC_TABLE = "culture_civic_facility_v1"
SETTINGS_TABLE = "culture_reader_settings"

CALENDAR_STAGING_FILES = (
    ("workforce1", "workforce1_events.json"),
    ("nybc", "nybc_blood_drives.json"),
    ("show", "show_mobile_clinics.json"),
    ("dol", "dol_career_events.json"),
    ("cuny", "cuny_career_events.json"),
    ("aspca", "aspca_mobile.json"),
)

CIVIC_STAGING_FILES = (
    ("nypd", "nypd_precincts.json", "civic_nypd"),
    ("fdny", "fdny_firehouses.json", "civic_fdny"),
    ("shelter", "shelters.json", "shelter"),
)

CIVIC_KINDS = {"civic_nypd", "civic_fdny", "shelter", "pet_care"}
OCCURRENCE_KINDS = {
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
}
PIN_POLICIES = {"list_only", "zip_area_only", "certified_pin"}
GATE_COLUMNS = tuple(default_reader_gates().keys())

CALENDAR_COLUMNS = (
    "occurrence_id",
    "calendar_kind",
    "occurrence_kind",
    "title",
    "start_at",
    "end_at",
    "timezone",
    "time_precision",
    "borough",
    "display_location",
    "address",
    "place_id",
    "facility_id",
    "lat",
    "lng",
    "map_ready",
    "zip_codes",
    "waitlist_gated",
    "pin_policy",
    "chip_id",
    "chip_label",
    "emoji",
    "source_name",
    "source_dataset",
    "source_event_id",
    "source_family",
    "public_url",
    "is_sample",
    "review_status",
    "manual_review_status",
    "manual_reviewer",
    "manual_reviewed_at_utc",
    "approval_decision_reason",
    "promotion_allowed",
)

CIVIC_COLUMNS = (
    "facility_id",
    "place_kind",
    "source_dataset",
    "source_facility_id",
    "display_name",
    "address",
    "borough",
    "lat",
    "lng",
    "emoji",
    "geometry",
    "addressable",
    "map_eligible",
    "review_status",
    "confidence_reason",
    "is_sample",
    "manual_review_status",
    "manual_reviewer",
    "manual_reviewed_at_utc",
    "approval_decision_reason",
    "promotion_allowed",
    "public_map_modified",
    "location_cache_modified",
    "staged_feed_modified",
)

REVIEW_PRESERVE_FIELDS = (
    "review_status",
    "manual_review_status",
    "manual_reviewer",
    "manual_reviewed_at_utc",
    "approval_decision_reason",
    "promotion_allowed",
)


class LoadError(RuntimeError):
    """Raised when a write target or payload is unsafe."""


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_timestamptz(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace(" ", "T", 1)
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ET)
    return parsed.isoformat()


def _zip_codes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return value is True


def _rows_from_staging(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return [], {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return [], payload
    return [row for row in rows if isinstance(row, dict)], payload


def calendar_row_from_staging(raw: dict[str, Any]) -> dict[str, Any] | None:
    occurrence_id = _clean_text(raw.get("occurrence_id"))
    title = _clean_text(raw.get("title"))
    start_at = _as_timestamptz(raw.get("start_at"))
    if not occurrence_id or not title or not start_at:
        return None
    kind = _clean_text(raw.get("calendar_kind")) or _clean_text(raw.get("occurrence_kind"))
    if kind not in CALENDAR_KINDS:
        return None
    occurrence_kind = _clean_text(raw.get("occurrence_kind")) or kind
    if occurrence_kind not in OCCURRENCE_KINDS:
        return None
    waitlist = _bool(raw.get("waitlist_gated"))
    pin_policy = _clean_text(raw.get("pin_policy")) or ("zip_area_only" if waitlist else "list_only")
    if pin_policy not in PIN_POLICIES or pin_policy == "certified_pin":
        pin_policy = "zip_area_only" if waitlist else "list_only"
    lat, lng, in_nyc = nyc_point(raw.get("lat"), raw.get("lng"))
    review_status = _clean_text(raw.get("review_status")) or "pending"
    if review_status.upper() != "ACCEPTED":
        review_status = "pending"
    manual = (_clean_text(raw.get("manual_review_status")) or "pending").lower()
    if manual not in {"pending", "approved", "accepted"}:
        manual = "pending"
    return {
        "occurrence_id": occurrence_id,
        "calendar_kind": kind,
        "occurrence_kind": occurrence_kind,
        "title": title,
        "start_at": start_at,
        "end_at": _as_timestamptz(raw.get("end_at")),
        "timezone": _clean_text(raw.get("timezone")) or "America/New_York",
        "time_precision": _clean_text(raw.get("time_precision")),
        "borough": _clean_text(raw.get("borough")),
        "display_location": _clean_text(raw.get("display_location")) or _clean_text(raw.get("address")),
        "address": _clean_text(raw.get("address")),
        "place_id": _clean_text(raw.get("place_id")),
        "facility_id": _clean_text(raw.get("facility_id")),
        "lat": lat if in_nyc else None,
        "lng": lng if in_nyc else None,
        "map_ready": False,
        "zip_codes": _zip_codes(raw.get("zip_codes")),
        "waitlist_gated": waitlist,
        "pin_policy": pin_policy,
        "chip_id": _clean_text(raw.get("chip_id")),
        "chip_label": _clean_text(raw.get("chip_label")),
        "emoji": _clean_text(raw.get("emoji")),
        "source_name": _clean_text(raw.get("source_name")),
        "source_dataset": _clean_text(raw.get("source_dataset")),
        "source_event_id": _clean_text(raw.get("source_event_id")),
        "source_family": _clean_text(raw.get("source_family")),
        "public_url": _clean_text(raw.get("public_url")),
        "is_sample": False,
        "review_status": review_status if review_status.upper() == "ACCEPTED" else "pending",
        "manual_review_status": manual,
        "manual_reviewer": _clean_text(raw.get("manual_reviewer")),
        "manual_reviewed_at_utc": _as_timestamptz(raw.get("manual_reviewed_at_utc")),
        "approval_decision_reason": _clean_text(raw.get("approval_decision_reason")),
        "promotion_allowed": False,
    }


def civic_row_from_staging(raw: dict[str, Any], *, default_kind: str | None = None) -> dict[str, Any] | None:
    facility_id = _clean_text(raw.get("facility_id"))
    display_name = _clean_text(raw.get("display_name"))
    source_dataset = _clean_text(raw.get("source_dataset"))
    source_facility_id = _clean_text(raw.get("source_facility_id"))
    place_kind = _clean_text(raw.get("place_kind")) or default_kind
    if not facility_id or not display_name or not source_dataset or not source_facility_id:
        return None
    if place_kind not in CIVIC_KINDS:
        return None
    lat, lng, in_nyc = nyc_point(raw.get("lat"), raw.get("lng"))
    census_only = raw.get("census_only") is True
    if census_only:
        lat, lng = None, None
    review_status = _clean_text(raw.get("review_status")) or "pending"
    if review_status.upper() != "ACCEPTED":
        review_status = "pending"
    manual = (_clean_text(raw.get("manual_review_status")) or "pending").lower()
    if manual not in {"pending", "approved", "accepted"}:
        manual = "pending"
    addressable = _bool(raw.get("addressable")) and not census_only
    return {
        "facility_id": facility_id,
        "place_kind": place_kind,
        "source_dataset": source_dataset,
        "source_facility_id": source_facility_id,
        "display_name": display_name,
        "address": None if census_only else _clean_text(raw.get("address")),
        "borough": _clean_text(raw.get("borough")),
        "lat": lat if in_nyc else None,
        "lng": lng if in_nyc else None,
        "emoji": _clean_text(raw.get("emoji")),
        "geometry": None,
        "addressable": addressable,
        "map_eligible": False,
        "review_status": review_status if review_status.upper() == "ACCEPTED" else "pending",
        "confidence_reason": _clean_text(raw.get("confidence_reason")),
        "is_sample": False,
        "manual_review_status": manual,
        "manual_reviewer": _clean_text(raw.get("manual_reviewer")),
        "manual_reviewed_at_utc": _as_timestamptz(raw.get("manual_reviewed_at_utc")),
        "approval_decision_reason": _clean_text(raw.get("approval_decision_reason")),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }


def _dedupe(rows: list[dict[str, Any]], key: str) -> tuple[list[dict[str, Any]], int]:
    seen: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for row in rows:
        ident = str(row.get(key) or "")
        if ident in seen:
            duplicates += 1
        seen[ident] = row
    return list(seen.values()), duplicates


def collect_calendar_rows(staging_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    counts: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    dropped = 0
    missing_files: list[str] = []
    for name, filename in CALENDAR_STAGING_FILES:
        path = staging_dir / filename
        raw_rows, meta = _rows_from_staging(path)
        if not path.exists():
            missing_files.append(filename)
            counts[name] = {"staged": 0, "accepted_for_load": 0, "missing_file": True}
            continue
        kept: list[dict[str, Any]] = []
        for raw in raw_rows:
            mapped = calendar_row_from_staging(raw)
            if mapped:
                kept.append(mapped)
            else:
                dropped += 1
        counts[name] = {
            "staged": len(raw_rows),
            "accepted_for_load": len(kept),
            "missing_file": False,
            "note": meta.get("note"),
        }
        rows.extend(kept)
    rows, dupes = _dedupe(rows, "occurrence_id")
    return rows, {
        "by_source": counts,
        "dropped_incomplete": dropped,
        "duplicate_occurrence_ids": dupes,
        "missing_files": missing_files,
    }


def collect_civic_rows(staging_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    counts: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    dropped = 0
    missing_files: list[str] = []
    shelter_census_only = False
    for name, filename, default_kind in CIVIC_STAGING_FILES:
        path = staging_dir / filename
        raw_rows, meta = _rows_from_staging(path)
        if name == "shelter" and meta.get("census_only") is True:
            shelter_census_only = True
        if not path.exists():
            missing_files.append(filename)
            counts[name] = {"staged": 0, "accepted_for_load": 0, "missing_file": True}
            continue
        kept: list[dict[str, Any]] = []
        for raw in raw_rows:
            mapped = civic_row_from_staging(raw, default_kind=default_kind)
            if mapped:
                kept.append(mapped)
            else:
                dropped += 1
        counts[name] = {
            "staged": len(raw_rows),
            "accepted_for_load": len(kept),
            "missing_file": False,
            "addressable": sum(1 for row in kept if row.get("addressable")),
            "census_only": meta.get("census_only"),
            "note": meta.get("note"),
        }
        rows.extend(kept)
    rows, dupes = _dedupe(rows, "facility_id")
    source_keys = {(row["source_dataset"], row["source_facility_id"]) for row in rows}
    source_dupes = len(rows) - len(source_keys)
    if source_dupes:
        # Unique (source_dataset, source_facility_id) is enforced in SQL.
        filtered: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            key = (row["source_dataset"], row["source_facility_id"])
            if key in seen:
                continue
            seen.add(key)
            filtered.append(row)
        rows = filtered
    return rows, {
        "by_source": counts,
        "dropped_incomplete": dropped,
        "duplicate_facility_ids": dupes,
        "duplicate_source_keys_collapsed": max(source_dupes, 0),
        "missing_files": missing_files,
        "shelter_census_only": shelter_census_only,
    }


def enabled_gates(settings: dict[str, Any] | None) -> list[str]:
    if not isinstance(settings, dict):
        return []
    return [name for name in GATE_COLUMNS if settings.get(name) is True]


def merge_preserve_review(
    incoming: dict[str, Any],
    existing: dict[str, Any] | None,
    *,
    id_field: str,
) -> dict[str, Any]:
    merged = dict(incoming)
    merged["promotion_allowed"] = False
    if id_field == "occurrence_id":
        merged["map_ready"] = False
    else:
        merged["map_eligible"] = False
        merged["public_map_modified"] = False
        merged["location_cache_modified"] = False
        merged["staged_feed_modified"] = False
    if not existing:
        if str(merged.get("review_status") or "").upper() != "ACCEPTED":
            merged["review_status"] = "pending"
            merged["manual_review_status"] = "pending"
            merged["manual_reviewer"] = None
            merged["manual_reviewed_at_utc"] = None
            merged["approval_decision_reason"] = None
        return merged
    if str(existing.get("review_status") or "").upper() == "ACCEPTED":
        for field in REVIEW_PRESERVE_FIELDS:
            merged[field] = existing.get(field)
        if id_field == "occurrence_id" and existing.get("map_ready") is True:
            merged["map_ready"] = True
            merged["pin_policy"] = existing.get("pin_policy") or merged["pin_policy"]
        if id_field == "facility_id" and existing.get("map_eligible") is True:
            merged["map_eligible"] = True
    return merged


def _canonical_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.params or parsed.query or parsed.fragment:
        raise LoadError("SUPABASE_URL must be a plain https project URL")
    if parsed.username or parsed.password or parsed.port or parsed.path not in {"", "/"}:
        raise LoadError("SUPABASE_URL must not contain credentials, a port, or a path")
    host = (parsed.hostname or "").lower()
    return f"https://{host}"


def validate_write_target(environ: dict[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    url = _canonical_url(str(env.get("SUPABASE_URL") or APPROVED_SUPABASE_URL))
    if url != APPROVED_SUPABASE_URL:
        raise LoadError(f"refusing write target {url}; only {APPROVED_SUPABASE_URL} is approved")
    key = str(env.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not key:
        raise LoadError("SUPABASE_SERVICE_ROLE_KEY is required with --write")
    return url


def _rest_headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def rest_get(url: str, key: str, path: str) -> Any:
    request = urllib.request.Request(f"{url}/rest/v1/{path}", headers=_rest_headers(key), method="GET")
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def rest_upsert(url: str, key: str, table: str, rows: list[dict[str, Any]], on_conflict: str) -> int:
    if not rows:
        return 0
    written = 0
    chunk_size = 80
    headers = {
        **_rest_headers(key),
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        body = json.dumps(chunk).encode("utf-8")
        request = urllib.request.Request(
            f"{url}/rest/v1/{table}?on_conflict={on_conflict}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LoadError(f"upsert {table} failed HTTP {exc.code}: {detail[:800]}") from exc
        written += len(chunk)
    return written


def fetch_settings(url: str, key: str) -> dict[str, Any]:
    rows = rest_get(url, key, f"{SETTINGS_TABLE}?id=eq.{SETTINGS_ID}&select=*")
    if not isinstance(rows, list) or not rows:
        raise LoadError("culture_reader_settings id=v1 is missing")
    return rows[0]


def fetch_existing_map(url: str, key: str, table: str, id_field: str, extra: str) -> dict[str, dict[str, Any]]:
    select = ",".join((id_field, *REVIEW_PRESERVE_FIELDS, extra))
    rows = rest_get(url, key, f"{table}?select={select}")
    if not isinstance(rows, list):
        return {}
    return {str(row.get(id_field)): row for row in rows if isinstance(row, dict) and row.get(id_field)}


def apply_preserve(
    rows: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    id_field: str,
) -> list[dict[str, Any]]:
    return [merge_preserve_review(row, existing.get(str(row[id_field])), id_field=id_field) for row in rows]


def emit_sql(
    calendar_rows: list[dict[str, Any]],
    civic_rows: list[dict[str, Any]],
) -> str:
    def dump(rows: list[dict[str, Any]]) -> str:
        return json.dumps(rows, ensure_ascii=False).replace("'", "''")

    calendar_json = dump(calendar_rows)
    civic_json = dump(civic_rows)
    gate_checks = "\n    ".join(
        f"IF COALESCE(gates.{name}, false) THEN RAISE EXCEPTION 'refusing load: {name} is true'; END IF;"
        for name in GATE_COLUMNS
    )
    return f"""-- Culture calendar/civic staging load. Does not update culture_reader_settings.
-- Generated by scripts/culture/load_calendar_civic_staging.py

DO $$
DECLARE
  gates public.culture_reader_settings%ROWTYPE;
BEGIN
  SELECT * INTO STRICT gates FROM public.culture_reader_settings WHERE id = 'v1';
    {gate_checks}
END $$;

INSERT INTO public.culture_calendar_occurrence_v1 (
  {", ".join(CALENDAR_COLUMNS)}
)
SELECT
  x.occurrence_id,
  x.calendar_kind,
  x.occurrence_kind,
  x.title,
  x.start_at,
  x.end_at,
  COALESCE(x.timezone, 'America/New_York'),
  x.time_precision,
  x.borough,
  x.display_location,
  x.address,
  x.place_id,
  x.facility_id,
  x.lat,
  x.lng,
  false,
  COALESCE(x.zip_codes, '{{}}'),
  COALESCE(x.waitlist_gated, false),
  COALESCE(x.pin_policy, 'list_only'),
  x.chip_id,
  x.chip_label,
  x.emoji,
  x.source_name,
  x.source_dataset,
  x.source_event_id,
  x.source_family,
  x.public_url,
  false,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.review_status
    ELSE 'pending'
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.manual_review_status
    ELSE 'pending'
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.manual_reviewer
    ELSE NULL
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.manual_reviewed_at_utc
    ELSE NULL
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.approval_decision_reason
    ELSE NULL
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN COALESCE(existing.promotion_allowed, false)
    ELSE false
  END
FROM jsonb_to_recordset('{calendar_json}'::jsonb) AS x(
  occurrence_id text,
  calendar_kind text,
  occurrence_kind text,
  title text,
  start_at timestamptz,
  end_at timestamptz,
  timezone text,
  time_precision text,
  borough text,
  display_location text,
  address text,
  place_id text,
  facility_id text,
  lat double precision,
  lng double precision,
  map_ready boolean,
  zip_codes text[],
  waitlist_gated boolean,
  pin_policy text,
  chip_id text,
  chip_label text,
  emoji text,
  source_name text,
  source_dataset text,
  source_event_id text,
  source_family text,
  public_url text,
  is_sample boolean,
  review_status text,
  manual_review_status text,
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  promotion_allowed boolean
)
LEFT JOIN public.culture_calendar_occurrence_v1 AS existing
  ON existing.occurrence_id = x.occurrence_id
ON CONFLICT (occurrence_id) DO UPDATE SET
  calendar_kind = EXCLUDED.calendar_kind,
  occurrence_kind = EXCLUDED.occurrence_kind,
  title = EXCLUDED.title,
  start_at = EXCLUDED.start_at,
  end_at = EXCLUDED.end_at,
  timezone = EXCLUDED.timezone,
  time_precision = EXCLUDED.time_precision,
  borough = EXCLUDED.borough,
  display_location = EXCLUDED.display_location,
  address = EXCLUDED.address,
  place_id = EXCLUDED.place_id,
  facility_id = EXCLUDED.facility_id,
  lat = EXCLUDED.lat,
  lng = EXCLUDED.lng,
  map_ready = CASE
    WHEN public.culture_calendar_occurrence_v1.review_status = 'ACCEPTED'
      THEN public.culture_calendar_occurrence_v1.map_ready
    ELSE false
  END,
  zip_codes = EXCLUDED.zip_codes,
  waitlist_gated = EXCLUDED.waitlist_gated,
  pin_policy = EXCLUDED.pin_policy,
  chip_id = EXCLUDED.chip_id,
  chip_label = EXCLUDED.chip_label,
  emoji = EXCLUDED.emoji,
  source_name = EXCLUDED.source_name,
  source_dataset = EXCLUDED.source_dataset,
  source_event_id = EXCLUDED.source_event_id,
  source_family = EXCLUDED.source_family,
  public_url = EXCLUDED.public_url,
  is_sample = false,
  review_status = CASE
    WHEN public.culture_calendar_occurrence_v1.review_status = 'ACCEPTED'
      THEN public.culture_calendar_occurrence_v1.review_status
    ELSE 'pending'
  END,
  promotion_allowed = public.culture_calendar_occurrence_v1.promotion_allowed,
  updated_at = now();

INSERT INTO public.culture_civic_facility_v1 (
  {", ".join(CIVIC_COLUMNS)}
)
SELECT
  x.facility_id,
  x.place_kind,
  x.source_dataset,
  x.source_facility_id,
  x.display_name,
  x.address,
  x.borough,
  x.lat,
  x.lng,
  x.emoji,
  NULL,
  COALESCE(x.addressable, false),
  false,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.review_status
    ELSE 'pending'
  END,
  x.confidence_reason,
  false,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.manual_review_status
    ELSE 'pending'
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.manual_reviewer
    ELSE NULL
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.manual_reviewed_at_utc
    ELSE NULL
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN existing.approval_decision_reason
    ELSE NULL
  END,
  CASE
    WHEN existing.review_status = 'ACCEPTED' THEN COALESCE(existing.promotion_allowed, false)
    ELSE false
  END,
  false,
  false,
  false
FROM jsonb_to_recordset('{civic_json}'::jsonb) AS x(
  facility_id text,
  place_kind text,
  source_dataset text,
  source_facility_id text,
  display_name text,
  address text,
  borough text,
  lat double precision,
  lng double precision,
  emoji text,
  geometry jsonb,
  addressable boolean,
  map_eligible boolean,
  review_status text,
  confidence_reason text,
  is_sample boolean,
  manual_review_status text,
  manual_reviewer text,
  manual_reviewed_at_utc timestamptz,
  approval_decision_reason text,
  promotion_allowed boolean,
  public_map_modified boolean,
  location_cache_modified boolean,
  staged_feed_modified boolean
)
LEFT JOIN public.culture_civic_facility_v1 AS existing
  ON existing.facility_id = x.facility_id
ON CONFLICT (facility_id) DO UPDATE SET
  place_kind = EXCLUDED.place_kind,
  source_dataset = EXCLUDED.source_dataset,
  source_facility_id = EXCLUDED.source_facility_id,
  display_name = EXCLUDED.display_name,
  address = EXCLUDED.address,
  borough = EXCLUDED.borough,
  lat = EXCLUDED.lat,
  lng = EXCLUDED.lng,
  emoji = EXCLUDED.emoji,
  addressable = EXCLUDED.addressable,
  map_eligible = CASE
    WHEN public.culture_civic_facility_v1.review_status = 'ACCEPTED'
      THEN public.culture_civic_facility_v1.map_eligible
    ELSE false
  END,
  confidence_reason = EXCLUDED.confidence_reason,
  is_sample = false,
  review_status = CASE
    WHEN public.culture_civic_facility_v1.review_status = 'ACCEPTED'
      THEN public.culture_civic_facility_v1.review_status
    ELSE 'pending'
  END,
  promotion_allowed = public.culture_civic_facility_v1.promotion_allowed,
  public_map_modified = false,
  location_cache_modified = false,
  staged_feed_modified = false,
  updated_at = now();
"""


def build_report(
    *,
    dataset: str,
    calendar_rows: list[dict[str, Any]],
    civic_rows: list[dict[str, Any]],
    calendar_meta: dict[str, Any],
    civic_meta: dict[str, Any],
    applied: bool,
    settings_before: dict[str, Any] | None,
    settings_after: dict[str, Any] | None,
    notes: list[str],
) -> dict[str, Any]:
    empty_reasons: list[str] = []
    if dataset in {"calendar", "all"} and not calendar_rows:
        empty_reasons.append(
            "No calendar rows mapped. Run the help-calendar pullers first. "
            "CUNY stays 0 unless a campus fixture/scrape is supplied."
        )
    if dataset in {"civic", "all"} and not civic_rows:
        empty_reasons.append("No civic rows mapped. Run NYPD/FDNY/shelter pullers first.")
    if civic_meta.get("shelter_census_only"):
        notes.append(
            "Shelter dataset g9nt-57fp is census-only; rows load as addressable=false "
            "list-only. Prefer bmxf-3rd4 / ntcm-2w4k before any pin review."
        )
    return {
        "artifact_type": "culture_calendar_civic_load_report",
        "generated_at_utc": utc_now(),
        "dataset": dataset,
        "applied": applied,
        "qa_pass": True,
        "publication_allowed": False,
        "would_publish": False,
        "gates_touched": False,
        "settings_id": SETTINGS_ID,
        "settings_before_enabled": enabled_gates(settings_before),
        "settings_after_enabled": enabled_gates(settings_after),
        "calendar_row_count": len(calendar_rows),
        "civic_row_count": len(civic_rows),
        "calendar": calendar_meta,
        "civic": civic_meta,
        "accepted_calendar_count": sum(
            1 for row in calendar_rows if str(row.get("review_status")) == "ACCEPTED"
        ),
        "accepted_civic_count": sum(
            1 for row in civic_rows if str(row.get("review_status")) == "ACCEPTED"
        ),
        "promotion_allowed_count": sum(
            1
            for row in (*calendar_rows, *civic_rows)
            if row.get("promotion_allowed") is True
        ),
        "map_ready_count": sum(1 for row in calendar_rows if row.get("map_ready") is True),
        "map_eligible_count": sum(1 for row in civic_rows if row.get("map_eligible") is True),
        "empty_reasons": empty_reasons,
        "notes": notes,
        "wordpress_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "event_occurrences_modified": False,
        "culture_place_beta_modified": False,
        "public_map_modified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=("calendar", "civic", "all"), default="all")
    parser.add_argument("--staging-dir", type=Path, default=STAGING_DIR)
    parser.add_argument("--write", action="store_true", help="Upsert into approved Supabase project")
    parser.add_argument("--emit-sql", type=Path, help="Write a gated SQL upsert file")
    parser.add_argument("--payload-json", type=Path, help="Write mapped payload JSON")
    args = parser.parse_args(argv)

    notes: list[str] = []
    calendar_rows: list[dict[str, Any]] = []
    civic_rows: list[dict[str, Any]] = []
    calendar_meta: dict[str, Any] = {"by_source": {}}
    civic_meta: dict[str, Any] = {"by_source": {}}

    if args.dataset in {"calendar", "all"}:
        calendar_rows, calendar_meta = collect_calendar_rows(args.staging_dir)
    if args.dataset in {"civic", "all"}:
        civic_rows, civic_meta = collect_civic_rows(args.staging_dir)

    unsafe = [
        row
        for row in (*calendar_rows, *civic_rows)
        if row.get("promotion_allowed") is True
        or row.get("map_ready") is True
        or row.get("map_eligible") is True
        or row.get("is_sample") is True
    ]
    if unsafe:
        raise LoadError("mapped payload included promotion_allowed, map_ready, map_eligible, or is_sample")

    settings_before = None
    settings_after = None
    applied = False
    if args.write:
        url = validate_write_target()
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"].strip()
        settings_before = fetch_settings(url, key)
        enabled = enabled_gates(settings_before)
        if enabled:
            notes.append(f"gates already enabled before write (not flipped by this script): {enabled}")
        if calendar_rows:
            existing = fetch_existing_map(url, key, CALENDAR_TABLE, "occurrence_id", "map_ready")
            calendar_rows = apply_preserve(calendar_rows, existing, "occurrence_id")
        if civic_rows:
            existing = fetch_existing_map(url, key, CIVIC_TABLE, "facility_id", "map_eligible")
            civic_rows = apply_preserve(civic_rows, existing, "facility_id")
        rest_upsert(url, key, CALENDAR_TABLE, calendar_rows, "occurrence_id")
        rest_upsert(url, key, CIVIC_TABLE, civic_rows, "facility_id")
        settings_after = fetch_settings(url, key)
        if settings_after != settings_before and enabled_gates(settings_after) != enabled_gates(settings_before):
            raise LoadError("culture_reader_settings gates changed during load; refusing to continue")
        applied = True
        notes.append("Upserted staging rows. Gates were not written.")

    payload = {
        "artifact_type": "culture_calendar_civic_load_payload",
        "generated_at_utc": utc_now(),
        "dataset": args.dataset,
        "calendar_rows": calendar_rows,
        "civic_rows": civic_rows,
        "publication_allowed": False,
        "gates_touched": False,
    }
    payload_path = args.payload_json or (REPORT_DIR / "calendar_civic_load_payload.json")
    save_json(payload_path, payload)

    if args.emit_sql:
        args.emit_sql.parent.mkdir(parents=True, exist_ok=True)
        args.emit_sql.write_text(emit_sql(calendar_rows, civic_rows), encoding="utf-8")
        notes.append(f"wrote SQL {args.emit_sql}")

    report = build_report(
        dataset=args.dataset,
        calendar_rows=calendar_rows,
        civic_rows=civic_rows,
        calendar_meta=calendar_meta,
        civic_meta=civic_meta,
        applied=applied,
        settings_before=settings_before,
        settings_after=settings_after,
        notes=notes,
    )
    if report["promotion_allowed_count"] and not applied:
        # Preserve-path after --write may keep Howard-approved flags on existing rows.
        report["qa_pass"] = True
    if any(
        row.get("promotion_allowed") is True and str(row.get("review_status")) != "ACCEPTED"
        for row in (*calendar_rows, *civic_rows)
    ):
        report["qa_pass"] = False
        report["notes"].append("promotion_allowed on a non-ACCEPTED row")
    save_json(REPORT_DIR / "calendar_civic_load_report.json", report)
    print(
        f"dataset={args.dataset} calendar={len(calendar_rows)} civic={len(civic_rows)} "
        f"applied={applied} publication_allowed=false gates_touched=false"
    )
    if report["empty_reasons"]:
        for reason in report["empty_reasons"]:
            print(f"empty: {reason}")
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
