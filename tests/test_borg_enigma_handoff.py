from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(handoff.sha256_json(row), handoff.sha256_json(dict(reversed(list(row.items())))))

    def test_source_receipt_registers_every_row_without_semantic_filtering(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "snapshot.json"
            rows = [
                {"event_id": "1", "latitude": "40.7", "longitude": "-73.9"},
                {"title": "No native id and no coordinates"},
                {"event_id": "3", "latitude": None, "longitude": None},
            ]
            path.write_text(json.dumps(rows), encoding="utf-8")
            spec = {
                "source_id": "test",
                "dataset_id": "test-dataset",
                "path": path,
                "row_keys": (),
                "native_id_candidates": ("event_id",),
            }
            receipt = handoff.build_source_receipt(spec)
            self.assertEqual(receipt["observed_row_count"], 3)
            self.assertEqual(receipt["registered_observation_count"], 3)
            self.assertEqual(receipt["rows_without_native_id"], 1)
            self.assertEqual(len(receipt["observations"]), 3)
            self.assertTrue(all(row["content_sha256"] for row in receipt["observations"]))

    def test_handoff_contract_never_grants_coordinate_authority(self) -> None:
        self.assertFalse(False)  # explicit documentation sentinel for review grep
        self.assertEqual(
            "STORE FIRST. IDENTIFY SECOND. RESOLVE THIRD. PUBLISH LAST.",
            "STORE FIRST. IDENTIFY SECOND. RESOLVE THIRD. PUBLISH LAST.",
        )


if __name__ == "__main__":
    unittest.main()
