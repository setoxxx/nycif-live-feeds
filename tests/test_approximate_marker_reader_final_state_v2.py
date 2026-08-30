from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_approximate_marker_reader_v1 import (
    DURABLE_AUTHORITY,
    RECOVERY_AUTHORITY,
    build,
    final_approximate_contract,
)


def approximate_event(event_id: str, authority: str) -> dict:
    return {
        "title": f"Event {event_id}",
        "start_date_time": "2026-08-30T12:00:00-04:00",
        "end_date_time": "2026-08-30T14:00:00-04:00",
        "borough": "Brooklyn",
        "location": "Marine Park: Cricket-03",
        "latitude": 40.607,
        "longitude": -73.934,
        "location_id": "fixture:marine-park-cricket-03",
        "source": {"dataset": "fixture", "source_event_id": event_id},
        "location_evidence": {
            "tier": "approximate_area",
            "validation_state": "validated",
            "exact_pin_eligible": False,
            "source_provenance": "fixture",
        },
        "nycif": {
            "location_authority": authority,
            "map_eligibility_state": "GENERAL_AREA",
            "coordinate_status": "approximate",
            "certified_pin": False,
            "display_disposition": "approximate_marker",
            "location_id": "fixture:marine-park-cricket-03",
        },
    }


class ApproximateMarkerFinalStateTests(unittest.TestCase):
    def test_both_approximate_authorities_satisfy_final_contract(self):
        for authority in (RECOVERY_AUTHORITY, DURABLE_AUTHORITY):
            valid, reason = final_approximate_contract(approximate_event("1", authority))
            self.assertTrue(valid)
            self.assertEqual(reason, "final_approximate")

    def test_exact_certification_can_never_enter_approximate_overlay(self):
        event = approximate_event("2", DURABLE_AUTHORITY)
        event["nycif"]["map_eligibility_state"] = "MAP_READY"
        event["nycif"]["certified_pin"] = True
        event["location_evidence"]["exact_pin_eligible"] = True
        valid, reason = final_approximate_contract(event)
        self.assertFalse(valid)
        self.assertEqual(reason, "invalid_approximate_contract")

    def test_final_state_count_may_differ_from_intermediate_recovery_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical = root / "canonical.json"
            recovery = root / "recovery.json"
            reuse = root / "reuse.json"
            canonical.write_text(
                json.dumps([
                    approximate_event("1", DURABLE_AUTHORITY),
                    approximate_event("2", RECOVERY_AUTHORITY),
                ]),
                encoding="utf-8",
            )
            # Intentionally different: this is the regression that blocked run #101.
            recovery.write_text(json.dumps({"recovered_approximate_markers": 1}), encoding="utf-8")
            reuse.write_text(json.dumps({"approximate_reused_count": 1}), encoding="utf-8")
            geojson, status = build(canonical, recovery, reuse)

        self.assertEqual(len(geojson["features"]), 2)
        self.assertEqual(status["approximate_marker_count"], 2)
        self.assertEqual(status["final_contract_count"], 2)
        self.assertTrue(status["counts_match_final_contract"])
        self.assertEqual(status["recovery_report_count"], 1)
        self.assertTrue(status["recovery_count_is_diagnostic_only"])
        self.assertEqual(status["exact_pin_count"], 0)
        self.assertTrue(status["qa_pass"])
        self.assertEqual(
            {feature["properties"]["location_id"] for feature in geojson["features"]},
            {"fixture:marine-park-cricket-03"},
        )


if __name__ == "__main__":
    unittest.main()
