#!/usr/bin/env python3
"""Read-only probe of NYC Parks Athletic Facilities for CEMS permit recovery.

Dataset qnem-b8re is an official Parks facility layer used by CEMS to book
athletic permits. This probe intentionally does not promote coordinates. It
measures whether current/future Parks Department TVPP facility claims can be
joined deterministically to a unique official athletic-facility row.

A deterministic join requires exact normalized agreement on facility tokens we
can derive from public source text; ambiguous/multiple matches remain blocked.
Geometry is retained only as evidence for later site-validation work.
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
        request = urllib.request.Request(f"{SOURCE_URL}?{query}", headers={"User-Agent": "NYCIF-location-recovery/1.0"})
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
    normalized = normalize_text_legacy(value)
    # Examples: Basketball-01, Soccer-02-Stanton St, Football-01.
    sport = re.split(r"[-_/]", normalized, maxsplit=1)[0].strip()
    number = normalized_field_number(normalized.replace("-", " ").replace("_", " "))
    return sport, number


def _first(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def official_descriptor(row: dict[str, Any]) -> tuple[str, str, str, str]:
    park = _first(row, "signname", "sign_name", "park_name", "propertyname", "property_name")
    sport = _first(row, "primary_sport", "primarysport", "sport", "facility_type", "type")
    number = normalized_field_number(_first(row, "field_number", "fieldnumber", "field_no", "fieldnum"))
    system = _first(row, "system", "system_id", "facility_id")
    return normalize_text_legacy(park), normalize_text_legacy(sport), number, system


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
        item = claims.setdefault(key, {
            "park_name": park,
            "facility_descriptor": descriptor,
            "sport_token": sport,
            "field_number_token": number,
            "occurrence_count": 0,
            "source_event_ids": [],
            "source_cemsids": set(),
        })
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


def audit_claims(claims: dict[str, dict[str, Any]], facilities: list[dict[str, Any]]) -> dict[str, Any]:
    by_park: dict[str, list[tuple[dict[str, Any], tuple[str, str, str, str]]]] = defaultdict(list)
    schema_fields: Counter[str] = Counter()
    for row in facilities:
        schema_fields.update(row.keys())
        desc = official_descriptor(row)
        if desc[0]:
            by_park[desc[0]].append((row, desc))

    disposition_counts: Counter[str] = Counter()
    rows_matched = 0
    occurrence_coverage = 0
    matches: list[dict[str, Any]] = []

    for key in sorted(claims):
        claim = claims[key]
        park_norm = normalize_text_legacy(claim["park_name"])
        sport_norm = normalize_text_legacy(claim["sport_token"])
        field_number = claim["field_number_token"]
        candidates = []
        for row, desc in by_park.get(park_norm, []):
            _, official_sport, official_number, system = desc
            sport_ok = bool(sport_norm and official_sport and sport_norm == official_sport)
            number_ok = bool(field_number and official_number and field_number == official_number)
            if sport_ok and number_ok:
                candidates.append((row, desc))

        if len(candidates) == 1:
            disposition = "UNIQUE_EXACT_TOKENS"
            rows_matched += 1
            occurrence_coverage += int(claim["occurrence_count"])
        elif len(candidates) > 1:
            disposition = "AMBIGUOUS_MULTIPLE_OFFICIAL_ROWS"
        elif park_norm not in by_park:
            disposition = "PARK_NAME_NOT_FOUND"
        elif not sport_norm or not field_number:
            disposition = "INSUFFICIENT_FACILITY_TOKENS"
        else:
            disposition = "NO_EXACT_SPORT_FIELD_MATCH"
        disposition_counts[disposition] += 1

        evidence = None
        if len(candidates) == 1:
            row, desc = candidates[0]
            geometry = row.get("multipolygon") or row.get("the_geom") or row.get("shape") or row.get("geometry")
            evidence = {
                "official_system_id": desc[3] or None,
                "official_park_name": _first(row, "signname", "sign_name", "park_name", "propertyname", "property_name") or None,
                "official_primary_sport": _first(row, "primary_sport", "primarysport", "sport", "facility_type", "type") or None,
                "official_field_number": _first(row, "field_number", "fieldnumber", "field_no", "fieldnum") or None,
                "official_gispropnum": _first(row, "gispropnum", "gis_prop_num", "parknum") or None,
                "geometry_present": geometry is not None,
                "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
            }
        matches.append({**claim, "disposition": disposition, "official_match": evidence})

    return {
        "schema_version": "NYCIF_PARKS_CEMS_ATHLETIC_FACILITY_RECOVERY_PROBE_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_dataset": DATASET_ID,
        "source_url": SOURCE_URL,
        "read_only": True,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "official_facility_rows": len(facilities),
        "observed_schema_fields": sorted(schema_fields),
        "unique_tvpp_facility_claims": len(claims),
        "unique_deterministic_matches": rows_matched,
        "occurrence_coverage_by_unique_matches": occurrence_coverage,
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
    print(json.dumps({
        "source_dataset": report["source_dataset"],
        "official_facility_rows": report["official_facility_rows"],
        "unique_tvpp_facility_claims": report["unique_tvpp_facility_claims"],
        "unique_deterministic_matches": report["unique_deterministic_matches"],
        "occurrence_coverage_by_unique_matches": report["occurrence_coverage_by_unique_matches"],
        "disposition_counts": report["disposition_counts"],
        "observed_schema_fields": report["observed_schema_fields"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
