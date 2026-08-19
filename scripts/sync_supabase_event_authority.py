#!/usr/bin/env python3
"""Chunked NYCIF Events authority sync.

Heavy canonical processing stays on the GitHub runner. Supabase remains the
atomic write boundary through the existing Rung 8 RPC. The full corpus is never
sent in one request: membership is staged across bounded chunks using a shared
sync token, and source expiration is allowed only on the final chunk after the
RPC proves the complete expected membership has been staged.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import supabase_event_writer as writer

DEFAULT_INPUT = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
DEFAULT_DATASET = "tvpp-9vvx"
DEFAULT_CHUNK_SIZE = 500
MAX_CHUNK_SIZE = 1000
MIN_CHUNK_SIZE = 50


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def apply_interval_quality(event: dict[str, Any]) -> dict[str, Any]:
    """Flag impossible intervals without discarding the occurrence.

    Existing quality data is preserved. When end < start, the row is retained
    for lineage/accounting but cannot be treated as a clean full-time display.
    """
    result = copy.deepcopy(event)
    start = _parse_dt(result.get("start_at") or result.get("start_date_time"))
    end = _parse_dt(result.get("end_at") or result.get("end_date_time"))
    if start is None or end is None or end >= start:
        return result

    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    quality = dict(quality)
    flags = quality.get("quality_flags") if isinstance(quality.get("quality_flags"), list) else []
    flags = list(flags)
    if "END_BEFORE_START" not in flags:
        flags.append("END_BEFORE_START")
    details = quality.get("details") if isinstance(quality.get("details"), dict) else {}
    details = dict(details)
    details.update(
        {
            "interval_issue": "end_before_start",
            "start_at": str(result.get("start_at") or result.get("start_date_time")),
            "end_at": str(result.get("end_at") or result.get("end_date_time")),
        }
    )
    quality.update(
        {
            "quality_status": "REVIEW_REQUIRED",
            "quality_flags": flags,
            "public_display_status": "LIST_ONLY",
            "details": details,
        }
    )
    result["quality"] = quality
    return result


def canonical_events(path: Path) -> list[dict[str, Any]]:
    payload = writer.load_json(path)
    return writer.extract_events(payload)


def normalized_dataset_rows(path: Path, dataset: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in canonical_events(path):
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        source_dataset = str(source.get("source_dataset") or source.get("dataset") or "")
        if source_dataset != dataset:
            continue
        rows.append(writer.normalize_event(apply_interval_quality(event)))

    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        occurrence_id = row["occurrence_id"]
        if occurrence_id in seen:
            duplicates.append(occurrence_id)
        seen.add(occurrence_id)
    if duplicates:
        raise RuntimeError(
            f"duplicate OccurrenceIdentityV2 IDs in {dataset}: {len(duplicates)}"
        )
    if not rows:
        raise RuntimeError(f"no canonical rows found for source dataset {dataset!r}")
    return rows


def _chunk_size(value: int) -> int:
    if value < MIN_CHUNK_SIZE or value > MAX_CHUNK_SIZE:
        raise ValueError(
            f"chunk size must be between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE}"
        )
    return value


def run_sync(
    rows: list[dict[str, Any]],
    dataset: str,
    chunk_size: int,
    *,
    write_enabled: bool,
) -> dict[str, Any]:
    chunk_size = _chunk_size(chunk_size)
    source_names = {row["source"]["source_name"] for row in rows}
    source_datasets = {row["source"]["source_dataset"] for row in rows}
    if len(source_names) != 1:
        raise RuntimeError("one sync must contain exactly one source_name")
    if source_datasets != {dataset}:
        raise RuntimeError("dataset filter does not match normalized source lineage")

    token = str(uuid.uuid4())
    expected_count = len(rows)
    chunk_count = (expected_count + chunk_size - 1) // chunk_size
    started = time.monotonic()
    aggregate = {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 0, "EXPIRE": 0}
    pipeline_run_ids: list[int] = []
    source_rows_inactivated = 0
    quality_changes = 0
    classification_changes = 0

    if not write_enabled:
        return {
            "run_type": "supabase_authority_sync_dry_run",
            "dataset": dataset,
            "input_count": expected_count,
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "sync_token_generated": True,
            "database_write_performed": False,
        }

    project_ref, target_url = writer.validate_write_target()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_key:
        raise writer.WriteGuardError(
            "SUPABASE_SERVICE_ROLE_KEY is required in the environment"
        )

    for index in range(chunk_count):
        start = index * chunk_size
        chunk = copy.deepcopy(rows[start : start + chunk_size])
        for row in chunk:
            row["_sync_token"] = token
            row["_sync_expected_count"] = expected_count
            row["_sync_chunk_index"] = index + 1
            row["_sync_chunk_count"] = chunk_count

        final_chunk = index == chunk_count - 1
        result = writer.post_atomic_batch(
            target_url,
            service_key,
            {
                "p_events": chunk,
                "p_source_name": next(iter(source_names)),
                "p_allow_expire": final_chunk,
                "p_simulate_failure": False,
                "p_expected_project_ref": project_ref,
            },
        )
        if result.get("newsroom_queue_delta") != 0:
            raise RuntimeError("Supabase sync mutated newsroom_queue")
        actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
        for action in aggregate:
            aggregate[action] += int(actions.get(action, 0) or 0)
        run_id = result.get("pipeline_run_id")
        if isinstance(run_id, int):
            pipeline_run_ids.append(run_id)
        source_rows_inactivated += int(result.get("source_rows_inactivated", 0) or 0)
        quality_changes += int(result.get("quality_changes", 0) or 0)
        classification_changes += int(result.get("classification_changes", 0) or 0)

    return {
        "run_type": "supabase_authority_sync",
        "dataset": dataset,
        "input_count": expected_count,
        "chunk_size": chunk_size,
        "chunk_count": chunk_count,
        "duration_seconds": round(time.monotonic() - started, 3),
        "actions": aggregate,
        "source_rows_inactivated": source_rows_inactivated,
        "quality_changes": quality_changes,
        "classification_changes": classification_changes,
        "pipeline_run_ids": pipeline_run_ids,
        "database_write_performed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=int(os.environ.get("NYCIF_SUPABASE_SYNC_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)),
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    rows = normalized_dataset_rows(Path(args.input), args.dataset)
    result = run_sync(
        rows,
        args.dataset,
        args.chunk_size,
        write_enabled=args.write,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
