import unittest

from scripts.audit_street_segment_geoclient_recovery import audit_claims, current_segment_claims
from scripts.nyc_location_resolver import ResolveResult


class FakeResolver:
    def __init__(self, results):
        self.results = results
        self.geoclient = type("FakeGeoclient", (), {"live_calls": 2})()

    def resolve(self, *, display_location, borough=None, cache_keys=None):
        return self.results[(borough, display_location)]


class StreetSegmentGeoclientRecoveryAuditTests(unittest.TestCase):
    def test_current_segment_claims_deduplicate_recurring_occurrences(self):
        rows = [
            {
                "event_id": "one",
                "event_borough": "Brooklyn",
                "event_location": "MAIN STREET between FIRST AVENUE and SECOND AVENUE",
                "start_date_time": "2026-08-20T10:00:00",
            },
            {
                "event_id": "two",
                "event_borough": "Brooklyn",
                "event_location": "MAIN STREET between FIRST AVENUE and SECOND AVENUE",
                "start_date_time": "2026-08-21T10:00:00",
            },
            {
                "event_id": "old",
                "event_borough": "Brooklyn",
                "event_location": "OLD STREET between A STREET and B STREET",
                "start_date_time": "2026-08-01T10:00:00",
            },
        ]
        claims = current_segment_claims(rows, "2026-08-13")
        self.assertEqual(len(claims), 1)
        claim = next(iter(claims.values()))
        self.assertEqual(claim["occurrence_count"], 2)
        self.assertEqual(claim["source_event_ids"], ["one", "two"])

    def test_audit_certifies_only_validated_exact_segment_results(self):
        exact_location = "MAIN STREET between FIRST AVENUE and SECOND AVENUE"
        unresolved_location = "OTHER STREET between THIRD AVENUE and FOURTH AVENUE"
        claims = {
            "brooklyn|main": {
                "borough": "Brooklyn",
                "event_location": exact_location,
                "occurrence_count": 3,
                "source_event_ids": ["1"],
            },
            "brooklyn|other": {
                "borough": "Brooklyn",
                "event_location": unresolved_location,
                "occurrence_count": 1,
                "source_event_ids": ["2"],
            },
        }
        resolver = FakeResolver(
            {
                ("Brooklyn", exact_location): ResolveResult(
                    resolved=True,
                    tier="certified_street_segment",
                    lat=40.65,
                    lng=-73.95,
                    source="nyc_geoclient_segment_midpoint",
                    confidence="high",
                    confidence_reason="fixture",
                    validation_state="validated",
                    exact_pin_eligible=True,
                    reason_code="SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED",
                ),
                ("Brooklyn", unresolved_location): ResolveResult(
                    resolved=False,
                    tier="unresolved",
                    lat=None,
                    lng=None,
                    source=None,
                    confidence=None,
                    confidence_reason="fixture",
                    validation_state="invalid",
                    exact_pin_eligible=False,
                    reason_code="SEGMENT_UNCERTIFIED",
                ),
            }
        )
        report = audit_claims(claims, resolver, credentials_available=True)
        self.assertEqual(report["unique_segment_claim_count"], 2)
        self.assertEqual(report["certified_segment_claim_count"], 1)
        self.assertEqual(report["unresolved_segment_claim_count"], 1)
        self.assertEqual(report["geoclient_live_call_count"], 2)
        self.assertFalse(report["promotion_allowed"])
        self.assertFalse(report["public_map_modified"])
        exact = next(item for item in report["claims"] if item["exact_segment_certified"])
        self.assertEqual(exact["latitude"], 40.65)
        self.assertEqual(exact["reason_code"], "SEGMENT_GEOCLIENT_ENDPOINTS_VALIDATED")


if __name__ == "__main__":
    unittest.main()
