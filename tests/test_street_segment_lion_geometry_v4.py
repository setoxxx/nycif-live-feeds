from __future__ import annotations

import unittest

from scripts.audit_street_segment_lion_geometry_v4 import audit, geometry_sha256


IDENTITY = {
    "schema_version": "NYCIF_STREET_SEGMENT_GEOSUPPORT_RECOVERY_AUDIT_V2",
    "geometry_join_status": "SEGMENT_IDENTIFIER_ONLY_GEOMETRY_NOT_YET_JOINED",
    "publication_authority_granted": False,
    "projector_consumed": False,
    "claims": [
        {
            "claim_key": "bk|main between a and b",
            "borough": "Brooklyn",
            "event_location": "MAIN STREET between A STREET and B STREET",
            "occurrence_count": 2,
            "source_event_ids": ["1", "2"],
            "strict_nonpublic_segment_evidence": True,
            "function_3_segment_identifier": "1234567",
            "endpoint_1": {"node": "0000001", "latitude": 40.6000, "longitude": -73.9000},
            "endpoint_2": {"node": "0000002", "latitude": 40.6010, "longitude": -73.8990},
        }
    ],
}


def feature(segment_id="1234567", geometry=None):
    if geometry is None:
        geometry = {
            "type": "LineString",
            "coordinates": [[-73.9000, 40.6000], [-73.8995, 40.6005], [-73.8990, 40.6010]],
        }
    return {
        "type": "Feature",
        "properties": {"SegmentID": segment_id},
        "geometry": geometry,
    }


class LionGeometryAuditTests(unittest.TestCase):
    def test_strict_identity_joins_source_line_without_point_generation(self):
        source = {"type": "FeatureCollection", "features": [feature()]}
        result = audit(IDENTITY, source)
        self.assertEqual(result["joined_geometry_count"], 1)
        self.assertEqual(result["unresolved_or_blocked_geometry_count"], 0)
        entry = result["entries"][0]
        self.assertTrue(entry["geometry_joined"])
        self.assertEqual(entry["geometry_type"], "LineString")
        self.assertEqual(entry["geometry_sha256"], geometry_sha256(entry["geometry"]))
        self.assertFalse(entry["publication_allowed"])
        self.assertFalse(entry["exact_pin_eligible"])
        self.assertFalse(entry["point_generated"])
        self.assertEqual(result["point_generated_count"], 0)
        self.assertEqual(result["midpoint_publication_count"], 0)

    def test_missing_segment_blocks(self):
        source = {"type": "FeatureCollection", "features": []}
        result = audit(IDENTITY, source)
        self.assertEqual(result["joined_geometry_count"], 0)
        self.assertEqual(result["reason_counts"]["OFFICIAL_LION_SEGMENT_NOT_FOUND"], 1)

    def test_duplicate_source_segment_blocks(self):
        source = {"type": "FeatureCollection", "features": [feature(), feature()]}
        result = audit(IDENTITY, source)
        self.assertEqual(result["joined_geometry_count"], 0)
        self.assertEqual(result["reason_counts"]["OFFICIAL_LION_SEGMENT_NOT_UNIQUE"], 1)

    def test_non_line_geometry_blocks(self):
        source = {
            "type": "FeatureCollection",
            "features": [feature(geometry={"type": "Point", "coordinates": [-73.9, 40.6]})],
        }
        result = audit(IDENTITY, source)
        self.assertEqual(result["joined_geometry_count"], 0)
        self.assertEqual(result["reason_counts"]["OFFICIAL_LION_GEOMETRY_INVALID_TYPE"], 1)

    def test_endpoint_disagreement_blocks(self):
        source = {
            "type": "FeatureCollection",
            "features": [
                feature(
                    geometry={
                        "type": "LineString",
                        "coordinates": [[-73.7, 40.8], [-73.699, 40.801]],
                    }
                )
            ],
        }
        result = audit(IDENTITY, source)
        self.assertEqual(result["joined_geometry_count"], 0)
        self.assertEqual(result["reason_counts"]["LION_GEOMETRY_ENDPOINT_DISAGREEMENT"], 1)


if __name__ == "__main__":
    unittest.main()
