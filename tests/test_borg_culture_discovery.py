from __future__ import annotations

import unittest

from scripts.validate_borg_culture_discovery import validate


def _base(code: str, name: str, residential: bool = True) -> dict:
    return {
        "type": "BASE_GEOGRAPHY",
        "nta2020": code,
        "nta_name": name,
        "geometry": {"type": "Polygon", "coordinates": []},
        "source_dataset_id": "9nt8-h7nd",
        "source_release": "26B",
        "residential": residential,
    }


def _profile(code: str, state: str = "READY") -> dict:
    return {
        "type": "COMMUNITY_PROFILE",
        "nta2020": code,
        "acs_vintage": 2024,
        "profile_state": state,
        "metrics": [],
    }


def _payload() -> dict:
    base = []
    profiles = []
    for i in range(262):
        code = f"NTA{i:03d}"
        name = "Marine Park-Mill Basin-Bergen Beach" if i == 0 else f"Test NTA {i}"
        base.append(_base(code, name))
        profiles.append(_profile(code))
    return {
        "contract": "nycif.borg-culture-discovery-handoff.v1",
        "records": base + profiles,
    }


class BorgCultureDiscoveryTests(unittest.TestCase):
    def test_marine_park_base_only_is_valid(self):
        payload = _payload()
        summary = validate(payload)
        self.assertEqual(summary["base_count"], 262)
        self.assertEqual(summary["profile_count"], 262)
        self.assertTrue(summary["profile_terminal_accounting_complete"])
        self.assertEqual(summary["cultural_area_count"], 0)
        self.assertEqual(summary["verified_place_count"], 0)
        self.assertEqual(summary["silent_loss"], 0)

    def test_little_haiti_named_area_is_separate_from_profile(self):
        payload = _payload()
        payload["records"].append({
            "type": "CULTURAL_AREA",
            "area_id": "culture-area-little-haiti-brooklyn",
            "public_name": "Little Haiti, Brooklyn",
            "boundary_type": "OFFICIAL_DESIGNATION",
            "boundary_status": "SOURCE_CERTIFIED_GEOMETRY_PENDING",
            "boundary_confidence": "HIGH",
            "sources": [{
                "source_family": "official_certification_designation",
                "authority": "New York City Council",
                "source_ref": "Res 0423-2018",
                "source_url": "https://legistar.council.nyc.gov/",
            }],
        })
        summary = validate(payload)
        self.assertEqual(summary["cultural_area_count"], 1)
        self.assertEqual(summary["profile_count"], 262)

    def test_census_only_area_fails_closed(self):
        payload = _payload()
        payload["records"].append({
            "type": "CULTURAL_AREA",
            "area_id": "bad-census-area",
            "public_name": "Invented Culture Area",
            "boundary_type": "FUZZY_AREA",
            "boundary_status": "REVIEW_REQUIRED",
            "boundary_confidence": "LOW",
            "sources": [{
                "source_family": "acs_census_aggregate",
                "authority": "U.S. Census Bureau",
                "source_ref": "ACS 2024",
                "source_url": "https://api.census.gov/",
            }],
        })
        with self.assertRaises(ValueError):
            validate(payload)

    def test_profile_cannot_embed_culture_label(self):
        payload = _payload()
        for row in payload["records"]:
            if row.get("type") == "COMMUNITY_PROFILE":
                row["culture_label"] = "Invented"
                break
        with self.assertRaises(ValueError):
            validate(payload)

    def test_public_place_must_be_accepted_and_canonical(self):
        payload = _payload()
        payload["records"].append({
            "type": "VERIFIED_PLACE",
            "business_id": "bus-1",
            "location_id": "loc-1",
            "disposition": "REVIEW_REQUIRED",
            "why_included": "pending",
        })
        with self.assertRaises(ValueError):
            validate(payload)

    def test_missing_profile_fails_even_for_special_nta(self):
        payload = _payload()
        for row in payload["records"]:
            if row.get("type") == "BASE_GEOGRAPHY" and row.get("nta2020") == "NTA261":
                row["residential"] = False
        payload["records"] = [
            row for row in payload["records"]
            if not (row.get("type") == "COMMUNITY_PROFILE" and row.get("nta2020") == "NTA261")
        ]
        with self.assertRaises(ValueError):
            validate(payload)

    def test_nonresidential_nta_uses_not_applicable(self):
        payload = _payload()
        for row in payload["records"]:
            if row.get("type") == "BASE_GEOGRAPHY" and row.get("nta2020") == "NTA261":
                row["residential"] = False
            if row.get("type") == "COMMUNITY_PROFILE" and row.get("nta2020") == "NTA261":
                row["profile_state"] = "NOT_APPLICABLE"
        summary = validate(payload)
        self.assertEqual(summary["profile_count"], 262)

    def test_residential_nta_cannot_use_not_applicable(self):
        payload = _payload()
        for row in payload["records"]:
            if row.get("type") == "COMMUNITY_PROFILE" and row.get("nta2020") == "NTA000":
                row["profile_state"] = "NOT_APPLICABLE"
                break
        with self.assertRaises(ValueError):
            validate(payload)


if __name__ == "__main__":
    unittest.main()
