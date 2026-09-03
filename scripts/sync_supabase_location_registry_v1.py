#!/usr/bin/env python3
"""Build and optionally apply the durable Supabase location-registry payload.

Reads canonical V3 event geography. It never edits location_cache or event rows.
Approximate geography remains approximate and review-required; this sync cannot
certify an event pin. Reused locations preserve the authority that originally
certified the durable place instead of replacing it with circular reuse metadata.
Unprovenanced reused rows are counted and omitted from the payload; they do not
abort the persist step or invent an authority. Locations are unique on
location_id and aliases are unique on (location_id, normalized_alias) before
apply so one INSERT cannot hit the same ON CONFLICT row twice.
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


def alias_source_datasets(row: dict[str, Any]) -> list[str]:
    """Return every source dataset that observed this alias, including merges."""
    datasets: list[str] = []
    primary = str(row.get("source_dataset") or "").strip()
    if primary:
        datasets.append(primary)
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for item in metadata.get("merged_source_datasets") or []:
        text = str(item or "").strip()
        if text and text not in datasets:
            datasets.append(text)
    return datasets


def prefer_location(existing: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep exact over approximate and never certify circular reuse authority."""
    if existing is None:
        kept = dict(candidate)
    elif existing.get("precision") == "approximate" and candidate.get("precision") == "exact":
        kept = dict(candidate)
    else:
        kept = dict(existing)

    existing_auth = str((existing or {}).get("location_authority") or "").strip()
    candidate_auth = str(candidate.get("location_authority") or "").strip()
    kept_auth = str(kept.get("location_authority") or "").strip()
    if kept_auth == REUSE_AUTHORITY:
        for auth in (existing_auth, candidate_auth):
            if auth and auth != REUSE_AUTHORITY:
                kept["location_authority"] = auth
                break
    elif candidate_auth == REUSE_AUTHORITY and existing_auth and existing_auth != REUSE_AUTHORITY:
        kept["location_authority"] = existing_auth
    return kept


