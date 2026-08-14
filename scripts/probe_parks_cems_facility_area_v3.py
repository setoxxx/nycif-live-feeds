#!/usr/bin/env python3
"""Read-only V3 Parks/CEMS facility-area recovery probe.

This probe tests a two-stage official-source chain without publishing geometry:

TVPP exact parent park name + borough
  -> NYC Parks Properties exact name + borough
  -> unique GISPROPNUM
  -> NYC Parks Athletic Facilities same GISPROPNUM
  -> exact sport token + field number

The result is facility-area evidence only. Athletic Facilities supplies polygon
geometry; this probe never converts that polygon to a point or centroid and
never grants exact-pin/publication authority.
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
    from scripts.probe_parks_cems_athletic_facilities_v2 import (
        DATASET_ID as ATHLETIC_DATASET_ID,
        fetch_facilities,
        normalized_field_number,
        official_descriptor,
        split_tvpp_location,
    )
    from scripts.sync_nyc_open_data import date_key, fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_clock import nyc_today_iso
    from probe_parks_cems_athletic_facilities_v2 import (
        DATASET_ID as ATHLETIC_DATASET_ID,
        fetch_facilities,
        normalized_field_number,
        official_descriptor,
        split_tvpp_location,
    )
    from sync_nyc_open_data import date_key, fetch_raw_rows

PARK_PROPERTIES_DATASET_ID = "enfh-gkve"
PARK_PROPERTIES_URL = f"https://data.cityofnewyork.us/resource/{PARK_PROPERTIES_DATASET_ID}.json"
PAGE_SIZE = 5000
PROPERTY_NAME_FIELDS = (
    "signname",
    "name311",
    "propertyname",
    "property_name",
    "park_name",
    "name",
)
BOROUGH_CODES = {"B", "M", "Q", "R", "X"}
BOROUGH_ALIASES = {
    "brooklyn": "B",
    "kings": "B",
    "manhattan": "M",
    "new york": "M",
    "queens": "Q",
    "bronx": "X",
    "the bronx": "X",
    "staten island": "R",
    "richmond": "R",
}


def fetch_park_properties() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = urllib.parse.urlencode({"$limit": PAGE_SIZE, "$offset": offset})
        request = urllib.request.Request(
            f"{PARK_PROPERTIES_URL}?{query}",
            headers={"User-Agent": "NYCIF-location-recovery/1.2"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.load(response)
        if not isinstance(page, list):
            raise RuntimeError("Parks Properties source did not return a JSON array")
        rows.extend(item for item in page if isinstance(item, dict))
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
    return rows


def _first(row: dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def borough_code(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.upper() in BOROUGH_CODES:
        return raw.upper()
    return BOROUGH_ALIASES.get(normalize_text_legacy(raw), "")


def property_borough_code(row: dict[str, Any]) -> str:
    gispropnum = _first(row, "gispropnum", "gis_prop_num", "parknum")
    if gispropnum and gispropnum[0].upper() in BOROUGH_CODES:
        return gispropnum[0].upper()
    return borough_code(_first(row, "borough", "boro"))


def property_names(row: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for field in PROPERTY_NAME_FIELDS:
        value = row.get(field)
        normalized = normalize_text_legacy(value)
        if normalized:
            values.add(normalized)
    return values


def descriptor_contains_sport(descriptor: Any, official_sport: Any) -> bool:
    descriptor_norm = normalize_text_legacy(descriptor)
    sport_norm = normalize_text_legacy(official_sport)
    if not descriptor_norm or not sport_norm:
        return False
    return f" {sport_norm} " in f" {descriptor_norm} "


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
        park_name, descriptor = split
        code = borough_code(row.get("event_borough") or row.get("borough") or row.get("boro"))
        key = "|".join((code, normalize_text_legacy(park_name), normalize_text_legacy(descriptor)))
        item = claims.setdefault(
            key,
            {
                "borough_code": code,
                "park_name": park_name,
                "facility_descriptor": descriptor,
                "field_number_token": normalized_field_number(
                    str(descriptor).replace("-", " ").replace("_", " ")
                ),
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


def audit_claims(
    claims: dict[str, dict[str, Any]],
    properties: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
) -> dict[str, Any]:
    property_schema: Counter[str] = Counter()
    property_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    property_rows_by_gispropnum: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in properties:
        property_schema.update(row.keys())
        gispropnum = _first(row, "gispropnum", "gis_prop_num", "parknum")
        code = property_borough_code(row)
        if not gispropnum or not code:
            continue
        property_rows_by_gispropnum[gispropnum].append(row)
        for name in property_names(row):
            property_index[(code, name)].add(gispropnum)

    athletic_schema: Counter[str] = Counter()
    facilities_by_gispropnum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in facilities:
        athletic_schema.update(row.keys())
        _, _, _, gispropnum = official_descriptor(row)
        if gispropnum:
            facilities_by_gispropnum[gispropnum].append(row)

    dispositions: Counter[str] = Counter()
    property_resolved_count = 0
    facility_area_candidate_count = 0
    facility_area_candidates_with_geometry = 0
    occurrence_coverage = 0
    matches: list[dict[str, Any]] = []

    for key in sorted(claims):
        claim = claims[key]
        code = str(claim.get("borough_code") or "")
        park_norm = normalize_text_legacy(claim.get("park_name"))
        descriptor = claim.get("facility_descriptor") or ""
        field_number = str(claim.get("field_number_token") or "").strip()
        property_ids = sorted(property_index.get((code, park_norm), set())) if code else []

        evidence = None
        if not code:
            disposition = "CLAIM_BOROUGH_MISSING"
        elif not property_ids:
            disposition = "PROPERTY_NAME_BOROUGH_NOT_FOUND"
        elif len(property_ids) > 1:
            disposition = "AMBIGUOUS_PROPERTY_GISPROPNUM"
        else:
            gispropnum = property_ids[0]
            property_resolved_count += 1
            facility_rows = facilities_by_gispropnum.get(gispropnum, [])
            candidate_rows: list[dict[str, Any]] = []
            for row in facility_rows:
                official_sport, official_number, _, _ = official_descriptor(row)
                if (
                    field_number
                    and official_number
                    and field_number == official_number
                    and descriptor_contains_sport(descriptor, official_sport)
                ):
                    candidate_rows.append(row)

            if len(candidate_rows) == 1:
                row = candidate_rows[0]
                official_sport, official_number, system, _ = official_descriptor(row)
                geometry = row.get("multipolygon") or row.get("the_geom") or row.get("shape") or row.get("geometry")
                geometry_present = geometry is not None
                facility_area_candidate_count += 1
                occurrence_coverage += int(claim.get("occurrence_count") or 0)
                if geometry_present:
                    facility_area_candidates_with_geometry += 1
                disposition = "UNIQUE_OFFICIAL_PROPERTY_AND_FACILITY_AREA"
                evidence = {
                    "official_gispropnum": gispropnum,
                    "official_system_id": system or None,
                    "official_primary_sport": official_sport or None,
                    "official_field_number": official_number or None,
                    "geometry_present": geometry_present,
                    "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
                    "geometry_role": "facility_area_evidence_only",
                    "centroid_generated": False,
                    "point_generated": False,
                }
            elif len(candidate_rows) > 1:
                disposition = "AMBIGUOUS_MULTIPLE_FACILITY_ROWS"
            elif not facility_rows:
                disposition = "PROPERTY_RESOLVED_NO_ATHLETIC_FACILITIES"
            elif not field_number:
                disposition = "PROPERTY_RESOLVED_FIELD_NUMBER_MISSING"
            else:
                disposition = "PROPERTY_RESOLVED_NO_EXACT_SPORT_FIELD_MATCH"

        dispositions[disposition] += 1
        matches.append({**claim, "disposition": disposition, "official_match": evidence})

    return {
        "schema_version": "NYCIF_PARKS_CEMS_FACILITY_AREA_RECOVERY_PROBE_V3",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "park_properties_dataset": PARK_PROPERTIES_DATASET_ID,
        "park_properties_url": PARK_PROPERTIES_URL,
        "athletic_facilities_dataset": ATHLETIC_DATASET_ID,
        "read_only": True,
        "promotion_allowed": False,
        "publication_eligible_count": 0,
        "exact_pin_candidate_count": 0,
        "centroid_generated_count": 0,
        "point_generated_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "official_property_rows": len(properties),
        "official_athletic_facility_rows": len(facilities),
        "observed_property_schema_fields": sorted(property_schema),
        "observed_athletic_schema_fields": sorted(athletic_schema),
        "unique_tvpp_facility_claims": len(claims),
        "property_resolved_claim_count": property_resolved_count,
        "facility_area_candidate_count": facility_area_candidate_count,
        "facility_area_candidates_with_geometry": facility_area_candidates_with_geometry,
        "occurrence_coverage_by_facility_area_candidates": occurrence_coverage,
        "disposition_counts": dict(sorted(dispositions.items())),
        "matches": matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    raw = fetch_raw_rows()
    claims = current_parks_claims(raw, nyc_today_iso())
    properties = fetch_park_properties()
    facilities = fetch_facilities()
    report = audit_claims(claims, properties, facilities)
    report["raw_tvpp_rows_loaded"] = len(raw)

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    print(
        json.dumps(
            {
                "park_properties_dataset": report["park_properties_dataset"],
                "athletic_facilities_dataset": report["athletic_facilities_dataset"],
                "official_property_rows": report["official_property_rows"],
                "official_athletic_facility_rows": report["official_athletic_facility_rows"],
                "unique_tvpp_facility_claims": report["unique_tvpp_facility_claims"],
                "property_resolved_claim_count": report["property_resolved_claim_count"],
                "facility_area_candidate_count": report["facility_area_candidate_count"],
                "facility_area_candidates_with_geometry": report["facility_area_candidates_with_geometry"],
                "occurrence_coverage_by_facility_area_candidates": report["occurrence_coverage_by_facility_area_candidates"],
                "publication_eligible_count": report["publication_eligible_count"],
                "exact_pin_candidate_count": report["exact_pin_candidate_count"],
                "centroid_generated_count": report["centroid_generated_count"],
                "point_generated_count": report["point_generated_count"],
                "disposition_counts": report["disposition_counts"],
                "observed_property_schema_fields": report["observed_property_schema_fields"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
