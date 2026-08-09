#!/usr/bin/env python3
"""Validate BORG Culture discovery handoff records.

Fail-closed rules:
- exactly 262 BASE_GEOGRAPHY records;
- every base NTA has exactly one COMMUNITY_PROFILE terminal state unless explicitly nonresidential;
- Cultural areas require independent non-Census source evidence;
- public places must be ACCEPTED only;
- absence of a cultural area is valid and never backfilled from demographics.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXPECTED_NTAS = 262
PROFILE_STATES = {"READY", "STALE", "UNAVAILABLE", "NOT_APPLICABLE"}
PUBLIC_PLACE_DISPOSITIONS = {"ACCEPTED"}
CENSUS_SOURCE_MARKERS = {"acs", "census", "american community survey"}


def _is_census_source(source: dict[str, Any]) -> bool:
    haystack = " ".join(str(source.get(k, "")) for k in ("source_family", "authority", "source_ref", "source_url")).lower()
    return any(marker in haystack for marker in CENSUS_SOURCE_MARKERS)


def validate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("contract") != "nycif.borg-culture-discovery-handoff.v1":
        raise ValueError("Unsupported BORG Culture discovery contract")

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Every record must be an object")
        by_type[str(row.get("type"))].append(row)

    base = by_type["BASE_GEOGRAPHY"]
    if len(base) != EXPECTED_NTAS:
        raise ValueError(f"Expected {EXPECTED_NTAS} BASE_GEOGRAPHY records, found {len(base)}")

    nta_codes = [str(row.get("nta2020", "")) for row in base]
    if any(not code for code in nta_codes):
        raise ValueError("BASE_GEOGRAPHY missing nta2020")
    if len(set(nta_codes)) != EXPECTED_NTAS:
        raise ValueError("Duplicate BASE_GEOGRAPHY nta2020 values")

    profile_rows = by_type["COMMUNITY_PROFILE"]
    profile_by_nta = Counter(str(row.get("nta2020", "")) for row in profile_rows)
    unknown_profile_ntas = sorted(set(profile_by_nta) - set(nta_codes))
    if unknown_profile_ntas:
        raise ValueError(f"COMMUNITY_PROFILE references unknown NTAs: {unknown_profile_ntas[:10]}")
    duplicate_profiles = sorted(code for code, count in profile_by_nta.items() if count != 1)
    if duplicate_profiles:
        raise ValueError(f"Expected exactly one COMMUNITY_PROFILE per represented NTA: {duplicate_profiles[:10]}")

    base_by_nta = {str(row["nta2020"]): row for row in base}
    missing_profiles: list[str] = []
    for code, base_row in base_by_nta.items():
        residential = bool(base_row.get("residential", True))
        if residential and profile_by_nta.get(code, 0) != 1:
            missing_profiles.append(code)
    if missing_profiles:
        raise ValueError(f"Residential NTAs missing COMMUNITY_PROFILE: {missing_profiles[:10]}")

    for row in profile_rows:
        state = str(row.get("profile_state", ""))
        if state not in PROFILE_STATES:
            raise ValueError(f"Invalid COMMUNITY_PROFILE state: {state!r}")
        if row.get("culture_label") or row.get("cultural_area_name"):
            raise ValueError("COMMUNITY_PROFILE cannot carry a cultural-area classification")

    for area in by_type["CULTURAL_AREA"]:
        sources = area.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"CULTURAL_AREA {area.get('area_id')} lacks source evidence")
        if all(_is_census_source(src) for src in sources if isinstance(src, dict)):
            raise ValueError(f"CULTURAL_AREA {area.get('area_id')} is Census-only")

    for place in by_type["VERIFIED_PLACE"]:
        disposition = str(place.get("disposition", ""))
        if disposition not in PUBLIC_PLACE_DISPOSITIONS:
            raise ValueError(f"Public VERIFIED_PLACE must be ACCEPTED, found {disposition!r}")
        if not place.get("business_id") or not place.get("location_id"):
            raise ValueError("VERIFIED_PLACE missing canonical business/location identity")
        if not place.get("why_included"):
            raise ValueError("VERIFIED_PLACE missing why_included")

    return {
        "base_count": len(base),
        "profile_count": len(profile_rows),
        "cultural_area_count": len(by_type["CULTURAL_AREA"]),
        "verified_place_count": len(by_type["VERIFIED_PLACE"]),
        "silent_loss": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    summary = validate(payload)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
