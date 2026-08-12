#!/usr/bin/env python3
"""Build the production BORG Culture discovery handoff from protected source artifacts.

Only Layer 1 base geography and Layer 1B aggregate Community Profile material
are projected here. Layer 2/3 records must be added by their separate certified
pipelines; review-required cultural-area candidates are intentionally excluded.
"""

from __future__ import annotations

import argparse
from typing import Any

from scripts.borg_cli_paths import read_workspace_json, write_workspace_json

CONTRACT = "nycif.borg-culture-discovery-handoff.v1"
EXPECTED_NTAS = 262
LANGUAGE_CONTRACT = "nycif.community-language-profile.v1"


def _validate_source_contracts(
    base_registry: dict[str, Any],
    profiles: dict[str, Any],
    language_profiles: dict[str, Any],
) -> None:
    expected = (
        (base_registry, "nycif.culture-base-geography.v1", "base geography"),
        (profiles, "nycif.community-demographic-profile.v1", "Community Profile"),
        (language_profiles, LANGUAGE_CONTRACT, "language profile"),
    )
    for payload, contract, label in expected:
        if payload.get("contract") != contract:
            raise ValueError(f"Unsupported {label} contract")


def _index_profile_rows(rows: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    if len(rows) != EXPECTED_NTAS:
        raise ValueError(f"BORG Culture handoff requires 262 {label} records")
    indexed = {str(row["nta2020"]): row for row in rows}
    if len(indexed) != EXPECTED_NTAS:
        raise ValueError(f"Duplicate NTA ids in {label}")
    return indexed


def _validate_demographic_authority(code: str, core: dict[str, Any], language: dict[str, Any]) -> None:
    if core.get("culture_classification_power") != "NONE" or language.get("culture_classification_power") != "NONE":
        raise ValueError(f"NTA {code} demographic source has Culture classification power")
    if core.get("boundary_creation_power") != "NONE" or language.get("boundary_creation_power") != "NONE":
        raise ValueError(f"NTA {code} demographic source has boundary creation power")
    if core.get("profile_state") != language.get("profile_state"):
        raise ValueError(f"NTA {code} core/language terminal-state mismatch")


def _records_for_nta(base: dict[str, Any], core: dict[str, Any], language: dict[str, Any]) -> list[dict[str, Any]]:
    code = str(base["nta2020"])
    _validate_demographic_authority(code, core, language)
    return [
        {
            "type": "BASE_GEOGRAPHY",
            "nta2020": code,
            "nta_name": base.get("nta_name"),
            "geometry": base.get("geometry"),
            "source_dataset_id": base.get("source_dataset_id"),
            "source_release": base.get("source_release"),
            "residential": core.get("profile_state") != "NOT_APPLICABLE",
        },
        {
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
        },
    ]


def build_handoff(*, base_registry: dict[str, Any], profiles: dict[str, Any], language_profiles: dict[str, Any]) -> dict[str, Any]:
    _validate_source_contracts(base_registry, profiles, language_profiles)
    base_rows = base_registry.get("records") or []
    if len(base_rows) != EXPECTED_NTAS:
        raise ValueError("BORG Culture handoff requires 262 base records")
    profile_by_nta = _index_profile_rows(profiles.get("records") or [], label="core-profile")
    language_by_nta = _index_profile_rows(language_profiles.get("records") or [], label="language-profile")

    records: list[dict[str, Any]] = []
    for base in sorted(base_rows, key=lambda row: str(row["nta2020"])):
        code = str(base["nta2020"])
        core = profile_by_nta.get(code)
        language = language_by_nta.get(code)
        if core is None or language is None:
            raise ValueError(f"NTA {code} missing core or language profile")
        records.extend(_records_for_nta(base, core, language))

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
        base_registry=read_workspace_json(args.base_registry),
        profiles=read_workspace_json(args.profiles),
        language_profiles=read_workspace_json(args.language_profiles),
    )
    write_workspace_json(args.output, result)
    print(f"Built BORG Culture discovery handoff with {result['record_count']} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
