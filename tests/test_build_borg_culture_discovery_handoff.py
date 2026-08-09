from __future__ import annotations

import unittest

from scripts.build_borg_culture_discovery_handoff import build_handoff
from scripts.validate_borg_culture_discovery import validate


def source_payloads():
    base_records = []
    profiles = []
    languages = []
    for i in range(262):
        code = f"NTA{i:03d}"
        name = "Marine Park-Mill Basin-Bergen Beach" if i == 0 else f"Test NTA {i}"
        base_records.append({
            "nta2020": code,
            "nta_name": name,
            "geometry": {"type": "Polygon", "coordinates": []},
            "source_dataset_id": "9nt8-h7nd",
            "source_release": "26B",
        })
        profiles.append({
            "nta2020": code,
            "acs_vintage": 2024,
            "profile_state": "READY",
            "tracts_expected": 1,
            "tracts_aggregated": 1,
            "metrics": [{"variable_id": "B01003_001E", "estimate": 100, "margin_of_error": 10}],
            "culture_classification_power": "NONE",
            "boundary_creation_power": "NONE",
        })
        languages.append({
            "nta2020": code,
            "acs_vintage": 2024,
            "profile_state": "READY",
            "tracts_expected": 1,
            "tracts_aggregated": 1,
            "universe": "Population age 5 years and over",
            "metrics": [{"variable_id": "C16001_002E", "estimate": 80, "margin_of_error": 9}],
            "culture_classification_power": "NONE",
            "boundary_creation_power": "NONE",
        })
    return (
        {"contract": "nycif.culture-base-geography.v1", "records": base_records},
        {"contract": "nycif.community-demographic-profile.v1", "records": profiles},
        {"contract": "nycif.community-language-profile.v1", "records": languages},
    )


class BorgCultureHandoffBuilderTests(unittest.TestCase):
    def test_builds_valid_262_nta_handoff_with_separate_language_universe(self):
        base, profiles, languages = source_payloads()
        handoff = build_handoff(base_registry=base, profiles=profiles, language_profiles=languages)
        self.assertEqual(handoff["record_count"], 524)
        summary = validate(handoff)
        self.assertEqual(summary["base_count"], 262)
        self.assertEqual(summary["profile_count"], 262)
        marine = next(
            row for row in handoff["records"]
            if row.get("type") == "COMMUNITY_PROFILE" and row.get("nta2020") == "NTA000"
        )
        self.assertEqual(marine["language_profile"]["universe"], "Population age 5 years and over")
        self.assertEqual(marine["language_profile"]["culture_classification_power"], "NONE")

    def test_rejects_language_state_mismatch(self):
        base, profiles, languages = source_payloads()
        languages["records"][0]["profile_state"] = "UNAVAILABLE"
        with self.assertRaises(ValueError):
            build_handoff(base_registry=base, profiles=profiles, language_profiles=languages)

    def test_rejects_demographic_culture_power(self):
        base, profiles, languages = source_payloads()
        languages["records"][0]["culture_classification_power"] = "CREATE_LABEL"
        with self.assertRaises(ValueError):
            build_handoff(base_registry=base, profiles=profiles, language_profiles=languages)


if __name__ == "__main__":
    unittest.main()
