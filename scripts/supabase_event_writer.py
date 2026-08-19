#!/usr/bin/env python3
"""NYCIF Supabase event writer.

Dry-run remains the default.  Controlled writes are sent as one RPC call so
Postgres, rather than a sequence of REST upserts, owns the transaction.
Occurrence identifiers are consumed exactly as emitted by Enigma's
OccurrenceIdentityV2 authority; this module never derives or rewrites them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "reports" / "supabase_writer_report.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enigma.shadow2.occurrence_identity import build_occurrence_identity

ACTIONS = (
    "INSERT",
    "UPDATE",
    "UNCHANGED",
    "EXPIRE",
    "QUALITY_CHANGE",
    "CLASSIFICATION_CHANGE",
    "LOCATION_CHANGE",
)

# Rung 8 is intentionally pinned to the inspected staging project.  Adding a
# target is a reviewed code change, not an environment-only escape hatch.
APPROVED_STAGING_TARGETS = {
    "oggwpvdirkrnzoolparx": "https://oggwpvdirkrnzoolparx.supabase.co",
}
PROJECT_REF_RE = re.compile(r"^[a-z0-9]{20}$")
OCCURRENCE_ID_RE = re.compile(r"^[0-9a-f]{64}$")


class WriteGuardError(RuntimeError):
    """Raised before network access when a write target is not authorized."""


class SupabaseRPCError(RuntimeError):
    """Raised when the atomic database RPC does not complete successfully."""


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract_events(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("events", [])
    return []


def load_supabase_snapshot(path: Path | None):
    """Read-only adapter boundary.

    Future Supabase API/database connector code belongs here.
    This function intentionally only reads exported state.
    """
    if not path:
        return {
            "occurrences": {},
            "sources": {},
            "classifications": {},
            "quality": {},
        }
    return load_json(path)


def occurrence_key(event):
    return str(event.get("occurrence_id") or event.get("id") or "")


def env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def canonical_target_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.params or parsed.query or parsed.fragment:
        raise WriteGuardError("SUPABASE_URL must be a plain https project URL")
    if parsed.username or parsed.password or parsed.port or parsed.path not in {"", "/"}:
        raise WriteGuardError("SUPABASE_URL must not contain credentials, a port, or a path")
    return f"https://{(parsed.hostname or '').lower()}"


def validate_write_target(environ=None):
    """Return the exact approved staging target or fail closed.

    The checked allowlist lives in source control.  Environment variables can
    narrow or deny a target, but cannot authorize a new one.
    """
    environ = os.environ if environ is None else environ
    if str(environ.get("SUPABASE_WRITE_ENABLED", "false")).strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise WriteGuardError("SUPABASE_WRITE_ENABLED is false (default)")
    if str(environ.get("SUPABASE_TARGET_ENV", "")).strip().lower() != "staging":
        raise WriteGuardError("SUPABASE_TARGET_ENV must be exactly 'staging'")

    project_ref = str(environ.get("SUPABASE_PROJECT_REF", "")).strip().lower()
    raw_url = str(environ.get("SUPABASE_URL", "")).strip()
    if not project_ref or not raw_url:
        raise WriteGuardError("SUPABASE_PROJECT_REF and SUPABASE_URL are required")
    if not PROJECT_REF_RE.fullmatch(project_ref):
        raise WriteGuardError("SUPABASE_PROJECT_REF has an invalid format")

    target_url = canonical_target_url(raw_url)
    expected_url = APPROVED_STAGING_TARGETS.get(project_ref)
    if expected_url is None or target_url != expected_url:
        raise WriteGuardError("unknown or non-staging Supabase target")
    if target_url != f"https://{project_ref}.supabase.co":
        raise WriteGuardError("Supabase project ref/URL mismatch")

    denied_refs = {
        item.strip().lower()
        for item in str(environ.get("SUPABASE_PRODUCTION_REFS", "")).split(",")
        if item.strip()
    }
    denied_urls = {
        canonical_target_url(item)
        for item in str(environ.get("SUPABASE_PRODUCTION_URLS", "")).split(",")
        if item.strip()
    }
    if project_ref in denied_refs or target_url in denied_urls:
        raise WriteGuardError("production target is explicitly denied")
    return project_ref, target_url


def _first(event, *paths, default=None):
    for path in paths:
        value = event
        for part in path.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value is not None:
            return value
    return default


def normalize_event(event):
    """Translate canonical Enigma output to the reviewed Rung 8 RPC contract."""
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    raw = source.get("raw_record") if isinstance(source.get("raw_record"), dict) else event
    category = _first(event, "public_category", "category", "nycif.current_classification")
    subtype = _first(event, "public_subtype", "source.source_event_type", "nycif.event_type")
    source_name = str(source.get("source_name") or "nyc_open_data")
    source_dataset = str(source.get("source_dataset") or source.get("dataset") or "")
    source_event_id = str(source.get("source_event_id") or "")
    if not source_dataset or not source_event_id:
        raise ValueError("source dataset/event id missing")

    supplied_occurrence_id = str(event.get("occurrence_id") or "")
    if supplied_occurrence_id:
        occurrence_id = supplied_occurrence_id
    else:
        identity = build_occurrence_identity(
            {
                "source_event_id": source_event_id,
                "start_date_time": _first(event, "start_at", "start_date_time"),
                "event_date": _first(event, "event_date", "nycif.event_date"),
                "timezone": event.get("timezone") or "America/New_York",
            },
            source_name,
            source_dataset,
        )
        if identity is None:
            raise ValueError("OccurrenceIdentityV2 could not build an occurrence id")
        occurrence_id = identity.canonical_id()
    if not OCCURRENCE_ID_RE.fullmatch(occurrence_id):
        raise ValueError(f"invalid OccurrenceIdentityV2 occurrence id: {occurrence_id!r}")

    flags = _first(event, "quality.quality_flags", default=[])
    details = _first(event, "quality.details", default={})
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    return {
        "occurrence_id": occurrence_id,
        "title": str(_first(event, "title", "event_name", default="")),
        "start_at": _first(event, "start_at", "start_date_time"),
        "end_at": _first(event, "end_at", "end_date_time"),
        "timezone": str(event.get("timezone") or "America/New_York"),
        "borough": _first(event, "borough", "event_borough"),
        "display_location": _first(event, "display_location", "location", "event_location"),
        "lat": _first(event, "lat", "latitude"),
        "lng": _first(event, "lng", "longitude"),
        "public_category": category,
        "public_subtype": subtype,
        "status": str(event.get("status") or "active"),
        "source_active": bool(event.get("source_active", True)),
        "map_ready": bool(_first(event, "map_ready", "nycif.certified_pin", default=False)),
        "editorial_priority": str(event.get("editorial_priority") or "normal"),
        "metadata": metadata,
        "source": {
            "source_name": source_name,
            "source_dataset": source_dataset,
            "source_event_id": source_event_id,
            "source_cemsid": source.get("source_cemsid"),
            "source_event_type": source.get("source_event_type") or nycif.get("event_type"),
            "source_agency": source.get("source_agency") or nycif.get("event_agency"),
            "source_url": source.get("source_url"),
            "source_first_seen": source.get("source_first_seen"),
            "source_last_seen": source.get("source_last_seen"),
            "source_active": bool(source.get("source_active", True)),
            "raw_record": raw,
        },
        "classification": {
            "public_category": category or "general",
            "public_subtype": subtype,
            "classification_reason": str(
                _first(event, "classification.classification_reason", "nycif.classification_reason", default="unspecified")
            ),
            "classifier_version": _first(event, "classification.classifier_version", "nycif.classification_version"),
            "confidence": _first(event, "classification.confidence", default=None),
            "source_event_type": source.get("source_event_type") or nycif.get("event_type"),
            "source_agency": source.get("source_agency") or nycif.get("event_agency"),
        },
        "quality": {
            "quality_status": str(_first(event, "quality.quality_status", default="VALID")),
            "quality_flags": flags if isinstance(flags, list) else [],
            "public_display_status": str(_first(event, "quality.public_display_status", default="FULL_TIME")),
            "details": details if isinstance(details, dict) else {},
        },
    }


def post_atomic_batch(target_url, service_key, payload, timeout=120):
    request = urllib.request.Request(
        f"{target_url}/rest/v1/rpc/nycif_apply_staging_event_batch",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "apikey": service_key,
            "authorization": f"Bearer {service_key}",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SupabaseRPCError(f"atomic RPC failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SupabaseRPCError(f"atomic RPC connection failed: {exc.reason}") from exc
    result = json.loads(body)
    if not isinstance(result, dict) or result.get("transaction") != "committed":
        raise SupabaseRPCError("atomic RPC returned an invalid success document")
    return result


def execute_write(canonical_events, allow_expire=False, simulate_failure=False):
    project_ref, target_url = validate_write_target()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_key:
        raise WriteGuardError("SUPABASE_SERVICE_ROLE_KEY is required in the environment")
    normalized = [normalize_event(event) for event in canonical_events]
    source_names = {event["source"]["source_name"] for event in normalized}
    if len(source_names) != 1:
        raise ValueError("one atomic batch must contain exactly one source_name")
    return post_atomic_batch(
        target_url,
        service_key,
        {
            "p_events": normalized,
            "p_source_name": next(iter(source_names)),
            "p_allow_expire": allow_expire,
            "p_simulate_failure": simulate_failure,
            "p_expected_project_ref": project_ref,
        },
    )


def compare_to_supabase(canonical_events, supabase_state):
    existing = supabase_state.get("occurrences", {})

    report = {
        "actions": {key: 0 for key in ACTIONS},
        "identity": {
            "duplicate_ids": 0,
            "missing_ids": 0,
            "orphan_sources": 0,
        },
        "classification": {
            "category_changes": 0,
            "subtype_changes": 0,
        },
        "quality": {
            "new_flags": 0,
            "resolved_flags": 0,
            "missing_quality_rows": 0,
        },
        "location": {
            "coordinate_changes": 0,
            "map_state_changes": 0,
        },
    }

    seen = set()
    for event in canonical_events:
        key = occurrence_key(event)
        if not key:
            report["identity"]["missing_ids"] += 1
            continue
        if key in seen:
            report["identity"]["duplicate_ids"] += 1
            continue
        seen.add(key)
        report["actions"]["UPDATE" if key in existing else "INSERT"] += 1

    for key in existing:
        if key not in seen:
            report["actions"]["EXPIRE"] += 1

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--supabase-snapshot")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-expire", action="store_true")
    parser.add_argument("--simulate-failure", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    canonical = extract_events(load_json(Path(args.input)))
    if args.write:
        result = execute_write(canonical, args.allow_expire, args.simulate_failure)
        report = {
            "run_type": "controlled_staging_write",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_count": len(canonical),
            **result,
            "database_write_performed": True,
        }
    else:
        supabase = load_supabase_snapshot(
            Path(args.supabase_snapshot) if args.supabase_snapshot else None
        )

        report = {
            "run_type": "dry_run",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_count": len(canonical),
            **compare_to_supabase(canonical, supabase),
            "database_write_performed": False,
        }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
