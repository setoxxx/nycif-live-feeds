import unittest

from scripts.sources.ticketmaster import DATASET, TicketmasterAdapter, normalize_event


FIXTURE = {
    "id": "tm-123",
    "name": "Example Concert",
    "url": "https://www.ticketmaster.com/event/tm-123",
    "dates": {
        "timezone": "America/New_York",
        "start": {"dateTime": "2026-09-04T23:00:00Z", "localDate": "2026-09-04", "localTime": "19:00:00"},
    },
    "_embedded": {
        "venues": [
            {
                "id": "venue-1",
                "name": "Example Arena",
                "address": {"line1": "4 Pennsylvania Plaza"},
                "city": {"name": "New York"},
                "state": {"stateCode": "NY", "name": "New York"},
                "postalCode": "10001",
                "location": {"latitude": "40.7505", "longitude": "-73.9934"},
            }
        ]
    },
}


class TicketmasterAdapterTests(unittest.TestCase):
    def test_normalizes_to_source_observation_not_canonical_id(self):
        observation = normalize_event(FIXTURE)
        self.assertEqual(observation.source_dataset, DATASET)
        self.assertEqual(observation.source_event_id, "tm-123")
        self.assertEqual(observation.title, "Example Concert")
        self.assertEqual(observation.venue_id, "venue-1")
        self.assertEqual(observation.venue_name, "Example Arena")
        self.assertEqual(observation.latitude, 40.7505)
        self.assertEqual(observation.longitude, -73.9934)
        self.assertIsNone(observation.series_id)
        self.assertEqual(observation.raw_record["id"], "tm-123")

    def test_preserves_source_url_and_address(self):
        observation = normalize_event(FIXTURE)
        self.assertEqual(observation.source_url, "https://www.ticketmaster.com/event/tm-123")
        self.assertEqual(observation.address, "4 Pennsylvania Plaza, New York, NY, 10001")

    def test_local_date_fallback_preserves_timezone(self):
        fixture = dict(FIXTURE)
        fixture["dates"] = {
            "timezone": "America/New_York",
            "start": {"localDate": "2026-09-05", "localTime": "14:00:00"},
        }
        observation = normalize_event(fixture)
        self.assertEqual(observation.start_date_time, "2026-09-05T14:00:00")
        self.assertEqual(observation.timezone, "America/New_York")

    def test_missing_native_id_fails_closed(self):
        fixture = dict(FIXTURE)
        fixture.pop("id")
        with self.assertRaises(ValueError):
            normalize_event(fixture)

    def test_network_adapter_requires_api_key(self):
        with self.assertRaises(ValueError):
            TicketmasterAdapter("")

    def test_url_is_nyc_scoped_and_paginated(self):
        adapter = TicketmasterAdapter("secret", page_size=200)
        url = adapter.build_url(3)
        self.assertIn("city=New+York", url)
        self.assertIn("stateCode=NY", url)
        self.assertIn("page=3", url)
        self.assertIn("size=200", url)


if __name__ == "__main__":
    unittest.main()
