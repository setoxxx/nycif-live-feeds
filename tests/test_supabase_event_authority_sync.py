from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import sync_supabase_event_authority as sync


class SupabaseEventAuthoritySyncTests(unittest.TestCase):
    def normalized_row(self, index: int, dataset: str = "tvpp-9vvx") -> dict:
        return {
            "occurrence_id": f"{index + 1:064x}",
            "source": {
                "source_name": "nyc_open_data",
                "source_dataset": dataset,
                "source_event_id": str(index + 1),
            },
            "metadata": {"reader": {"source_dataset": dataset}},
        }

    def test_dry_run_is_bounded_and_does_not_write(self) -> None:
        rows = [self.normalized_row(i) for i in range(1201)]
        with mock.patch.object(sync.writer, "validate_write_target") as validate_target, \
             mock.patch.object(sync.writer, "post_atomic_batch") as atomic_write, \
             mock.patch.object(sync, "_post_rpc") as post_rpc:
            result = sync.run_sync(rows, "tvpp-9vvx", 500, write_enabled=False)

        self.assertEqual(result["input_count"], 1201)
        self.assertEqual(result["chunk_size"], 500)
        self.assertEqual(result["chunk_count"], 3)
        self.assertFalse(result["database_write_performed"])
        validate_target.assert_not_called()
        atomic_write.assert_not_called()
        post_rpc.assert_not_called()

    def test_write_stages_every_chunk_before_single_finalizer(self) -> None:
        rows = [self.normalized_row(i) for i in range(120)]
        atomic_results = [
            {
                "transaction": "committed",
                "pipeline_run_id": 101 + i,
                "newsroom_queue_delta": 0,
                "actions": {"INSERT": 50 if i < 2 else 20, "UPDATE": 0, "UNCHANGED": 0, "EXPIRE": 0},
                "quality_changes": 0,
                "classification_changes": 0,
            }
            for i in range(3)
        ]
        rpc_calls: list[tuple[str, dict]] = []

        def fake_rpc(target_url: str, service_key: str, function_name: str, payload: dict, timeout: int = 120):
            rpc_calls.append((function_name, payload))
            if function_name == "nycif_stage_event_dataset_membership":
                staged_before = sum(
                    len(call_payload["p_occurrence_ids"])
                    for call_name, call_payload in rpc_calls
                    if call_name == "nycif_stage_event_dataset_membership"
                )
                return {
                    "transaction": "committed",
                    "staged_count": staged_before,
                    "expected_count": 120,
                }
            if function_name == "nycif_finalize_event_dataset_sync":
                return {
                    "transaction": "committed",
                    "pipeline_run_id": 104,
                    "staged_count": 120,
                    "expected_count": 120,
                    "source_rows_inactivated": 4,
                    "actions": {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 120, "EXPIRE": 4},
                    "newsroom_queue_delta": 0,
                }
            raise AssertionError(function_name)

        env = {
            "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
        }
        with mock.patch.dict(os.environ, env, clear=False), \
             mock.patch.object(
                 sync.writer,
                 "validate_write_target",
                 return_value=("oggwpvdirkrnzoolparx", "https://oggwpvdirkrnzoolparx.supabase.co"),
             ), \
             mock.patch.object(sync.writer, "post_atomic_batch", side_effect=atomic_results) as atomic_write, \
             mock.patch.object(sync, "_post_rpc", side_effect=fake_rpc):
            result = sync.run_sync(rows, "tvpp-9vvx", 50, write_enabled=True)

        self.assertEqual(atomic_write.call_count, 3)
        for call in atomic_write.call_args_list:
            payload = call.args[2]
            self.assertFalse(payload["p_allow_expire"])
            self.assertFalse(payload["p_simulate_failure"])
            self.assertEqual(payload["p_source_name"], "nyc_open_data")
            self.assertLessEqual(len(payload["p_events"]), 50)

        self.assertEqual([name for name, _ in rpc_calls], [
            "nycif_stage_event_dataset_membership",
            "nycif_stage_event_dataset_membership",
            "nycif_stage_event_dataset_membership",
            "nycif_finalize_event_dataset_sync",
        ])
        stage_payloads = [payload for name, payload in rpc_calls if name == "nycif_stage_event_dataset_membership"]
        tokens = {payload["p_sync_token"] for payload in stage_payloads}
        self.assertEqual(len(tokens), 1)
        self.assertEqual({payload["p_expected_count"] for payload in stage_payloads}, {120})
        final_payload = rpc_calls[-1][1]
        self.assertEqual(final_payload["p_sync_token"], next(iter(tokens)))
        self.assertEqual(final_payload["p_expected_count"], 120)
        self.assertEqual(result["actions"]["INSERT"], 120)
        self.assertEqual(result["actions"]["EXPIRE"], 4)
        self.assertEqual(result["membership_staged_count"], 120)
        self.assertTrue(result["database_write_performed"])

    def test_one_sync_cannot_mix_source_datasets(self) -> None:
        rows = [self.normalized_row(1), self.normalized_row(2, dataset="other-dataset")]
        with self.assertRaisesRegex(RuntimeError, "dataset filter"):
            sync.run_sync(rows, "tvpp-9vvx", 50, write_enabled=False)

    def test_duplicate_occurrence_ids_fail_closed(self) -> None:
        occurrence_id = "a" * 64
        payload = {
            "events": [
                {
                    "occurrence_id": occurrence_id,
                    "title": "Duplicate A",
                    "start_date_time": "2026-08-20T10:00:00",
                    "timezone": "America/New_York",
                    "source": {"dataset": "tvpp-9vvx", "source_event_id": "1"},
                },
                {
                    "occurrence_id": occurrence_id,
                    "title": "Duplicate B",
                    "start_date_time": "2026-08-20T11:00:00",
                    "timezone": "America/New_York",
                    "source": {"dataset": "tvpp-9vvx", "source_event_id": "2"},
                },
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "canonical.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "duplicate OccurrenceIdentityV2"):
                sync.normalized_dataset_rows(path, "tvpp-9vvx")

    def test_impossible_interval_is_preserved_but_forced_to_review_list_only(self) -> None:
        event = {
            "title": "Impossible interval fixture",
            "start_date_time": "2026-08-20T15:00:00",
            "end_date_time": "2026-08-20T14:00:00",
            "timezone": "America/New_York",
            "source": {"dataset": "tvpp-9vvx", "source_event_id": "interval-1"},
            "nycif": {"certified_pin": True, "display_disposition": "standalone_public_event"},
        }
        prepared = sync.prepare_event_for_authority(event)
        self.assertEqual(prepared["quality"]["quality_status"], "REVIEW_REQUIRED")
        self.assertEqual(prepared["quality"]["public_display_status"], "LIST_ONLY")
        self.assertIn("END_BEFORE_START", prepared["quality"]["quality_flags"])
        self.assertIn("reader", prepared["metadata"])
        self.assertEqual(prepared["metadata"]["reader"]["source_dataset"], "tvpp-9vvx")
        self.assertEqual(prepared["metadata"]["reader"]["source_event_id"], "interval-1")

    def test_chunk_size_guard_rejects_unbounded_requests(self) -> None:
        rows = [self.normalized_row(i) for i in range(10)]
        with self.assertRaises(ValueError):
            sync.run_sync(rows, "tvpp-9vvx", 1001, write_enabled=False)
        with self.assertRaises(ValueError):
            sync.run_sync(rows, "tvpp-9vvx", 49, write_enabled=False)


if __name__ == "__main__":
    unittest.main()
