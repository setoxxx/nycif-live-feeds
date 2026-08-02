import unittest
from datetime import date, datetime

from enigma.shadow2.occurrence_identity import (
    build_occurrence_identity,
    normalize_date,
    normalize_time,
)


class NormalizeDateTests(unittest.TestCase):
    def test_valid_supported_dates(self) -> None:
        self.assertEqual(normalize_date("2026-08-01"), "2026-08-01")
        self.assertEqual(normalize_date("2026-08-01T11:00:00.000Z"), "2026-08-01")
        self.assertEqual(normalize_date("08/01/2026"), "2026-08-01")
        self.assertEqual(normalize_date(date(2026, 8, 1)), "2026-08-01")

    def test_invalid_calendar_date_fails_closed(self) -> None:
        self.assertIsNone(normalize_date("2026-02-31"))
        self.assertIsNone(normalize_date("next tuesday"))
        self.assertIsNone(normalize_date(None))


class NormalizeTimeTests(unittest.TestCase):
    def test_normalizes_to_seconds(self) -> None:
        self.assertEqual(normalize_time("14:30"), "14:30:00")
        self.assertEqual(normalize_time("2:30 PM"), "14:30:00")
        self.assertEqual(normalize_time("2026-08-01T11:00:00.000-04:00"), "11:00:00")
        self.assertEqual(normalize_time(datetime(2026, 8, 1, 11, 0)), "11:00:00")

    def test_invalid_time_fails_closed(self) -> None:
        self.assertIsNone(normalize_time("25:00"))
        self.assertIsNone(normalize_time(None))


class OccurrenceIdentityTests(unittest.TestCase):
    def test_recurring_dates_do_not_collapse(self) -> None:
        first = build_occurrence_identity(
            {"source_event_id": "923896", "date": "2026-08-01", "start_time": "11:00"},
            "nycopendata",
            "tvpp-9vvx",
        )
        second = build_occurrence_identity(
            {"source_event_id": "923896", "date": "2026-08-08", "start_time": "11:00"},
            "nycopendata",
            "tvpp-9vvx",
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        assert first is not None and second is not None
        self.assertNotEqual(first.canonical_id(), second.canonical_id())
        self.assertNotEqual(first.composite_key(), second.composite_key())

    def test_different_start_times_do_not_collapse(self) -> None:
        morning = build_occurrence_identity(
            {"id": "7", "event_date": "2026-08-01", "start_time": "09:00"},
            "source",
            "dataset",
        )
        evening = build_occurrence_identity(
            {"id": "7", "event_date": "2026-08-01", "start_time": "19:00"},
            "source",
            "dataset",
        )
        assert morning is not None and evening is not None
        self.assertNotEqual(morning.canonical_id(), evening.canonical_id())

    def test_same_occurrence_is_deterministic(self) -> None:
        record = {"source": {"source_event_id": "923896"}, "event_date": "2026-08-01"}
        first = build_occurrence_identity(record, "nycopendata", "tvpp-9vvx")
        second = build_occurrence_identity(record, "nycopendata", "tvpp-9vvx")
        assert first is not None and second is not None
        self.assertEqual(first.canonical_id(), second.canonical_id())
        self.assertEqual(len(first.canonical_id()), 64)

    def test_missing_required_components_return_none(self) -> None:
        self.assertIsNone(build_occurrence_identity({"date": "2026-08-01"}, "source", "dataset"))
        self.assertIsNone(build_occurrence_identity({"id": "1"}, "source", "dataset"))
        self.assertIsNone(build_occurrence_identity({"id": "1", "date": "2026-08-01"}, "", "dataset"))

    def test_event_923896_regression_identity(self) -> None:
        occurrence = build_occurrence_identity(
            {
                "source_event_id": "923896",
                "start": "2026-08-01T11:00:00.000",
                "borough": "Brooklyn",
                "location": "EAST 74 STREET between AVENUE U and AVENUE T",
            },
            "nycopendata",
            "tvpp-9vvx",
        )
        self.assertIsNotNone(occurrence)
        assert occurrence is not None
        self.assertEqual(occurrence.normalized_date, "2026-08-01")
        self.assertEqual(occurrence.start_time, "11:00:00")
        self.assertEqual(
            occurrence.composite_key(),
            "nycopendata:tvpp-9vvx:923896@2026-08-01T11:00:00",
        )


if __name__ == "__main__":
    unittest.main()
