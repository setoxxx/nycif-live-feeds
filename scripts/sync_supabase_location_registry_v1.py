#!/usr/bin/env python3
"""Build and optionally apply the durable Supabase location-registry payload.

Reads canonical V3 event geography. It never edits location_cache or event rows.
Approximate geography remains approximate and review-required; this sync cannot
certify an event pin. Reused locations preserve the authority that originally
certified the durable place instead of replacing it with circular reuse metadata.
Unprovenanced reused rows are counted and omitted from the payload; they do not
abort the persist step or invent an authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
PAYLOAD = ROOT / "data" / "location_registry_sync_v1_payload.json"
REPORT = ROOT / "data" / "location_registry_sync_v1_report.json"
REUSE_AUTHORITY = "durable_location_registry_v1"


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "rows", "items", "records", "occurrences", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_alias(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()
    return re.sub(r"\s+", " ", text)


def source(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("source") if isinstance(row.get("source"), dict) else {}


def source_dataset(row: dict[str, Any]) -> str:
    s = source(row)
    return str(row.get("source_dataset") or s.get("dataset") or "unknown").strip()


def raw_location(row: dict[str, Any]) -> str:
    n = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return str(
        n.get("source_location_text")
        or row.get("event_location")
        or row.get("location")
        or row.get("venue_name")
        or row.get("address")
        or ""
    ).strip()


def reuse_source_authority(row: dict[str, Any]) -> str:
    """Return a non-circular original authority if this occurrence recorded one."""
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    original = str(
        nycif.get("location_reuse_source_authority")
        or row.get("location_reuse_source_authority")
        or ""
    ).strip()
    if not original or original == REUSE_AUTHORITY:
        return ""
    return original


def effective_location_authority(row: dict[str, Any]) -> tuple[str, str] | None:
    """Return durable authority plus the authority observed on this occurrence.

    A reused occurrence is allowed to say that its current placement came from
    the durable registry, but syncing that occurrence back must retain the
    original authority that certified the stored location. Otherwise repeated
    reuse would erase provenance and make the registry self-referential.

    Unprovenanced reuse is skipped rather than raised so a READY transaction can
    still persist provenanced locations. Missing original authority is never
    invented and never certified into the registry payload.
    """
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    observed = str(nycif.get("location_authority") or row.get("location_authority") or "unknown")
    if observed == REUSE_AUTHORITY:
        original = reuse_source_authority(row)
        if not original:
            return None
        return original, observed
    return observed, observed


def stable_location_id(row: dict[str, Any], lat: float, lng: float) -> tuple[str, str]:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    s = source(row)
    existing = row.get("location_id") or nycif.get("location_id")
    if existing:
        return str(existing), "existing_location_id"
    cemsid = row.get("source_cemsid") or s.get("source_cemsid") or s.get("cemsid")
    if cemsid:
        return f"cems:{str(cemsid).strip()}", "source_cemsid"
    dataset = source_dataset(row)
    venue_id = row.get("venue_id") or s.get("venue_id")
    if venue_id:
        return f"{dataset}:venue:{str(venue_id).strip()}", "venue_id"
    facility_id = row.get("facility_id") or row.get("facility_number") or s.get("facility_id")
    if facility_id:
        return f"{dataset}:facility:{str(facility_id).strip()}", "facility_id"
    name = normalize_alias(raw_location(row))
    borough = normalize_alias(row.get("borough"))
    digest = hashlib.sha256(f"{borough}|{name}|{lat:.5f}|{lng:.5f}".encode()).hexdigest()[:24]
    return f"locv1:{digest}", "deterministic_location_signature"


def load_rows(path: Path) -> list[dict[str, Any]]:
    return extract_rows(json.loads(path.read_text(encoding="utf-8")))


def build_payload(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    locations: dict[str, dict[str, Any]] = {}
    alias_counts: Counter[tuple[str, str, str]] = Counter()
    alias_raw: dict[tuple[str, str, str], str] = {}
    authority_counts: Counter[str] = Counter()
    observed_authority_counts: Counter[str] = Counter()
    precision_counts: Counter[str] = Counter()
    id_basis_counts: Counter[str] = Counter()
    skipped: Counter[str] = Counter()

    for row in rows:
        nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
        state = str(nycif.get("map_eligibility_state") or row.get("map_eligibility_state") or "")
        certified = nycif.get("certified_pin") is True or row.get("certified_pin") is True
        if state not in {"MAP_READY", "GENERAL_AREA"}:
            skipped["not_geography_assigned"] += 1
            continue
        lat = finite(row.get("latitude") if row.get("latitude") is not None else row.get("lat"))
        lng = finite(row.get("longitude") if row.get("longitude") is not None else row.get("lng"))
        if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            skipped["invalid_or_missing_coordinates"] += 1
            continue
        if state == "MAP_READY" and not certified:
            skipped["map_ready_without_certification"] += 1
            continue
        if state == "GENERAL_AREA" and certified:
            skipped["approximate_certification_contradiction"] += 1
            continue

        precision = "exact" if state == "MAP_READY" else "approximate"
        resolved = effective_location_authority(row)
        if resolved is None:
            skipped["reused_location_missing_source_authority"] += 1
            continue
        authority, observed_authority = resolved
        loc_id, basis = stable_location_id(row, lat, lng)
        id_basis_counts[basis] += 1
        raw = raw_location(row)
        canonical_name = raw or str(row.get("borough") or "Unnamed location")
        evidence = row.get("location_evidence") if isinstance(row.get("location_evidence"), dict) else {}
        confidence = finite(evidence.get("confidence") or nycif.get("location_confidence"))
        s = source(row)

        candidate = {
            "location_id": loc_id,
            "borough": row.get("borough"),
            "canonical_name": canonical_name,
            "canonical_full_name": raw or canonical_name,
            "facility_name": row.get("facility_name") or row.get("venue_name"),
            "location_type": "event_location",
            "facility_type": row.get("facility_type"),
            "source_cemsid": row.get("source_cemsid") or s.get("source_cemsid") or s.get("cemsid"),
            "street_address": row.get("street_address") or row.get("address"),
            "street_segment": row.get("street_segment"),
            "cross_streets": row.get("cross_streets"),
            "review_required": precision != "exact",
            "latitude": lat,
            "longitude": lng,
            "precision": precision,
            "location_authority": authority,
            "confidence": confidence,
            "last_seen": generated,
            "metadata": {
                "sync_version": "location_registry_v1",
                "id_basis": basis,
                "exact_pin_eligible": precision == "exact",
                "observed_location_authority": observed_authority,
                "reused_from_registry": observed_authority == REUSE_AUTHORITY,
            },
        }

        existing = locations.get(loc_id)
        if existing is None or (existing["precision"] == "approximate" and precision == "exact"):
            locations[loc_id] = candidate
        authority_counts[authority] += 1
        observed_authority_counts[observed_authority] += 1
        precision_counts[precision] += 1

        normalized = normalize_alias(raw)
        if normalized:
            dataset = source_dataset(row)
            key = (loc_id, normalized, dataset)
            alias_counts[key] += 1
            alias_raw[key] = raw

    aliases = [
        {
            "location_id": loc_id,
            "raw_alias": alias_raw[(loc_id, normalized, dataset)],
            "normalized_alias": normalized,
            "source_dataset": dataset,
            "occurrence_count": count,
            "first_seen": generated,
            "last_seen": generated,
            "metadata": {"sync_version": "location_registry_v1"},
        }
        for (loc_id, normalized, dataset), count in sorted(alias_counts.items())
    ]
    payload = {
        "schema_version": "NYCIF_LOCATION_REGISTRY_SYNC_V1",
        "generated_at_utc": generated,
        "locations": list(sorted(locations.values(), key=lambda x: x["location_id"])),
        "aliases": aliases,
    }
    report = {
        "schema_version": "NYCIF_LOCATION_REGISTRY_SYNC_V1_REPORT",
        "generated_at_utc": generated,
        "location_count": len(locations),
        "alias_count": len(aliases),
        "precision_observation_counts": dict(sorted(precision_counts.items())),
        "authority_observation_counts": dict(sorted(authority_counts.items())),
        "observed_authority_counts": dict(sorted(observed_authority_counts.items())),
        "id_basis_counts": dict(sorted(id_basis_counts.items())),
        "skipped_counts": dict(sorted(skipped.items())),
        "approximate_certified_count": sum(
            1 for item in locations.values()
            if item["precision"] == "approximate" and item["metadata"].get("exact_pin_eligible")
        ),
        "circular_reuse_authority_count": sum(
            1 for item in locations.values() if item["location_authority"] == REUSE_AUTHORITY
        ),
        "protected_cache_modified": False,
        "event_rows_modified": False,
        "qa_pass": (
            len(locations) > 0
            and all(item["precision"] in {"exact", "approximate"} for item in locations.values())
            and all(item["location_authority"] != REUSE_AUTHORITY for item in locations.values())
        ),
    }
    return payload, report


def apply_payload(payload: dict[str, Any]) -> dict[str, Any]:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required with --apply")
    body = json.dumps({"payload": payload}).encode()
    request = Request(
        f"{base}/rest/v1/rpc/sync_location_registry_v1",
        data=body,
        method="POST",
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=120) as response:  # nosec B310 - configured HTTPS Supabase project URL
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply through service-role-only sync_location_registry_v1 RPC")
    args = parser.parse_args()
    payload, report = build_payload(load_rows(CANONICAL))
    PAYLOAD.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.apply:
        report["apply_result"] = apply_payload(payload)
        report["applied"] = True
    else:
        report["applied"] = False
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if (
        not report["qa_pass"]
        or report["approximate_certified_count"] != 0
        or report["circular_reuse_authority_count"] != 0
    ):
        raise RuntimeError(f"location registry sync QA failed: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
