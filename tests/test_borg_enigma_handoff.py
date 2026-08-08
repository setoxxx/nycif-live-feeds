from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_borg_enigma_handoff as handoff


class BorgEnigmaHandoffTest(unittest.TestCase):
    def test_rows_from_snapshot_accepts_list_and_named_collection(self) -> None:
        self.assertEqual(handoff.rows_from_snapshot([{"id": 1}], ()), [{"id": 1}])
        self.assertEqual(
            handoff.rows_from_snapshot({"events": [{"id": 2}]}, ("events",)),
            [{"id": 2}],
        )

    def test_native_id_is_best_effort_and_hash_is_deterministic(self) -> None:
        row = {"event_id": 906790, "title": "Jamaica Rising Day Parade"}
        self.assertEqual(handoff.native_id(row, ("event_id", "id")), "906790")
        self.assertEqual(
            handoff.sha256_json(row),
            handoff.sha256_json(dict(reversed(list(row.items())))),
        )

    def test_source_receipt_registers_every_row_without_semantic_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            rows = [
                {"event_id": "1", "latitude": "40.7", "longitude": "-73.9"},
                {"title": "No native id and no coordinates"},
                {"event_id": "3", "latitude": None, "longitude": None},
            ]
            path.write_text(json.dumps(rows), encoding="utf-8")
            receipt = handoff.build_source_receipt(
                {
                    "source_id": "test",
                    "dataset_id": "test-dataset",
                    "path": path,
                    "row_keys": (),
                    "native_id_candidates": ("event_id",),
                }
            )
            self.assertEqual(receipt["observed_row_count"], 3)
            self.assertEqual(receipt["registered_observation_count"], 3)
            self.assertEqual(receipt["rows_without_native_id"], 1)
            self.assertEqual(len(receipt["observations"]), 3)
            self.assertTrue(all(row["content_sha256"] for row in receipt["observations"]))

    def test_exact_duplicate_observations_are_registered_before_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "raw.json"
            duplicate = {"id": "same", "name": "same observation"}
            path.write_text(json.dumps([duplicate, duplicate]), encoding="utf-8")
            receipt = handoff.build_source_receipt(
                {
                    "source_id": "calendar",
                    "dataset_id": "calendar",
                    "path": path,
                    "row_keys": (),
                    "native_id_candidates": ("id",),
                }
            )
            self.assertEqual(receipt["observed_row_count"], 2)
            self.assertEqual(receipt["registered_observation_count"], 2)
            self.assertEqual(len(receipt["observations"]), 2)
            self.assertEqual(
                receipt["observations"][0]["content_sha256"],
                receipt["observations"][1]["content_sha256"],
            )
            self.assertNotEqual(
                receipt["observations"][0]["ordinal"],
                receipt["observations"][1]["ordinal"],
            )

    def test_build_handoff_declares_no_coordinate_authority(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            specs = []
            for index in range(3):
                path = Path(td) / f"source-{index}.json"
                path.write_text(
                    json.dumps([{"id": str(index), "latitude": 40.7, "longitude": -73.9}]),
                    encoding="utf-8",
                )
                specs.append(
                    {
                        "source_id": f"source-{index}",
                        "dataset_id": f"dataset-{index}",
                        "path": path,
                        "row_keys": (),
                        "native_id_candidates": ("id",),
                    }
                )
            with patch.object(handoff, "SOURCE_SPECS", tuple(specs)):
                result = handoff.build_handoff()
            self.assertTrue(result["qa_pass"])
            self.assertEqual(result["observed_row_count"], 3)
            self.assertEqual(result["registered_observation_count"], 3)
            self.assertEqual(result["unregistered_row_count"], 0)
            self.assertFalse(result["coordinates_are_authority"])
            self.assertEqual(result["identity_authority"], "OccurrenceIdentityV2")
            self.assertEqual(result["exact_location_authority"], "Projector V3")
            self.assertEqual(
                result["governing_rule"],
                "STORE FIRST. IDENTIFY SECOND. RESOLVE THIRD. PUBLISH LAST.",
            )


if __name__ == "__main__":
    unittest.main()
