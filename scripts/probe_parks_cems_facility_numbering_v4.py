#!/usr/bin/env python3
"""Read-only V4 diagnostic for Parks/CEMS facility-numbering semantics.

The V3 official-property chain resolves many TVPP park claims to a unique
GISPROPNUM but currently finds no exact athletic facility rows. This diagnostic
separates field-number alignment from sport-taxonomy alignment so we can learn
why without weakening any publication gate.

It never emits a publication-eligible event, exact pin, centroid, or synthetic
point. All output is diagnostic evidence only.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
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
        descriptor_contains_sport,
        fetch_park_properties,
        property_borough_code,
        property_names,
        _first,
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
        descriptor_contains_sport,
        fetch_park_properties,
        property_borough_code,
        property_names,
        _first,
    )
    from sync_nyc_open_data import fetch_raw_rows


def build_property_index(properties: list[dict[str, Any]]) -> dict[tuple[str, str], set[str]]:
    index: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in properties:
        gispropnum = _first(row, "gispropnum", "gis_prop_num", "parknum")
        code = property_borough_code(row)
        if not gispropnum or not code:
            continue
        for name in property_names(row):
            index[(code, name)].add(gispropnum)
    return index


def build_facility_index(facilities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in facilities:
        _, _, _, gispropnum = official_descriptor(row)
        if gispropnum:
            index[gispropnum].append(row)
    return index


def raw_facility_summary(row: dict[str, Any]) -> dict[str, Any]:
    official_sport, official_number, system, gispropnum = official_descriptor(row)
    return {
        "gispropnum": gispropnum or None,
        "system": system or None,
        "primary_sport_raw": _first(row, "primary_sport", "primarysport", "sport") or None,
        "primary_sport_normalized": official_sport or None,
        "field_number_raw": _first(row, "field_number", "fieldnumber", "field_no", "fieldnum") or None,
        "field_number_normalized": official_number or None,
        "geometry_present": bool(row.get("multipolygon") or row.get("the_geom") or row.get("shape") or row.get("geometry")),
    }


def diagnose_claims(
    claims: dict[str, dict[str, Any]],
    properties: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
) -> dict[str, Any]:
    property_index = build_property_index(properties)
    facility_index = build_facility_index(facilities)

    official_raw_field_values: Counter[str] = Counter()
    official_normalized_field_values: Counter[str] = Counter()
    official_primary_sports: Counter[str] = Counter()
    official_rows_with_normalized_field = 0
    official_rows_without_normalized_field = 0
    for row in facilities:
        raw_field = _first(row, "field_number", "fieldnumber", "field_no", "fieldnum")
        normalized_field = normalized_field_number(raw_field)
        raw_sport = _first(row, "primary_sport", "primarysport", "sport")
        official_raw_field_values[raw_field or "<EMPTY>"] += 1
        official_normalized_field_values[normalized_field or "<EMPTY>"] += 1
        official_primary_sports[raw_sport or "<EMPTY>"] += 1
        if normalized_field:
            official_rows_with_normalized_field += 1
        else:
            official_rows_without_normalized_field += 1

    field_alignment: Counter[str] = Counter()
    unique_field_exact_sport_count = 0
    unique_field_sport_mismatch_count = 0
    ambiguous_field_exact_sport_unique_count = 0
    resolved_claims = 0
    resolved_with_athletic_rows = 0
    resolved_with_claim_field = 0
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sport_pairs: Counter[str] = Counter()

    for key in sorted(claims):
        claim = claims[key]
        code = str(claim.get("borough_code") or "")
        park_norm = normalize_text_legacy(claim.get("park_name"))
        property_ids = sorted(property_index.get((code, park_norm), set())) if code else []
        if len(property_ids) != 1:
            continue

        resolved_claims += 1
        gispropnum = property_ids[0]
        rows = facility_index.get(gispropnum, [])
        claim_field = str(claim.get("field_number_token") or "").strip()
        descriptor = claim.get("facility_descriptor") or ""

        if not rows:
            field_alignment["NO_ATHLETIC_ROWS"] += 1
            continue
        resolved_with_athletic_rows += 1

        if not claim_field:
            field_alignment["CLAIM_FIELD_NUMBER_MISSING"] += 1
            continue
        resolved_with_claim_field += 1

        field_rows: list[dict[str, Any]] = []
        for row in rows:
            raw_field = _first(row, "field_number", "fieldnumber", "field_no", "fieldnum")
            if normalized_field_number(raw_field) == claim_field:
                field_rows.append(row)

        if not field_rows:
            bucket = "NO_OFFICIAL_FIELD_NUMBER_MATCH"
            field_alignment[bucket] += 1
        elif len(field_rows) == 1:
            row = field_rows[0]
            raw_sport = _first(row, "primary_sport", "primarysport", "sport")
            sport_matches = descriptor_contains_sport(descriptor, raw_sport)
            if sport_matches:
                bucket = "UNIQUE_FIELD_NUMBER_EXACT_SPORT"
                unique_field_exact_sport_count += 1
            else:
                bucket = "UNIQUE_FIELD_NUMBER_SPORT_MISMATCH"
                unique_field_sport_mismatch_count += 1
            field_alignment[bucket] += 1
            sport_pairs[f"{normalize_text_legacy(descriptor)} => {normalize_text_legacy(raw_sport)}"] += 1
        else:
            exact_sport_rows = [
                row
                for row in field_rows
                if descriptor_contains_sport(
                    descriptor,
                    _first(row, "primary_sport", "primarysport", "sport"),
                )
            ]
            if len(exact_sport_rows) == 1:
                bucket = "AMBIGUOUS_FIELD_NUMBER_UNIQUE_EXACT_SPORT"
                ambiguous_field_exact_sport_unique_count += 1
            elif len(exact_sport_rows) > 1:
                bucket = "AMBIGUOUS_FIELD_NUMBER_MULTIPLE_EXACT_SPORT"
            else:
                bucket = "AMBIGUOUS_FIELD_NUMBER_NO_EXACT_SPORT"
            field_alignment[bucket] += 1

        if len(samples[bucket]) < 30:
            samples[bucket].append(
                {
                    "borough_code": code,
                    "park_name": claim.get("park_name"),
                    "facility_descriptor": descriptor,
                    "claim_field_number": claim_field or None,
                    "official_gispropnum": gispropnum,
                    "official_facility_row_count": len(rows),
                    "field_number_match_count": len(field_rows),
                    "field_number_match_rows": [raw_facility_summary(row) for row in field_rows[:12]],
                    "available_facility_rows_sample": [raw_facility_summary(row) for row in rows[:12]],
                    "source_cemsids": claim.get("source_cemsids", []),
                }
            )

    return {
        "schema_version": "NYCIF_PARKS_CEMS_FACILITY_NUMBERING_DIAGNOSTIC_V4",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "diagnostic_only": True,
        "promotion_allowed": False,
        "publication_eligible_count": 0,
        "exact_pin_candidate_count": 0,
        "centroid_generated_count": 0,
        "point_generated_count": 0,
        "public_map_modified": False,
        "location_cache_modified": False,
        "unique_tvpp_facility_claims": len(claims),
        "property_resolved_claim_count": resolved_claims,
        "property_resolved_with_athletic_rows_count": resolved_with_athletic_rows,
        "property_resolved_with_claim_field_number_count": resolved_with_claim_field,
        "official_athletic_facility_rows": len(facilities),
        "official_rows_with_normalized_field_number": official_rows_with_normalized_field,
        "official_rows_without_normalized_field_number": official_rows_without_normalized_field,
        "field_alignment_counts": dict(sorted(field_alignment.items())),
        "unique_field_number_exact_sport_count": unique_field_exact_sport_count,
        "unique_field_number_sport_mismatch_count": unique_field_sport_mismatch_count,
        "ambiguous_field_number_unique_exact_sport_count": ambiguous_field_exact_sport_unique_count,
        "top_official_field_number_raw_values": official_raw_field_values.most_common(40),
        "top_official_field_number_normalized_values": official_normalized_field_values.most_common(40),
        "top_official_primary_sports": official_primary_sports.most_common(40),
        "top_unique_field_sport_pairs": sport_pairs.most_common(100),
        "samples": dict(samples),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    raw = fetch_raw_rows()
    claims = current_parks_claims(raw, nyc_today_iso())
    properties = fetch_park_properties()
    facilities = fetch_facilities()
    report = diagnose_claims(claims, properties, facilities)
    report["raw_tvpp_rows_loaded"] = len(raw)

    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")

    summary = {
        "unique_tvpp_facility_claims": report["unique_tvpp_facility_claims"],
        "property_resolved_claim_count": report["property_resolved_claim_count"],
        "property_resolved_with_athletic_rows_count": report["property_resolved_with_athletic_rows_count"],
        "property_resolved_with_claim_field_number_count": report["property_resolved_with_claim_field_number_count"],
        "official_athletic_facility_rows": report["official_athletic_facility_rows"],
        "official_rows_with_normalized_field_number": report["official_rows_with_normalized_field_number"],
        "official_rows_without_normalized_field_number": report["official_rows_without_normalized_field_number"],
        "field_alignment_counts": report["field_alignment_counts"],
        "unique_field_number_exact_sport_count": report["unique_field_number_exact_sport_count"],
        "unique_field_number_sport_mismatch_count": report["unique_field_number_sport_mismatch_count"],
        "ambiguous_field_number_unique_exact_sport_count": report["ambiguous_field_number_unique_exact_sport_count"],
        "top_official_field_number_raw_values": report["top_official_field_number_raw_values"][:20],
        "top_official_primary_sports": report["top_official_primary_sports"][:20],
        "publication_eligible_count": report["publication_eligible_count"],
        "exact_pin_candidate_count": report["exact_pin_candidate_count"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
