#!/usr/bin/env python3
"""Read-only V2 probe of NYC Parks Athletic Facilities for CEMS permit recovery.

NYC Parks documents qnem-b8re as the athletic-facility layer used by CEMS for
Parks athletic permits. Its SYSTEM field is the unique identifier for an
athletic facility. This probe tests the strongest public identifier bridge
available in the two source systems: exact TVPP CEMSID -> official SYSTEM.

No match produced here is publication authority. A unique identifier match is
only a candidate for the exact-site evidence contract. Sport and field-number
agreement are recorded as an independent sanity check. Conflicts, duplicate
SYSTEM rows, missing geometry, and unmatched identifiers remain blocked.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_clock import nyc_today_iso
    from scripts.sync_nyc_open_data import date_key, fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_clock import nyc_today_iso
    from sync_nyc_open_data import date_key, fetch_raw_rows

DATASET_ID = "qnem-b8re"
SOURCE_URL = f"https://data.cityofnewyork.us/resource/{DATASET_ID}.json"
PAGE_SIZE = 5000


def fetch_facilities() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({"$limit": PAGE_SIZE, "$offset": offset})
        request = urllib.request.Request(
            f"{SOURCE_URL}?{query}",
            headers={"User-Agent": "NYCIF-location-recovery/1.1"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.load(response)
        if not isinstance(page, list):
            raise RuntimeError("athletic-facilities source did not return a JSON array")
        rows.extend(item for item in page if isinstance(item, dict))
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
    return rows


def split_tvpp_location(value: Any) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if ":" not in text:
        return None
    parent, facility = text.split(":", 1)
    parent = parent.strip()
    facility = facility.strip()
    if not parent or not facility:
        return None
    return parent, facility


def normalized_field_number(value: Any) -> str:
    text = normalize_text_legacy(value)
    match = re.search(r"(?:^|\s)(\d{1,3})(?:\s|$)", text)
    return str(int(match.group(1))) if match else ""


def facility_descriptor(value: str) -> tuple[str, str]:
    raw = str(value or "").strip()
    sport_raw = re.split(r"[-_/]", raw, maxsplit=1)[0].strip()
    sport = normalize_text_legacy(sport_raw)
    number = normalized_field_number(raw.replace("-", " ").replace("_", " "))
    return sport, number


def _first(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def official_descriptor(row: dict[str, Any]) -> tuple[str, str, str, str]:
    sport = _first(row, "primary_sport", "primarysport", "sport")
    number = normalized_field_number(_first(row, "field_number", "fieldnumber", "field_no", "fieldnum"))
    system = _first(row, "system", "system_id", "facility_id")
    gispropnum = _first(row, "gispropnum", "gis_prop_num", "parknum")
    return normalize_text_legacy(sport), number, system, gispropnum


def current_parks_claims(rows: list[dict[str, Any]], today_nyc: str) -> dict[str, dict[str, Any]]:
    claims: dict[str, dict[str, Any]] = {}
    for row in rows:
        if date_key(row.get("start_date_time")) < today_nyc:
            continue
        if normalize_text_legacy(row.get("event_agency")) != normalize_text_legacy("Parks Department"):
            continue
        split = split_tvpp_location(row.get("event_location") or row.get("location"))
        if split is None:
            continue
        park, descriptor = split
        sport, number = facility_descriptor(descriptor)
        key = "|".join((normalize_text_legacy(park), normalize_text_legacy(descriptor)))
        item = claims.setdefault(
            key,
            {
                "park_name": park,
                "facility_descriptor": descriptor,
                "sport_token": sport,
                "field_number_token": number,
                "occurrence_count": 0,
                "source_event_ids": [],
                "source_cemsids": set(),
            },
        )
        item["occurrence_count"] += 1
        source_id = str(row.get("event_id") or row.get("source_event_id") or "").strip()
        if source_id and len(item["source_event_ids"]) < 20:
            item["source_event_ids"].append(source_id)
        cemsids = row.get("cemsid") or row.get("source_cemsid") or []
        if not isinstance(cemsids, list):
            cemsids = [part.strip() for part in str(cemsids).split(",") if part.strip()]
        for cemsid in cemsids:
            value = str(cemsid).strip()
            if value and value != "0":
                item["source_cemsids"].add(value)
    for item in claims.values():
        item["source_cemsids"] = sorted(item["source_cemsids"])
    return claims


def descriptor_status(claim: dict[str, Any], row: dict[str, Any]) -> str:
    official_sport, official_number, _, _ = official_descriptor(row)
    claim_sport = normalize_text_legacy(claim.get("sport_token"))
    claim_number = str(claim.get("field_number_token") or "").strip()

    sport_conflict = bool(claim_sport and official_sport and claim_sport != official_sport)
    number_conflict = bool(claim_number and official_number and claim_number != official_number)
    if sport_conflict or number_conflict:
        return "CONFLICT"

    sport_complete = bool(claim_sport and official_sport)
    number_complete = bool(claim_number and official_number)
    if sport_complete and number_complete:
        return "CONSISTENT"
    return "INCOMPLETE"


def audit_claims(claims: dict[str, dict[str, Any]], facilities: list[dict[str, Any]]) -> dict[str, Any]:
    by_system: dict[str, list[dict[str, Any]]] = defaultdict(list)
    schema_fields: Counter[str] = Counter()
    for row in facilities:
        schema_fields.update(row.keys())
        _, _, system, _ = official_descriptor(row)
        if system:
            by_system[system].append(row)

    duplicate_system_values = sorted(system for system, rows in by_system.items() if len(rows) > 1)
    source_cemsids = sorted({c for claim in claims.values() for c in claim.get("source_cemsids", [])})
    overlapping_system_ids = sorted(set(source_cemsids) & set(by_system))

    disposition_counts: Counter[str] = Counter()
    identifier_candidate_count = 0
    descriptor_consistent_count = 0
    descriptor_conflict_count = 0
    descriptor_incomplete_count = 0
    geometry_present_count = 0
    occurrence_coverage = 0
    matches: list[dict[str, Any]] = []

    for key in sorted(claims):
        claim = claims[key]
        candidate_pairs: list[tuple[str, dict[str, Any]]] = []
        seen_rows: set[int] = set()
        for cemsid in claim.get("source_cemsids", []):
            for row in by_system.get(cemsid, []):
                marker = id(row)
                if marker not in seen_rows:
                    seen_rows.add(marker)
                    candidate_pairs.append((cemsid, row))

        evidence = None
        if len(candidate_pairs) == 1:
            matched_cemsid, row = candidate_pairs[0]
            state = descriptor_status(claim, row)
            disposition = f"CEMSID_SYSTEM_UNIQUE_DESCRIPTOR_{state}"
            identifier_candidate_count += 1
            occurrence_coverage += int(claim["occurrence_count"])
            if state == "CONSISTENT":
                descriptor_consistent_count += 1
            elif state == "CONFLICT":
                descriptor_conflict_count += 1
            else:
                descriptor_incomplete_count += 1

            official_sport, official_number, system, gispropnum = official_descriptor(row)
            geometry = row.get("multipolygon") or row.get("the_geom") or row.get("shape") or row.get("geometry")
            geometry_present = geometry is not None
            if geometry_present:
                geometry_present_count += 1
            evidence = {
                "matched_source_cemsid": matched_cemsid,
                "official_system_id": system or None,
                "official_gispropnum": gispropnum or None,
                "official_primary_sport": _first(row, "primary_sport", "primarysport", "sport") or None,
                "official_field_number": _first(row, "field_number", "fieldnumber", "field_no", "fieldnum") or None,
                "descriptor_status": state,
                "geometry_present": geometry_present,
                "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
            }
        elif len(candidate_pairs) > 1:
            disposition = "AMBIGUOUS_CEMSID_SYSTEM_ROWS"
        elif not claim.get("source_cemsids"):
            disposition = "SOURCE_CEMSID_MISSING"
        else:
            disposition = "CEMSID_SYSTEM_NOT_FOUND"

        disposition_counts[disposition] += 1
        matches.append({**claim, "disposition": disposition, "official_match": evidence})

    return {
        "schema_version": "NYCIF_PARKS_CEMS_ATHLETIC_FACILITY_RECOVERY_PROBE_V2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset": DATASET_ID,
        "source_url": SOURCE_URL,
        "authority_note": (
            "NYC Parks documents SYSTEM as the unique identifier for an athletic facility; "
            "this probe measures exact identifier overlap only and does not grant publication authority."
        ),
        "read_only": True,
        "promotion_allowed": False,
        "publication_eligible_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "official_facility_rows": len(facilities),
        "official_rows_with_system": sum(len(rows) for rows in by_system.values()),
        "official_unique_system_values": len(by_system),
        "duplicate_official_system_value_count": len(duplicate_system_values),
        "duplicate_official_system_values_sample": duplicate_system_values[:50],
        "observed_schema_fields": sorted(schema_fields),
        "unique_tvpp_facility_claims": len(claims),
        "claims_with_cemsid": sum(bool(claim.get("source_cemsids")) for claim in claims.values()),
        "unique_source_cemsids": len(source_cemsids),
        "unique_source_cemsids_matching_official_system": len(overlapping_system_ids),
        "identifier_candidate_count": identifier_candidate_count,
        "descriptor_consistent_identifier_candidates": descriptor_consistent_count,
        "descriptor_conflict_identifier_candidates": descriptor_conflict_count,
        "descriptor_incomplete_identifier_candidates": descriptor_incomplete_count,
        "identifier_candidates_with_geometry": geometry_present_count,
        "occurrence_coverage_by_identifier_candidates": occurrence_coverage,
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "matches": matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = fetch_raw_rows()
    claims = current_parks_claims(raw, nyc_today_iso())
    facilities = fetch_facilities()
    report = audit_claims(claims, facilities)
    report["raw_tvpp_rows_loaded"] = len(raw)
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "source_dataset": report["source_dataset"],
                "official_facility_rows": report["official_facility_rows"],
                "official_unique_system_values": report["official_unique_system_values"],
                "duplicate_official_system_value_count": report["duplicate_official_system_value_count"],
                "unique_tvpp_facility_claims": report["unique_tvpp_facility_claims"],
                "unique_source_cemsids": report["unique_source_cemsids"],
                "unique_source_cemsids_matching_official_system": report["unique_source_cemsids_matching_official_system"],
                "identifier_candidate_count": report["identifier_candidate_count"],
                "descriptor_consistent_identifier_candidates": report["descriptor_consistent_identifier_candidates"],
                "descriptor_conflict_identifier_candidates": report["descriptor_conflict_identifier_candidates"],
                "descriptor_incomplete_identifier_candidates": report["descriptor_incomplete_identifier_candidates"],
                "identifier_candidates_with_geometry": report["identifier_candidates_with_geometry"],
                "occurrence_coverage_by_identifier_candidates": report["occurrence_coverage_by_identifier_candidates"],
                "publication_eligible_count": report["publication_eligible_count"],
                "disposition_counts": report["disposition_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