def merge_alias(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    exist_count = int(existing.get("occurrence_count") or 0)
    incoming_count = int(incoming.get("occurrence_count") or 0)
    merged = dict(existing)
    if incoming_count > exist_count:
        merged["raw_alias"] = incoming.get("raw_alias") or existing.get("raw_alias")
        if incoming.get("source_dataset"):
            merged["source_dataset"] = incoming.get("source_dataset")
    merged["occurrence_count"] = exist_count + incoming_count
    datasets: list[str] = []
    for row in (existing, incoming):
        for dataset in alias_source_datasets(row):
            if dataset not in datasets:
                datasets.append(dataset)
    metadata: dict[str, Any] = {}
    if isinstance(existing.get("metadata"), dict):
        metadata.update(existing["metadata"])
    if isinstance(incoming.get("metadata"), dict):
        metadata.update(incoming["metadata"])
    if len(datasets) > 1:
        metadata["merged_source_datasets"] = datasets
    merged["metadata"] = metadata
    return merged


def unique_locations(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    kept: dict[str, dict[str, Any]] = {}
    merged = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        loc_id = str(row.get("location_id") or "")
        if not loc_id:
            continue
        if loc_id in kept:
            merged += 1
            kept[loc_id] = prefer_location(kept[loc_id], row)
        else:
            kept[loc_id] = prefer_location(None, row)
    return list(sorted(kept.values(), key=lambda item: str(item["location_id"]))), merged


def unique_aliases(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    kept: dict[tuple[str, str], dict[str, Any]] = {}
    merged = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        loc_id = str(row.get("location_id") or "")
        normalized = str(row.get("normalized_alias") or "").strip()
        if not loc_id or not normalized:
            continue
        key = (loc_id, normalized)
        if key in kept:
            merged += 1
            kept[key] = merge_alias(kept[key], row)
        else:
            kept[key] = dict(row)
    return [kept[key] for key in sorted(kept)], merged


def unique_registry_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Collapse one-command ON CONFLICT keys before the RPC sees the payload."""
    locations, location_merged = unique_locations(list(payload.get("locations") or []))
    aliases, alias_merged = unique_aliases(list(payload.get("aliases") or []))
    unique_payload = dict(payload)
    unique_payload["locations"] = locations
    unique_payload["aliases"] = aliases
    return unique_payload, {
        "duplicate_location_id_rows_merged": location_merged,
        "duplicate_alias_key_rows_merged": alias_merged,
    }


def duplicate_conflict_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the location_id / alias keys that would fail Postgres ON CONFLICT."""
    location_ids = [
        str(row.get("location_id") or "")
        for row in payload.get("locations") or []
        if isinstance(row, dict)
    ]
    location_counts = Counter(location_id for location_id in location_ids if location_id)
    duplicate_location_ids = sorted(key for key, count in location_counts.items() if count > 1)
    alias_keys = [
        (str(row.get("location_id") or ""), str(row.get("normalized_alias") or ""))
        for row in payload.get("aliases") or []
        if isinstance(row, dict)
    ]
    alias_counts = Counter(key for key in alias_keys if key[0] and key[1])
    duplicate_alias_keys = [
        {"location_id": loc_id, "normalized_alias": alias, "count": count}
        for (loc_id, alias), count in sorted(alias_counts.items())
        if count > 1
    ]
    return {
        "duplicate_location_ids": duplicate_location_ids,
        "duplicate_location_id_extra_rows": sum(location_counts[key] - 1 for key in duplicate_location_ids),
        "duplicate_alias_keys": duplicate_alias_keys,
        "duplicate_alias_key_extra_rows": sum(item["count"] - 1 for item in duplicate_alias_keys),
        "would_fail_on_conflict": bool(duplicate_location_ids or duplicate_alias_keys),
    }


def registry_qa_pass(locations: list[dict[str, Any]], payload: dict[str, Any] | None = None) -> bool:
    conflicts = duplicate_conflict_keys(payload or {"locations": locations, "aliases": []})
    return (
        len(locations) > 0
        and all(item.get("precision") in {"exact", "approximate"} for item in locations)
        and all(item.get("location_authority") != REUSE_AUTHORITY for item in locations)
        and not conflicts["would_fail_on_conflict"]
    )


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

        locations[loc_id] = prefer_location(locations.get(loc_id), candidate)
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
    payload, dedupe = unique_registry_payload(payload)
    locations_out = payload["locations"]
    aliases_out = payload["aliases"]
    conflicts = duplicate_conflict_keys(payload)
    report = {
        "schema_version": "NYCIF_LOCATION_REGISTRY_SYNC_V1_REPORT",
        "generated_at_utc": generated,
        "location_count": len(locations_out),
        "alias_count": len(aliases_out),
        "precision_observation_counts": dict(sorted(precision_counts.items())),
        "authority_observation_counts": dict(sorted(authority_counts.items())),
        "observed_authority_counts": dict(sorted(observed_authority_counts.items())),
        "id_basis_counts": dict(sorted(id_basis_counts.items())),
        "skipped_counts": dict(sorted(skipped.items())),
        "duplicate_location_id_rows_merged": dedupe["duplicate_location_id_rows_merged"],
        "duplicate_alias_key_rows_merged": dedupe["duplicate_alias_key_rows_merged"],
        "locations_unique_on_location_id": not conflicts["duplicate_location_ids"],
        "aliases_unique_on_location_id_normalized_alias": not conflicts["duplicate_alias_keys"],
        "approximate_certified_count": sum(
            1 for item in locations_out
            if item["precision"] == "approximate" and item["metadata"].get("exact_pin_eligible")
        ),
        "circular_reuse_authority_count": sum(
            1 for item in locations_out if item["location_authority"] == REUSE_AUTHORITY
        ),
        "protected_cache_modified": False,
        "event_rows_modified": False,
        "qa_pass": registry_qa_pass(locations_out, payload),
    }
    return payload, report


def apply_payload(payload: dict[str, Any]) -> dict[str, Any]:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required with --apply")
    unique_payload, _ = unique_registry_payload(payload)
    conflicts = duplicate_conflict_keys(unique_payload)
    if conflicts["would_fail_on_conflict"]:
        raise RuntimeError(
            "location registry payload still has ON CONFLICT duplicate keys: "
            f"{conflicts}"
        )
    body = json.dumps({"payload": unique_payload}).encode()
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
