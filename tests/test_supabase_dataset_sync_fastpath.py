from __future__ import annotations

import os
import unittest
from unittest import mock

from scripts import supabase_dataset_sync_fastpath as fast


class SupabaseDatasetSyncFastpathTests(unittest.TestCase):
    def rows(self):
        return [
            {
                "occurrence_id": "a" * 64,
                "source": {"source_name": "NYCIF", "source_dataset": "example"},
                "metadata": {"reader": {}},
            },
            {
                "occurrence_id": "b" * 64,
                "source": {"source_name": "NYCIF", "source_dataset": "example"},
                "metadata": {"reader": {}},
            },
        ]

    @mock.patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "service"}, clear=False)
    def test_exact_active_membership_skips_expiration_finalizer(self) -> None:
        rows = self.rows()
        expected = {row["occurrence_id"] for row in rows}
        with mock.patch.object(fast.writer, "validate_write_target", return_value=("oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co")), \
             mock.patch.object(fast.writer, "post_atomic_batch", return_value={
                 "transaction": "committed",
                 "newsroom_queue_delta": 0,
                 "actions": {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 2, "EXPIRE": 0},
                 "pipeline_run_id": 1,
                 "quality_changes": 0,
                 "classification_changes": 0,
             }), \
             mock.patch.object(fast.base, "_post_rpc", return_value={"transaction": "committed", "staged_count": 2}) as rpc, \
             mock.patch.object(fast, "active_dataset_occurrence_ids", return_value=expected), \
             mock.patch.object(fast, "cleanup_staged_membership") as cleanup:
            result = fast.run_sync(rows, "example", 50, write_enabled=True)

        self.assertEqual(result["finalizer_mode"], "exact_membership_no_expiration")
        self.assertEqual(result["source_rows_inactivated"], 0)
        self.assertEqual(result["actions"]["EXPIRE"], 0)
        self.assertEqual(result["membership_staged_count"], 2)
        self.assertEqual(rpc.call_count, 1)
        self.assertEqual(rpc.call_args.args[2], "nycif_stage_event_dataset_membership")
        cleanup.assert_called_once()

    @mock.patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "service"}, clear=False)
    def test_extra_active_membership_requires_expiration_finalizer(self) -> None:
        rows = self.rows()
        active = {row["occurrence_id"] for row in rows} | {"c" * 64}

        def rpc(_url, _key, function_name, _payload):
            if function_name == "nycif_stage_event_dataset_membership":
                return {"transaction": "committed", "staged_count": 2}
            if function_name == "nycif_finalize_event_dataset_sync":
                return {
                    "transaction": "committed",
                    "staged_count": 2,
                    "source_rows_inactivated": 1,
                    "pipeline_run_id": 9,
                    "actions": {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 2, "EXPIRE": 1},
                }
            raise AssertionError(function_name)

        with mock.patch.object(fast.writer, "validate_write_target", return_value=("oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co")), \
             mock.patch.object(fast.writer, "post_atomic_batch", return_value={
                 "transaction": "committed",
                 "newsroom_queue_delta": 0,
                 "actions": {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 2, "EXPIRE": 0},
                 "pipeline_run_id": 1,
                 "quality_changes": 0,
                 "classification_changes": 0,
             }), \
             mock.patch.object(fast.base, "_post_rpc", side_effect=rpc) as rpc_mock, \
             mock.patch.object(fast, "active_dataset_occurrence_ids", return_value=active), \
             mock.patch.object(fast, "cleanup_staged_membership") as cleanup:
            result = fast.run_sync(rows, "example", 50, write_enabled=True)

        self.assertEqual(result["finalizer_mode"], "rpc_expiration_finalizer_extra_1")
        self.assertEqual(result["source_rows_inactivated"], 1)
        self.assertEqual(result["actions"]["EXPIRE"], 1)
        self.assertEqual(rpc_mock.call_count, 2)
        cleanup.assert_not_called()

    @mock.patch.dict(os.environ, {"SUPABASE_SERVICE_ROLE_KEY": "service"}, clear=False)
    def test_missing_canonical_membership_fails_closed(self) -> None:
        rows = self.rows()
        active = {rows[0]["occurrence_id"]}
        with mock.patch.object(fast.writer, "validate_write_target", return_value=("oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co")), \
             mock.patch.object(fast.writer, "post_atomic_batch", return_value={
                 "transaction": "committed", "newsroom_queue_delta": 0,
                 "actions": {}, "pipeline_run_id": 1,
             }), \
             mock.patch.object(fast.base, "_post_rpc", return_value={"transaction": "committed", "staged_count": 2}), \
             mock.patch.object(fast, "active_dataset_occurrence_ids", return_value=active), \
             mock.patch.object(fast, "cleanup_staged_membership"):
            with self.assertRaisesRegex(RuntimeError, "missing 1 canonical occurrence IDs"):
                fast.run_sync(rows, "example", 50, write_enabled=True)


if __name__ == "__main__":
    unittest.main()
