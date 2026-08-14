#!/usr/bin/env python3
"""Read-only V6 strict Parks/CEMS sport-field facility-area probe.

V5 demonstrated a high-yield official chain but also exposed parser risks:
subfacility names can contain unrelated numbers, field identifiers may carry
suffixes such as 01A/01B, and a single TVPP location field can contain multiple
facilities. V6 tightens parsing rather than loosening authority.

A V6 candidate requires:
  * exact parent park/property name + borough -> one GISPROPNUM;
  * one non-composite descriptor with exactly one recognized sport family;
  * exactly one adjacent sport/field identifier pair;
  * exact suffix-preserving FIELD_NUMBER agreement;
  * explicit sport permitability on the official row;
  * exactly one active official SYSTEM row;
  * official MultiPolygon geometry.

Candidates remain evidence only. No exact pin, point, centroid, cache mutation,
feed mutation, or publication authority is produced.
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
    from scripts.probe_parks_cems_athletic_facilities_v2 import fetch_facilities, official_descriptor
    from scripts.probe_parks_cems_facility_area_v3 import current_parks_claims, fetch_park_properties, _first
    from scripts.probe_parks_cems_facility_numbering_v4 import build_facility_index, build_property_index
    from scripts.probe_parks_cems_permit_flag_v5 import SPORT_PERMIT_FIELDS, permitted_for_sport
    from scripts.sync_nyc_open_data import fetch_raw_rows
except ModuleNotFoundError:  # pragma: no cover
    from gps_identity import normalize_text_legacy
    from nyc_clock import nyc_today_iso
    from probe_parks_cems_athletic_facilities_v2 import fetch_facilities, official_descriptor
    from probe_parks_cems_facility_area_v3 import current_parks_claims, fetch_park_properties, _first
    from probe_parks_cems_facility_numbering_v4 import build_facility_index, build_property_index
    from probe_parks_cems_permit_flag_v5 import SPORT_PERMIT_FIELDS, permitted_for_sport
    from sync_nyc_open_data import fetch_raw_rows

SPORT_PATTERN = re.compile(
    r"(?i)(?<![a-z])(?:"
    r"(?P<track_and_field>track\s+and\s+field)|"
    r"(?P<flag_football>flag\s*football)|"
    r"(?P<t_ball>t(?:ee)?[-\s]?ball)|"
    r"(?P<baseball>baseball)|"
    r"(?P<basketball>basketball)|"
    r"(?P<bocce>bocce)|"
    r"(?P<cricket>cricket)|"
    r"(?P<football>football)|"
    r"(?P<frisbee>frisbee)|"
    r"(?P<handball>handball)|"
    r"(?P<hockey>hockey)|"
    r"(?P<kickball>kickball)|"
    r"(?P<lacrosse>lacrosse)|"
    r"(?P<netball>netball)|"
    r"(?P<pickleball>pickleball)|"
    r"(?P<rugby>rugby)|"
    r"(?P<soccer>soccer)|"
    r"(?P<softball>softball)|"
    r"(?P<tennis>tennis)|"
    r"(?P<track>track)|"
    r"(?P<volleyball>volleyball)"
    r")(?![a-z])"
)

CANONICAL_SPORT = {
    "track_and_field": "track and field",
    "flag_football": "flag football",
    "t_ball": "t ball",
    "baseball": "baseball",
    "basketball": "basketball",
    "bocce": "bocce",
    "cricket": "cricket",
    "football": "football",
    "frisbee": "frisbee",
    "handball": "handball",
    "hockey": "hockey",
    "kickball": "kickball",
    "lacrosse": "lacrosse",
    "netball": "netball",
    "pickleball": "pickleball",
    "rugby": "rugby",
    "soccer": "soccer",
    "softball": "softball",
    "tennis": "tennis",
    "track": "track",
    "volleyball": "volleyball",
}

FIELD_ID_PATTERN = re.compile(r"^(?:0*(\d{1,3})([A-Z]?)|([A-Z]))$")
COMPOSITE_LOCATION_PATTERN = re.compile(r",\s*[^,]{1,160}:")


def canonical_field_id(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().upper())
    match = FIELD_ID_PATTERN.fullmatch(text)
    if not match:
        return ""
    if match.group(3):
        return match.group(3)
    number = str(int(match.group(1)))
    suffix = match.group(2) or ""
    return number + suffix


def sport_mentions(descriptor: Any) -> list[tuple[str, int, int]]:
    text = str(descriptor or "")
    mentions: list[tuple[str, int, int]] = []
    for match in SPORT_PATTERN.finditer(text):
        group = next((name for name, value in match.groupdict().items() if value is not None), "")
        sport = CANONICAL_SPORT.get(group, "")
        if sport:
            mentions.append((sport, match.start(), match.end()))
    return mentions


def strict_sport_field_pairs(descriptor: Any) -> list[tuple[str, str, str]]:
    text = str(descriptor or "")
    pairs: list[tuple[str, str, str]] = []
    for sport, start, end in sport_mentions(text):
        tail = text[end : end + 40]
        match = re.match(
            r"(?i)^\s*(?:field\s*)?(?:[-_/:]|\s)+\s*([0-9]{1,3}[A-Z]?|[A-Z])(?=$|[\s,;)/])",
            tail,
        )
        if not match:
            continue
        field_id = canonical_field_id(match.group(1))
        if field_id:
            raw_pair = text[start : end + match.end()]
            pairs.append((sport, field_id, raw_pair.strip()))
    return pairs


def parse_descriptor(descriptor: Any) -> tuple[str, str, str]:
    text = str(descriptor or "").strip()
    if not text:
        return "EMPTY_DESCRIPTOR", "", ""
    if COMPOSITE_LOCATION_PATTERN.search(text):
        return "COMPOSITE_LOCATION_DESCRIPTOR", "", ""

    mentions = sport_mentions(text)
    families = sorted({sport for sport, _, _ in mentions})
    if not families:
        return "NO_RECOGNIZED_SPORT_FAMILY", "", ""
    if len(families) != 1:
        return "MULTIPLE_SPORT_FAMILIES", "", ""

    pairs = strict_sport_field_pairs(text)
    unique_pairs = sorted({(sport, field_id) for sport, field_id, _ in pairs})
    if not unique_pairs:
        return "SPORT_FIELD_PAIR_NOT_FOUND", families[0], ""
    if len(unique_pairs) != 1:
        return "MULTIPLE_SPORT_FIELD_PAIRS", "", ""
    sport, field_id = unique_pairs[0]
    return "PARSED", sport, field_id


def feature_status(row: dict[str, Any]) -> str:
    return normalize_text_legacy(_first(row, "featurestatus", "feature_status", "status"))


def geometry_from_row(row: dict[str, Any]) -> Any:
    return row.get("multipolygon") or row.get("the_geom") or row.get("shape") or row.get("geometry")


def official_field_id(row: dict[str, Any]) -> str:
    return canonical_field_id(_first(row, "field_number", "fieldnumber", "field_no", "fieldnum"))


def probe_claims(
    claims: dict[str, dict[str, Any]],
    properties: list[dict[str, Any]],
    facilities: list[dict[str, Any]],
) -> dict[str, Any]:
    property_index = build_property_index(properties)
    facility_index = build_facility_index(facilities)

    dispositions: Counter[str] = Counter()
    parsed_sports: Counter[str] = Counter()
    parsed_fields: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    occurrence_coverage = 0

    for key in sorted(claims):
        claim = claims[key]
        code = str(claim.get("borough_code") or "")
        park_norm = normalize_text_legacy(claim.get("park_name"))
        property_ids = sorted(property_index.get((code, park_norm), set())) if code else []
        descriptor = claim.get("facility_descriptor") or ""
        parse_state, sport, field_id = parse_descriptor(descriptor)
        evidence = None

        if not code:
            disposition = "CLAIM_BOROUGH_MISSING"
        elif not property_ids:
            disposition = "PROPERTY_NAME_BOROUGH_NOT_FOUND"
        elif len(property_ids) > 1:
            disposition = "AMBIGUOUS_PROPERTY_GISPROPNUM"
        elif parse_state != "PARSED":
            disposition = parse_state
        elif sport not in SPORT_PERMIT_FIELDS:
            disposition = "PARSED_SPORT_WITHOUT_PERMIT_MAPPING"
        else:
            parsed_sports[sport] += 1
            parsed_fields[field_id] += 1
            gispropnum = property_ids[0]
            rows = facility_index.get(gispropnum, [])
            if not rows:
                disposition = "PROPERTY_RESOLVED_NO_ATHLETIC_ROWS"
            else:
                field_rows = [row for row in rows if official_field_id(row) == field_id]
                if not field_rows:
                    disposition = "NO_EXACT_SUFFIX_PRESERVING_FIELD_MATCH"
                else:
                    permit_rows: list[tuple[dict[str, Any], list[str]]] = []
                    for row in field_rows:
                        permitted, fields = permitted_for_sport(row, sport)
                        if permitted:
                            permit_rows.append((row, fields))

                    if not permit_rows:
                        disposition = "FIELD_ROWS_BUT_SPORT_NOT_PERMITTED"
                    elif len(permit_rows) > 1:
                        disposition = "AMBIGUOUS_MULTIPLE_PERMITTED_ROWS"
                    else:
                        row, matched_fields = permit_rows[0]
                        status = feature_status(row)
                        _, _, system, official_gispropnum = official_descriptor(row)
                        geometry = geometry_from_row(row)
                        geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
                        if not status:
                            disposition = "UNIQUE_ROW_STATUS_MISSING"
                        elif status != "active":
                            disposition = "UNIQUE_ROW_NOT_ACTIVE"
                        elif not system:
                            disposition = "UNIQUE_ROW_SYSTEM_ID_MISSING"
                        elif geometry_type != "MultiPolygon":
                            disposition = "UNIQUE_ROW_MULTIPOLYGON_MISSING"
                        else:
                            disposition = "STRICT_UNIQUE_ACTIVE_PERMITTED_FACILITY_AREA"
                            occurrence_coverage += int(claim.get("occurrence_count") or 0)
                            evidence = {
                                "official_gispropnum": official_gispropnum or gispropnum,
                                "official_system_id": system,
                                "official_field_id": official_field_id(row),
                                "official_field_number_raw": _first(
                                    row, "field_number", "fieldnumber", "field_no", "fieldnum"
                                ) or None,
                                "official_primary_sport_code": _first(
                                    row, "primary_sport", "primarysport", "sport"
                                ) or None,
                                "feature_status": _first(
                                    row, "featurestatus", "feature_status", "status"
                                ) or None,
                                "matched_permit_fields": matched_fields,
                                "geometry_present": True,
                                "geometry_type": geometry_type,
                                "geometry_role": "facility_area_evidence_only",
                                "site_validation_state": "candidate_only",
                                "centroid_generated": False,
                                "point_generated": False,
                            }
                            candidates.append(
                                {
                                    "claim_key": key,
                                    "borough_code": code,
                                    "park_name": claim.get("park_name"),
                                    "facility_descriptor": descriptor,
                                    "parsed_sport": sport,
                                    "parsed_field_id": field_id,
                                    "occurrence_count": claim.get("occurrence_count", 0),
                                    "source_event_ids": claim.get("source_event_ids", []),
                                    "source_cemsids": claim.get("source_cemsids", []),
                                    "evidence": evidence,
                                }
                            )

        dispositions[disposition] += 1
        matches.append(
            {
                **claim,
                "strict_parse_state": parse_state,
                "strict_sport": sport or None,
                "strict_field_id": field_id or None,
                "disposition": disposition,
                "official_match": evidence,
            }
        )

    systems = [c["evidence"]["official_system_id"] for c in candidates]
    duplicate_candidate_systems = sorted(
        system for system, count in Counter(systems).items() if system and count > 1
    )

    return {
        "schema_version": "NYCIF_PARKS_CEMS_STRICT_FACILITY_AREA_PROBE_V6",
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
        "strict_facility_area_candidate_count": len(candidates),
        "strict_occurrence_coverage": occurrence_coverage,
        "strict_candidate_unique_system_count": len(set(systems)),
        "duplicate_candidate_system_count": len(duplicate_candidate_systems),
        "duplicate_candidate_systems_sample": duplicate_candidate_systems[:100],
        "parsed_sport_counts": dict(parsed_sports.most_common()),
        "parsed_field_counts": dict(parsed_fields.most_common()),
        "disposition_counts": dict(sorted(dispositions.items())),
        "candidates": candidates,
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

    print(
        json.dumps(
            {
                "unique_tvpp_facility_claims": report["unique_tvpp_facility_claims"],
                "strict_facility_area_candidate_count": report["strict_facility_area_candidate_count"],
                "strict_occurrence_coverage": report["strict_occurrence_coverage"],
                "strict_candidate_unique_system_count": report["strict_candidate_unique_system_count"],
                "duplicate_candidate_system_count": report["duplicate_candidate_system_count"],
                "publication_eligible_count": report["publication_eligible_count"],
                "exact_pin_candidate_count": report["exact_pin_candidate_count"],
                "centroid_generated_count": report["centroid_generated_count"],
                "point_generated_count": report["point_generated_count"],
                "disposition_counts": report["disposition_counts"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
