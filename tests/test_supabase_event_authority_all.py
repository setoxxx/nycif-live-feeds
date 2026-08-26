from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import sync_supabase_event_authority_all as sync_all


class SupabaseEventAuthorityAllTests(unittest.TestCase):
    def write_canonical(self, root: Path) -> Path:
        path = root / "canonical.json"
        payload = {
            "events": [
                {"source": {"dataset": "tvpp-9vvx", "source_event_id": "1"}},
                {"source": {"dataset": "citywide-calendar", "source_event_id": "2"}},
                {"source": {"dataset": "parks-events", "source_event_id": "3"}},
                {"source": {"dataset": "tvpp-9vvx", "source_event_id": "4"}},
            ]
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_canonical_datasets_enumerates_every_dataset_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_canonical(Path(tmp))
            self.assertEqual(
                sync_all.canonical_datasets(path),
                ["citywide-calendar", "parks-events", "tvpp-9vvx"],
            )

    def test_run_all_invokes_existing_dataset_scoped_transaction_per_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_canonical(Path(tmp))
            rows_by_dataset = {
                "citywide-calendar": [{"occurrence_id": "1"}],
                "parks-events": [{"occurrence_id": "2"}],
                "tvpp-9vvx": [{"occurrence_id": "3"}, {"occurrence_id": "4"}],
            }

            def normalized(_path: Path, dataset: str):
                return rows_by_dataset[dataset]

            def run_sync(rows, dataset: str, chunk_size: int, *, write_enabled: bool):
                self.assertIs(rows, rows_by_dataset[dataset])
                self.assertEqual(chunk_size, sync_all.TIMEOUT_SAFE_CHUNK_SIZE)
                self.assertFalse(write_enabled)
                return {
                    "dataset": dataset,
                    "input_count": len(rows),
                    "reader_metadata_rows": len(rows),
                    "actions": {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 0, "EXPIRE": 0},
                    "database_write_performed": False,
                }

            with mock.patch.object(sync_all.dataset_sync, "normalized_dataset_rows", side_effect=normalized), \
                 mock.patch.object(sync_all.dataset_sync, "run_sync", side_effect=run_sync) as called:
                result = sync_all.run_all(path, 500, write_enabled=False)

        self.assertEqual(called.call_count, 3)
        self.assertEqual(result["dataset_count"], 3)
        self.assertEqual(result["requested_chunk_size"], 500)
        self.assertEqual(result["effective_chunk_size"], sync_all.TIMEOUT_SAFE_CHUNK_SIZE)
        self.assertEqual(result["input_count"], 4)
        self.assertEqual(result["reader_metadata_rows"], 4)
        self.assertFalse(result["database_write_performed"])

    def test_smaller_caller_batch_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_canonical(Path(tmp))
            with mock.patch.object(sync_all.dataset_sync, "normalized_dataset_rows", return_value=[{"occurrence_id": "1"}]), \
                 mock.patch.object(sync_all.dataset_sync, "run_sync", return_value={
                     "input_count": 1,
                     "reader_metadata_rows": 1,
                     "actions": {},
                     "database_write_performed": False,
                 }) as called:
                result = sync_all.run_all(path, 50, write_enabled=False)
        self.assertEqual(result["effective_chunk_size"], 50)
        self.assertTrue(all(call.args[2] == 50 for call in called.call_args_list))

    def test_empty_canonical_corpus_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical.json"
            path.write_text(json.dumps({"events": []}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "no source datasets"):
                sync_all.canonical_datasets(path)


if __name__ == "__main__":
    unittest.main()
