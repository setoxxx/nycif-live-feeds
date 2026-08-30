from __future__ import annotations

import unittest

from scripts.occurrence_identity_contract import occurrence_key_v2, source_key


class OccurrenceIdentityContractTests(unittest.TestCase):
    def test_canonical_nested_native_source_id_beats_canonical_id(self) -> None:
        row = {
            "id": "canonical-tvpp-hash",
            "source": {"dataset": "tvpp-9vvx", "source_event_id": "912654"},
            "start_date_time": "2026-08-30T10:00:00.000",
        }
        self.assertEqual(source_key(row), ("tvpp-9vvx", "912654"))

    def test_top_level_native_source_id_wins(self) -> None:
        row = {
            "id": "canonical-row-id",
            "source_event_id": "native-top-level",
            "source": {"dataset": "tvpp-9vvx", "source_event_id": "nested-native"},
        }
        self.assertEqual(source_key(row), ("tvpp-9vvx", "native-top-level"))

    def test_legacy_id_remains_last_resort(self) -> None:
        row = {"id": "legacy-only-id", "dataset": "legacy-source"}
        self.assertEqual(source_key(row), ("legacy-source", "legacy-only-id"))

    def test_semantic_and_canonical_forms_share_occurrence_identity(self) -> None:
        semantic = {
            "source_dataset": "tvpp-9vvx",
            "source_event_id": "912654",
            "start_date_time": "2026-08-30T10:00:00.000",
        }
        canonical = {
            "id": "canonical-tvpp-hash",
            "source": {"dataset": "tvpp-9vvx", "source_event_id": "912654"},
            "start_date_time": "2026-08-30T10:00:00.000",
        }
        self.assertEqual(occurrence_key_v2(semantic), occurrence_key_v2(canonical))

    def test_recurring_multi_day_event_keeps_each_day_as_distinct_occurrence(self) -> None:
        rows = [
            {
                "source_dataset": "nycif-feast",
                "source_event_id": "18th-ave-feast-2026",
                "start_date_time": f"2026-08-{day:02d}T12:00:00.000",
                "event_location": "18th Avenue, Brooklyn",
            }
            for day in (29, 30, 31)
        ]
        keys = {occurrence_key_v2(row) for row in rows}
        self.assertEqual(len(keys), 3)
        self.assertEqual(
            {key[2][:10] for key in keys},
            {"2026-08-29", "2026-08-30", "2026-08-31"},
        )

    def test_same_source_same_day_different_start_times_are_distinct(self) -> None:
        morning = {
            "source_dataset": "venue-schedule",
            "source_event_id": "show-123",
            "start_date_time": "2026-08-30T14:00:00.000",
        }
        evening = {
            "source_dataset": "venue-schedule",
            "source_event_id": "show-123",
            "start_date_time": "2026-08-30T20:00:00.000",
        }
        self.assertNotEqual(occurrence_key_v2(morning), occurrence_key_v2(evening))


if __name__ == "__main__":
    unittest.main()
