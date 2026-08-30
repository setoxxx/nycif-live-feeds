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


def durable_exact_event(event_id: str) -> dict:
    event = approximate_event(event_id, DURABLE_AUTHORITY)
    event["nycif"].update({
        "map_eligibility_state": "MAP_READY",
        "coordinate_status": "map_ready",
        "certified_pin": True,
        "display_disposition": "standalone_public_event",
    })
    event["location_evidence"].update({
        "tier": "exact",
        "exact_pin_eligible": True,
    })
    return event


class ApproximateMarkerFinalStateTests(unittest.TestCase):
    def test_both_approximate_authorities_satisfy_final_contract(self):
        for authority in (RECOVERY_AUTHORITY, DURABLE_AUTHORITY):
            valid, reason = final_approximate_contract(approximate_event("1", authority))
            self.assertTrue(valid)
            self.assertEqual(reason, "final_approximate")

    def test_durable_exact_is_owned_by_exact_lane_not_invalid_approximate(self):
        valid, reason = final_approximate_contract(durable_exact_event("2"))
        self.assertFalse(valid)
        self.assertEqual(reason, "durable_exact_lane")

    def test_recovery_authority_exact_claim_still_fails_closed(self):
        event = approximate_event("3", RECOVERY_AUTHORITY)
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
            recovery.write_text(json.dumps({"recovered_approximate_markers": 1}), encoding="utf-8")
            reuse.write_text(
                json.dumps({"approximate_reused_count": 1, "exact_reused_count": 0}),
                encoding="utf-8",
            )
            geojson, status = build(canonical, recovery, reuse)

        self.assertEqual(len(geojson["features"]), 2)
        self.assertEqual(status["approximate_marker_count"], 2)
        self.assertEqual(status["final_contract_count"], 2)
        self.assertTrue(status["counts_match_final_contract"])
        self.assertEqual(status["recovery_report_count"], 1)
        self.assertTrue(status["recovery_count_is_diagnostic_only"])
        self.assertEqual(status["exact_pin_count"], 0)
        self.assertTrue(status["qa_pass"])

    def test_mixed_durable_exact_and_approximate_reconciles_precision_lanes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical = root / "canonical.json"
            recovery = root / "recovery.json"
            reuse = root / "reuse.json"
            canonical.write_text(
                json.dumps([
                    durable_exact_event(str(i)) for i in range(1, 10)
                ] + [approximate_event("10", DURABLE_AUTHORITY)]),
                encoding="utf-8",
            )
            recovery.write_text(json.dumps({"recovered_approximate_markers": 0}), encoding="utf-8")
            reuse.write_text(
                json.dumps({"approximate_reused_count": 1, "exact_reused_count": 9}),
                encoding="utf-8",
            )
            geojson, status = build(canonical, recovery, reuse)

        self.assertEqual(len(geojson["features"]), 1)
        self.assertEqual(status["approximate_marker_count"], 1)
        self.assertEqual(status["durable_exact_excluded_count"], 9)
        self.assertEqual(status["durable_exact_report_count"], 9)
        self.assertTrue(status["durable_exact_lane_reconciles"])
        self.assertEqual(status["invalid_marker_count"], 0)
        self.assertEqual(status["exact_pin_count"], 0)
        self.assertTrue(status["qa_pass"])


if __name__ == "__main__":
    unittest.main()
