from __future__ import annotations

import unittest

from scripts.build_street_segment_route_authority_v1 import (
    GeoSupportStreetEvidence,
    SCHEMA_IDENTITY,
    build_reader_artifact,
    current_segment_claims,
    valid_linear_geometry,
)


class FakeGeoSupport:
    def call(self, payload):
        function = payload.get("function")
        if function == 2:
            cross = payload.get("street_name_2")
            return {"LION Node Number": "100" if cross == "Avenue A" else "200"}
        if function == "2W":
            node = payload.get("node")
            if node == "100":
                return {"Latitude": "40.7000", "Longitude": "-73.9900"}
            return {"Latitude": "40.7010", "Longitude": "-73.9900"}
        if function == 3:
            return {
                "From Node": "100",
                "To Node": "200",
                "Segment Identifier": "123",
            }
        raise AssertionError(payload)


def canonical_event():
    return {
        "title": "Street Event",
        "location": "Main Street between Avenue A and Avenue B",
        "borough": "Brooklyn",
        "start_date_time": "2026-08-30T12:00:00-04:00",
        "end_date_time": "2026-08-30T18:00:00-04:00",
        "source": {"dataset": "tvpp-9vvx", "source_event_id": "abc"},
        "nycif": {
            "map_eligibility_state": "LIST_ONLY",
            "certified_pin": False,
        },
    }


class RouteAuthorityTests(unittest.TestCase):
    def test_current_claims_are_occurrence_keyed(self):
        rows = [
            {
                "event_id": "abc",
                "event_borough": "Brooklyn",
                "event_location": "Main Street between Avenue A and Avenue B",
                "start_date_time": "2026-08-30T12:00:00-04:00",
            }
        ]
        claims = current_segment_claims(rows, "2026-08-30")
        claim = next(iter(claims.values()))
        self.assertEqual(
            claim["occurrence_ids"],
            ["tvpp-9vvx|abc|2026-08-30T12:00:00-04:00"],
        )

    def test_geosupport_requires_endpoint_and_segment_agreement(self):
        evidence = GeoSupportStreetEvidence(FakeGeoSupport())
        result = evidence.resolve_segment(
            {
                "borough": "Brooklyn",
                "event_location": "Main Street between Avenue A and Avenue B",
            }
        )
        self.assertTrue(result["strict_segment_identity"])
        self.assertEqual(result["function_3_segment_identifier"], "0000123")

    def test_reader_emits_official_line_not_point(self):
        identity = {
            "schema_version": SCHEMA_IDENTITY,
            "publication_authority_granted": False,
            "strict_occurrence_coverage": 1,
            "claims": [
                {
                    "strict_segment_identity": True,
                    "event_location": "Main Street between Avenue A and Avenue B",
                    "borough": "Brooklyn",
                    "function_3_segment_identifier": "0000123",
                    "endpoint_1": {"latitude": 40.7000, "longitude": -73.9900},
                    "endpoint_2": {"latitude": 40.7010, "longitude": -73.9900},
                    "occurrence_ids": ["tvpp-9vvx|abc|2026-08-30T12:00:00-04:00"],
                }
            ],
        }
        lion = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-73.9900, 40.7000], [-73.9900, 40.7010]],
                    },
                    "properties": {
                        "SegmentID": "123",
                        "NodeIDFrom": "100",
                        "NodeIDTo": "200",
                    },
                }
            ],
        }
        collection, status = build_reader_artifact(identity, lion, [canonical_event()])
        self.assertTrue(status["qa_pass"])
        self.assertEqual(status["route_geometry_count"], 1)
        self.assertEqual(status["point_geometry_count"], 0)
        self.assertEqual(collection["features"][0]["geometry"]["type"], "LineString")
        self.assertEqual(collection["features"][0]["properties"]["display_geometry_role"], "route")

    def test_exact_point_is_never_overridden(self):
        event = canonical_event()
        event["nycif"] = {"map_eligibility_state": "MAP_READY", "certified_pin": True}
        identity = {
            "schema_version": SCHEMA_IDENTITY,
            "publication_authority_granted": False,
            "strict_occurrence_coverage": 1,
            "claims": [
                {
                    "strict_segment_identity": True,
                    "event_location": event["location"],
                    "borough": event["borough"],
                    "function_3_segment_identifier": "0000123",
                    "endpoint_1": {"latitude": 40.7000, "longitude": -73.9900},
                    "endpoint_2": {"latitude": 40.7010, "longitude": -73.9900},
                    "occurrence_ids": ["tvpp-9vvx|abc|2026-08-30T12:00:00-04:00"],
                }
            ],
        }
        lion = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-73.9900, 40.7000], [-73.9900, 40.7010]],
                    },
                    "properties": {"SegmentID": "123"},
                }
            ],
        }
        collection, status = build_reader_artifact(identity, lion, [event])
        self.assertEqual(collection["features"], [])
        self.assertEqual(status["exact_point_protected_count"], 1)

    def test_geometry_validator_rejects_points_and_degenerate_lines(self):
        self.assertFalse(valid_linear_geometry({"type": "Point", "coordinates": [-73.9, 40.7]}))
        self.assertFalse(
            valid_linear_geometry(
                {"type": "LineString", "coordinates": [[-73.9, 40.7], [-73.9, 40.7]]}
            )
        )


if __name__ == "__main__":
    unittest.main()
