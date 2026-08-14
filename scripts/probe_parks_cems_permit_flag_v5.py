#!/usr/bin/env python3
"""Read-only V5 Parks/CEMS permit-flag facility-area probe.

V4 proved that PRIMARY_SPORT is a coded domain (for example BKB/TNS/SFB/SCR),
not the English CEMS descriptor taxonomy. NYC Parks Athletic Facilities also
publishes sport-specific permitability columns. This probe therefore tests the
source's booking semantics directly:

exact park property + borough -> unique GISPROPNUM
+ exact CEMS field number -> official rows with same FIELD_NUMBER
+ explicit sport permit flag -> unique athletic facility area.

A unique result is evidence only. No event becomes publication eligible and no
point/centroid is derived from the facility polygon.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.gps_identity import normalize_text_legacy
    from scripts.nyc_clock import nyc_today_iso
    from scripts.probe_parks_cems_athletic_facilities_v2 import (
        fetch_facilities,
        normalized_field_number,
        official_descriptor,
    )
    from scripts.probe_parks_cems_facility_area_v3 import (
        current_parks_claims,
        fetch_park_properties,
        _first,
    )
    from scripts.probe_parks_cems_facility_numbering_v4 import (
        build_facility_index,
        build_property_index,
        raw_facility_summary,
    )
    from scripts.sync_nyc_open_data import fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_clock import nyc_today_iso
    from probe_parks_cems_athletic_facilities_v2 import (
        fetch_facilities,
        normalized_field_number,
        official_descriptor,
    )
    from probe_parks_cems_facility_area_v3 import (
        current_parks_claims,
        fetch_park_properties,
        _first,
    )
    from probe_parks_cems_facility_numbering_v4 import (
        build_facility_index,
        build_property_index,
        raw_facility_summary,
    )
    from sync_nyc_open_data import fetch_raw_rows

# Fields whose NYC Open Data descriptions state that a permit for the named
# activity can be acquired for the facility. Broad CEMS labels map only to the
# documented permit subtypes for that same sport family.
SPORT_PERMIT_FIELDS: dict[str, tuple[str, ...]] = {
    "baseball": ("adult_baseball", "ll_baseb_12andunder", "ll_baseb_13andolder"),
    "basketball": ("basketball",),
    "bocce": ("bocce",),
    "cricket": ("cricket",),
    "flag football": ("flagfootball",),
    "football": ("adult_football", "youth_football", "flagfootball", "wheelchairfootball"),
    "frisbee": ("frisbee",),
    "handball": ("handball",),
    "hockey": ("hockey",),
    "kickball": ("kickball",),
    "lacrosse": ("lacrosse",),
    "netball": ("netball",),
    "pickleball": ("pickleball",),
    "rugby": ("rugby",),
    "soccer": ("regulation_soccer", "nonregulation_soccer"),
    "softball": ("adult_softball", "ll_softball"),
    "t ball": ("t_ball",),
    "tennis": ("tennis",),
    "track": ("track_and_field",),
    "track and field": ("track_and_field",),
    "volleyball": ("volleyball",),
}


def descriptor_sport_token(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered.startswith("t-ball") or lowered.startswith("t ball"):
        return "t ball"
    head = re.split(r"[-_/]", raw, maxsplit=1)[0]
    return normalize_text_legacy(head)


def permit_flag_truthy(value: Any) -> bool:
    if value is True:
        return True
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value == 1
    return str(value or "").strip().lower() in {"true", "1"}


def permitted_for_sport(row: dict[str, Any], sport_token: str) -> tuple[bool, list[str]]:
    fields = SPORT_PERMIT_FIELDS.get(sport_token, ())
    matched = [field for field in fields if permit_flag_truthy(row.get(field))]
    return bool(matched), matched


def probe_claims(
    claims: dict[str, dict[str, Any]],
    properties: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
) -> dict[str, Any]:
    property_index = build_property_index(properties)
    facility_index = build_facility_index(facilities)

    dispositions: Counter[str] = Counter()
    sport_tokens: Counter[str] = Counter()
    permit_flag_raw_values: dict[str, Counter[str]] = {
        field: Counter() for fields in SPORT_PERMIT_FIELDS.values() for field in fields
    }
    for row in facilities:
        for field in permit_flag_raw_values:
            if field in row:
                permit_flag_raw_values[field][str(row.get(field))] += 1

    property_resolved = 0
    numbered_claims = 0
    mapped_sport_claims = 0
    field_number_row_match_claims = 0
    unique_permitted_area_candidates = 0
    unique_permitted_area_candidates_with_geometry = 0
    occurrence_coverage = 0
    samples: dict[str, list[dict[str, Any]]] = {}
    matches: list[dict[str, Any]] = []

    for key in sorted(claims):
        claim = claims[key]
        code = str(claim.get("borough_code") or "")
        park_norm = normalize_text_legacy(claim.get("park_name"))
        property_ids = sorted(property_index.get((code, park_norm), set())) if code else []
        descriptor = claim.get("facility_descriptor") or ""
        sport_token = descriptor_sport_token(descriptor)
        field_number = str(claim.get("field_number_token") or "").strip()
        sport_tokens[sport_token or "<EMPTY>"] += 1
        evidence = None

        if not code:
            disposition = "CLAIM_BOROUGH_MISSING"
        elif not property_ids:
            disposition = "PROPERTY_NAME_BOROUGH_NOT_FOUND"
        elif len(property_ids) > 1:
            disposition = "AMBIGUOUS_PROPERTY_GISPROPNUM"
        else:
            property_resolved += 1
            gispropnum = property_ids[0]
            rows = facility_index.get(gispropnum, [])
            if not rows:
                disposition = "PROPERTY_RESOLVED_NO_ATHLETIC_ROWS"
            elif not field_number:
                disposition = "CLAIM_FIELD_NUMBER_MISSING"
            elif sport_token not in SPORT_PERMIT_FIELDS:
                disposition = "CEMS_SPORT_TOKEN_UNMAPPED"
            else:
                numbered_claims += 1
                mapped_sport_claims += 1
                field_rows: list[dict[str, Any]] = []
                for row in rows:
                    raw_field = _first(row, "field_number", "fieldnumber", "field_no", "fieldnum")
                    if normalized_field_number(raw_field) == field_number:
                        field_rows.append(row)
                if not field_rows:
                    disposition = "NO_OFFICIAL_FIELD_NUMBER_MATCH"
                else:
                    field_number_row_match_claims += 1
                    permit_rows: list[tuple[dict[str, Any], list[str]]] = []
                    for row in field_rows:
                        allowed, matched_fields = permitted_for_sport(row, sport_token)
                        if allowed:
                            permit_rows.append((row, matched_fields))
                    if len(permit_rows) == 1:
                        row, matched_fields = permit_rows[0]
                        official_sport, official_number, system, official_gispropnum = official_descriptor(row)
                        geometry = row.get("multipolygon") or row.get("the_geom") or row.get("shape") or row.get("geometry")
                        geometry_present = geometry is not None
                        unique_permitted_area_candidates += 1
                        occurrence_coverage += int(claim.get("occurrence_count") or 0)
                        if geometry_present:
                            unique_permitted_area_candidates_with_geometry += 1
                        disposition = "UNIQUE_FIELD_NUMBER_AND_PERMITTED_SPORT_AREA"
                        evidence = {
                            "official_gispropnum": official_gispropnum or gispropnum,
                            "official_system_id": system or None,
                            "official_field_number": official_number or None,
                            "official_primary_sport_code": official_sport or None,
                            "matched_permit_fields": matched_fields,
                            "geometry_present": geometry_present,
                            "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
                            "geometry_role": "facility_area_evidence_only",
                            "centroid_generated": False,
                            "point_generated": False,
                        }
                    elif len(permit_rows) > 1:
                        disposition = "AMBIGUOUS_MULTIPLE_PERMITTED_FACILITY_ROWS"
                    else:
                        disposition = "FIELD_NUMBER_ROWS_BUT_SPORT_NOT_PERMITTED"

                    bucket = samples.setdefault(disposition, [])
                    if len(bucket) < 30:
                        bucket.append(
                            {
                                "borough_code": code,
                                "park_name": claim.get("park_name"),
                                "facility_descriptor": descriptor,
                                "sport_token": sport_token,
                                "field_number_token": field_number,
                                "official_gispropnum": gispropnum,
                                "field_number_row_count": len(field_rows),
                                "field_number_rows": [
                                    {
                                        **raw_facility_summary(row),
                                        "matched_permit_fields": permitted_for_sport(row, sport_token)[1],
                                    }
                                    for row in field_rows[:12]
                                ],
                            }
                        )

        dispositions[disposition] += 1
        matches.append({**claim, "sport_token": sport_token, "disposition": disposition, "official_match": evidence})

    return {
        "schema_version": "NYCIF_PARKS_CEMS_PERMIT_FLAG_FACILITY_AREA_PROBE_V5",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "promotion_allowed": False,
        "publication_eligible_count": 0,
        "exact_pin_candidate_count": 0,
        "centroid_generated_count": 0,
        "point_generated_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "unique_tvpp_facility_claims": len(claims),
        "property_resolved_claim_count": property_resolved,
        "numbered_claim_count": numbered_claims,
        "mapped_sport_claim_count": mapped_sport_claims,
        "field_number_row_match_claim_count": field_number_row_match_claims,
        "unique_permitted_area_candidate_count": unique_permitted_area_candidates,
        "unique_permitted_area_candidates_with_geometry": unique_permitted_area_candidates_with_geometry,
        "occurrence_coverage_by_unique_permitted_area_candidates": occurrence_coverage,
        "sport_permit_field_map": {key: list(value) for key, value in sorted(SPORT_PERMIT_FIELDS.items())},
        "sport_token_counts": dict(sport_tokens.most_common()),
        "permit_flag_raw_value_counts": {
            field: dict(counter.most_common()) for field, counter in sorted(permit_flag_raw_values.items())
        },
        "disposition_counts": dict(sorted(dispositions.items())),
        "samples": samples,
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
    report = probe_claims(claims, properties, facilities)
    report["raw_tvpp_rows_loaded"] = len(raw)

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    print(json.dumps({
        "unique_tvpp_facility_claims": report["unique_tvpp_facility_claims"],
        "property_resolved_claim_count": report["property_resolved_claim_count"],
        "mapped_sport_claim_count": report["mapped_sport_claim_count"],
        "field_number_row_match_claim_count": report["field_number_row_match_claim_count"],
        "unique_permitted_area_candidate_count": report["unique_permitted_area_candidate_count"],
        "unique_permitted_area_candidates_with_geometry": report["unique_permitted_area_candidates_with_geometry"],
        "occurrence_coverage_by_unique_permitted_area_candidates": report["occurrence_coverage_by_unique_permitted_area_candidates"],
        "publication_eligible_count": report["publication_eligible_count"],
        "exact_pin_candidate_count": report["exact_pin_candidate_count"],
        "disposition_counts": report["disposition_counts"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
