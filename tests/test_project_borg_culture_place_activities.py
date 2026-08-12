from __future__ import annotations

import unittest

from scripts.project_borg_culture_place_activities import project


def accepted_place():
    return {
        "business_id": "bus-1",
        "location_id": "loc-1",
        "disposition": "ACCEPTED",
        "why_included": "Independent reviewed Culture evidence.",
        "independent_culture_evidence": True,
    }


def candidate(**overrides):
    row = {
        "candidate_id": "act-1",
        "host_business_id": "bus-1",
        "host_location_id": "loc-1",
        "activity_kind": "DATED_OCCURRENCE",
        "activity_state": "CURRENT",
        "host_relation_evidence_state": "CONFIRMED",
        "source_class": "HOST_FIRST_PARTY",
        "title": "Neighborhood smoke-out",
        "location_state": "EXACT_STOREFRONT",
        "occurrence_id": "occ-1",
    }
    row.update(overrides)
    return row


class CulturePlaceActivityProjectorTests(unittest.TestCase):
    def test_verified_host_activity_is_public(self):
        result = project(places=[accepted_place()], candidates=[candidate()])
        record = result["records"][0]
        self.assertEqual(record["terminal_disposition"], "CULTURE_ACTIVITY_PUBLIC")
        self.assertTrue(record["public"])
        self.assertTrue(record["map_eligible"])
        self.assertEqual(result["accounting"]["silent_loss"], 0)

    def test_nearby_or_unaccepted_host_cannot_qualify(self):
        result = project(places=[], candidates=[candidate()])
        self.assertEqual(result["records"][0]["terminal_disposition"], "NOT_CULTURE_ACTIVITY")

    def test_host_relationship_must_be_confirmed(self):
        result = project(
            places=[accepted_place()],
            candidates=[candidate(host_relation_evidence_state="NEARBY_ONLY")],
        )
        self.assertEqual(result["records"][0]["terminal_disposition"], "CULTURE_ACTIVITY_REVIEW_REQUIRED")
        self.assertFalse(result["records"][0]["public"])

    def test_aggregator_only_does_not_qualify(self):
        result = project(
            places=[accepted_place()],
            candidates=[candidate(source_class="AGGREGATOR")],
        )
        self.assertEqual(result["records"][0]["terminal_disposition"], "CULTURE_ACTIVITY_REVIEW_REQUIRED")

    def test_dated_activity_requires_canonical_occurrence(self):
        result = project(places=[accepted_place()], candidates=[candidate(occurrence_id=None)])
        self.assertEqual(result["records"][0]["reason"], "canonical_occurrence_id_required")
        self.assertFalse(result["records"][0]["public"])

    def test_ongoing_program_requires_stable_program_id(self):
        result = project(
            places=[accepted_place()],
            candidates=[candidate(activity_kind="ONGOING_PROGRAM", occurrence_id=None, program_id=None)],
        )
        self.assertEqual(result["records"][0]["reason"], "stable_program_id_required")

    def test_unresolved_location_is_public_list_only(self):
        result = project(
            places=[accepted_place()],
            candidates=[candidate(location_state="UNRESOLVED")],
        )
        record = result["records"][0]
        self.assertEqual(record["terminal_disposition"], "CULTURE_ACTIVITY_LIST_ONLY_LOCATION_PENDING")
        self.assertTrue(record["public"])
        self.assertFalse(record["map_eligible"])

    def test_cancelled_and_expired_never_public(self):
        for state, disposition in [
            ("CANCELLED", "CULTURE_ACTIVITY_CANCELLED"),
            ("EXPIRED", "CULTURE_ACTIVITY_EXPIRED"),
        ]:
            with self.subTest(state=state):
                record = project(
                    places=[accepted_place()],
                    candidates=[candidate(activity_state=state)],
                )["records"][0]
                self.assertEqual(record["terminal_disposition"], disposition)
                self.assertFalse(record["public"])

    def test_duplicate_candidate_id_fails_closed(self):
        places = [accepted_place()]
        duplicates = [candidate(), candidate()]
        with self.assertRaises(ValueError):
            project(places=places, candidates=duplicates)


if __name__ == "__main__":
    unittest.main()
