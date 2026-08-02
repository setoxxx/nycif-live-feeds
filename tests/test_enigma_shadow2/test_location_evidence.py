import unittest

from enigma.shadow2.location_evidence import (
    LocationPrecisionTier,
    ReasonCode,
    ValidationState,
    classify_location_evidence,
)


class LocationEvidenceTests(unittest.TestCase):
    def test_source_coordinates_require_explicit_provenance(self) -> None:
        unproven = classify_location_evidence({"latitude": 40.618, "longitude": -73.905})
        self.assertEqual(unproven.tier, LocationPrecisionTier.UNRESOLVED)
        self.assertEqual(unproven.reason_code, ReasonCode.COORDINATE_SOURCE_UNPROVEN)
        self.assertFalse(unproven.exact_pin_eligible)

        proven = classify_location_evidence(
            {
                "latitude": 40.618,
                "longitude": -73.905,
                "coordinate_source": "source_provided",
            }
        )
        self.assertEqual(proven.tier, LocationPrecisionTier.EXACT_SOURCE_COORDINATE)
        self.assertEqual(proven.validation_state, ValidationState.UNVALIDATED)
        self.assertFalse(proven.exact_pin_eligible)
        self.assertFalse(proven.promotion_allowed)

    def test_null_island_is_invalid(self) -> None:
        evidence = classify_location_evidence({"latitude": 0.0, "longitude": 0.0})
        self.assertEqual(evidence.tier, LocationPrecisionTier.UNRESOLVED)
        self.assertEqual(evidence.validation_state, ValidationState.INVALID)
        self.assertEqual(evidence.reason_code, ReasonCode.NULL_ISLAND)

    def test_generic_fallback_cannot_be_exact(self) -> None:
        evidence = classify_location_evidence(
            {
                "latitude": 40.77,
                "longitude": -73.97,
                "coordinate_source": "generic_street_fallback",
                "borough": "Brooklyn",
            }
        )
        self.assertEqual(evidence.tier, LocationPrecisionTier.APPROXIMATE_AREA)
        self.assertEqual(evidence.validation_state, ValidationState.INVALID)
        self.assertEqual(evidence.reason_code, ReasonCode.GENERIC_FALLBACK)

    def test_facility_requires_authoritative_id(self) -> None:
        name_only = classify_location_evidence({"facility_name": "Prospect Park Bandshell"})
        self.assertEqual(name_only.tier, LocationPrecisionTier.UNRESOLVED)
        self.assertEqual(name_only.reason_code, ReasonCode.FACILITY_ID_UNKNOWN)

        identified = classify_location_evidence(
            {"facility_name": "Prospect Park Bandshell", "facility_id": "B001"}
        )
        self.assertEqual(identified.tier, LocationPrecisionTier.CERTIFIED_FACILITY)
        self.assertEqual(identified.validation_state, ValidationState.UNVALIDATED)
        self.assertFalse(identified.exact_pin_eligible)

    def test_segment_claim_is_not_certified_by_presence(self) -> None:
        evidence = classify_location_evidence(
            {"location": "EAST 74 STREET between AVENUE U and AVENUE T", "borough": "Brooklyn"}
        )
        self.assertEqual(evidence.tier, LocationPrecisionTier.CERTIFIED_STREET_SEGMENT)
        self.assertEqual(evidence.validation_state, ValidationState.UNVALIDATED)
        self.assertEqual(evidence.reason_code, ReasonCode.SEGMENT_UNCERTIFIED)
        self.assertFalse(evidence.exact_pin_eligible)

    def test_event_923896_regression_claim(self) -> None:
        evidence = classify_location_evidence(
            {
                "source_event_id": "923896",
                "display_location": "EAST 74 STREET between AVENUE U and AVENUE T",
                "borough": "Brooklyn",
            }
        )
        self.assertEqual(evidence.tier, LocationPrecisionTier.CERTIFIED_STREET_SEGMENT)
        self.assertEqual(evidence.evidence["street"], "EAST 74 STREET")
        self.assertEqual(evidence.evidence["cross_street_1"], "AVENUE U")
        self.assertEqual(evidence.evidence["cross_street_2"], "AVENUE T")

    def test_strict_intersection_avoids_plain_and_phrase(self) -> None:
        false_positive = classify_location_evidence({"location": "Arts and Crafts Center"})
        self.assertEqual(false_positive.tier, LocationPrecisionTier.UNRESOLVED)

        intersection = classify_location_evidence({"location": "Broadway & 42 Street"})
        self.assertEqual(intersection.tier, LocationPrecisionTier.EXACT_INTERSECTION)
        self.assertEqual(intersection.validation_state, ValidationState.UNVALIDATED)

    def test_numbered_address_is_unvalidated_exact_address_claim(self) -> None:
        evidence = classify_location_evidence({"street_address": "123 East 74 Street"})
        self.assertEqual(evidence.tier, LocationPrecisionTier.EXACT_ADDRESS)
        self.assertEqual(evidence.validation_state, ValidationState.UNVALIDATED)
        self.assertFalse(evidence.exact_pin_eligible)

    def test_area_only_is_approximate(self) -> None:
        evidence = classify_location_evidence({"municipality": "Little Silver", "state": "NJ"})
        self.assertEqual(evidence.tier, LocationPrecisionTier.APPROXIMATE_AREA)
        self.assertEqual(evidence.validation_state, ValidationState.NOT_APPLICABLE)
        self.assertFalse(evidence.exact_pin_eligible)

    def test_empty_record_is_unresolved(self) -> None:
        evidence = classify_location_evidence({})
        self.assertEqual(evidence.tier, LocationPrecisionTier.UNRESOLVED)
        self.assertEqual(evidence.reason_code, ReasonCode.MISSING_EVIDENCE)


if __name__ == "__main__":
    unittest.main()
