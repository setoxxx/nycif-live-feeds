#!/usr/bin/env python3
"""Build the production BORG Culture discovery handoff from protected source artifacts.

Only Layer 1 base geography and Layer 1B aggregate Community Profile material
are projected here. Layer 2/3 records must be added by their separate certified
pipelines; review-required cultural-area candidates are intentionally excluded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CONTRACT = "nycif.borg-culture-discovery-handoff.v1"
EXPECTED_NTAS = 262
LANGUAGE_CONTRACT = "nycif.community-language-profile.v1"


def build_handoff(*, base_registry: dict[str, Any], profiles: dict[str, Any], language_profiles: dict[str, Any]) -> dict[str, Any]:
    if base_registry.get("contract") != "nycif.culture-base-geography.v1":
        raise ValueError("Unsupported base geography contract")
    if profiles.get("contract") != "nycif.community-demographic-profile.v1":
        raise ValueError("Unsupported Community Profile contract")
    if language_profiles.get("contract") != LANGUAGE_CONTRACT:
        raise ValueError("Unsupported language profile contract")

    base_rows = base_registry.get("records") or []
    profile_rows = profiles.get("records") or []
    language_rows = language_profiles.get("records") or []
    if len(base_rows) != EXPECTED_NTAS or len(profile_rows) != EXPECTED_NTAS or len(language_rows) != EXPECTED_NTAS:
        raise ValueError("BORG Culture handoff requires 262 base, core-profile, and language-profile records")

    profile_by_nta = {str(row["nta2020"]): row for row in profile_rows}
    language_by_nta = {str(row["nta2020"]): row for row in language_rows}
    if len(profile_by_nta) != EXPECTED_NTAS or len(language_by_nta) != EXPECTED_NTAS:
        raise ValueError("Duplicate NTA ids in source profiles")

    records: list[dict[str, Any]] = []
    for base in sorted(base_rows, key=lambda row: str(row["nta2020"])):
        code = str(base["nta2020"])
        core = profile_by_nta.get(code)
        language = language_by_nta.get(code)
        if core is None or language is None:
            raise ValueError(f"NTA {code} missing core or language profile")
        if core.get("culture_classification_power") != "NONE" or language.get("culture_classification_power") != "NONE":
            raise ValueError(f"NTA {code} demographic source has Culture classification power")
        if core.get("boundary_creation_power") != "NONE" or language.get("boundary_creation_power") != "NONE":
            raise ValueError(f"NTA {code} demographic source has boundary creation power")
        if core.get("profile_state") != language.get("profile_state"):
            raise ValueError(f"NTA {code} core/language terminal-state mismatch")

        records.append({
            "type": "BASE_GEOGRAPHY",
            "nta2020": code,
            "nta_name": base.get("nta_name"),
            "geometry": base.get("geometry"),
            "source_dataset_id": base.get("source_dataset_id"),
            "source_release": base.get("source_release"),
            "residential": core.get("profile_state") != "NOT_APPLICABLE",
        })
        records.append({
            "type": "COMMUNITY_PROFILE",
            "nta2020": code,
            "acs_vintage": core.get("acs_vintage"),
            "profile_state": core.get("profile_state"),
            "metrics": core.get("metrics") or [],
            "source_tract_accounting": {
                "expected": core.get("tracts_expected"),
                "aggregated": core.get("tracts_aggregated"),
            },
            "language_profile": {
                "contract": LANGUAGE_CONTRACT,
                "profile_state": language.get("profile_state"),
                "universe": language.get("universe"),
                "metrics": language.get("metrics") or [],
                "source_tract_accounting": {
                    "expected": language.get("tracts_expected"),
                    "aggregated": language.get("tracts_aggregated"),
                },
                "culture_classification_power": "NONE",
                "boundary_creation_power": "NONE",
            },
            "culture_classification_power": "NONE",
            "boundary_creation_power": "NONE",
        })

    return {
        "contract": CONTRACT,
        "source_materialization_contract": "nycif.culture-geography-materialization.v5",
        "record_count": len(records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-registry", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--language-profiles", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = build_handoff(
        base_registry=json.loads(Path(args.base_registry).read_text(encoding="utf-8")),
        profiles=json.loads(Path(args.profiles).read_text(encoding="utf-8")),
        language_profiles=json.loads(Path(args.language_profiles).read_text(encoding="utf-8")),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Built BORG Culture discovery handoff with {result['record_count']} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
