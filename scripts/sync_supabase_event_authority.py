#!/usr/bin/env python3
"""Chunked NYCIF Events authority sync.

Heavy canonical processing stays on the GitHub runner. Supabase remains the
canonical data home and atomic write boundary through the existing Rung 8 RPC.
The full corpus is never sent in one request. Event rows are written in bounded
chunks with expiration disabled; membership is staged separately and a guarded
dataset finalizer expires only records absent from the complete staged corpus.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import supabase_event_writer as writer

DEFAULT_INPUT = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
DEFAULT_DATASET = "tvpp-9vvx"
# Rung-8 performs several relational comparisons/upserts per row. A 500-row
# live multi-source bootstrap exceeded the hosted Postgres statement timeout.
# Keep batches deliberately small; membership finalization remains dataset-scoped.
DEFAULT_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 500
MIN_CHUNK_SIZE = 50
NYC_TZ = ZoneInfo("America/New_York")


def _parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _aware_iso(value: Any, timezone_name: str) -> Any:
    if value in (None, ""):
        return value
    parsed = _parse_dt(value)
    if parsed is None:
        return value
    if parsed.tzinfo is None:
        try:
            zone = ZoneInfo(timezone_name)
        except Exception:
            zone = NYC_TZ
        parsed = parsed.replace(tzinfo=zone)
    return parsed.isoformat()


def _safe_public_url(event: dict[str, Any]) -> str | None:
    for key in ("public_url", "permalink", "link", "website", "url"):
        value = event.get(key)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if value.lower().startswith(("https://", "http://")):
            return value
    return None


def prepare_event_for_authority(event: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(event)
    timezone_name = str(result.get("timezone") or "America/New_York")
    result["timezone"] = timezone_name
    for key in ("start_at", "start_date_time", "end_at", "end_date_time"):
        if key in result:
            result[key] = _aware_iso(result.get(key), timezone_name)

    source = result.get("source") if isinstance(result.get("source"), dict) else {}
    nycif = result.get("nycif") if isinstance(result.get("nycif"), dict) else {}
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    metadata = dict(metadata)
    existing_reader = metadata.get("reader") if isinstance(metadata.get("reader"), dict) else {}
    reader = dict(existing_reader)
    source_dataset = str(source.get("source_dataset") or source.get("dataset") or "")
    source_event_id = str(source.get("source_event_id") or "")

    canonical_reader = {
        "event_role": result.get("event_role"),
        "parent_event_id": result.get("parent_event_id"),
        "display_disposition": nycif.get("display_disposition"),
        "map_eligibility_state": nycif.get("map_eligibility_state"),
        "certified_pin": nycif.get("certified_pin"),
        "location_authority": nycif.get("location_authority"),
        "significance": result.get("significance"),
        "public_url": _safe_public_url(result),
        "is_major": nycif.get("is_major"),
        "photo_pick": nycif.get("photo_pick"),
        "neighborhood": result.get("neighborhood"),
        "source_dataset": source_dataset,
        "source_event_id": source_event_id,
    }
    for key, value in canonical_reader.items():
        if value is not None and value != "":
            reader[key] = value
    metadata["reader"] = reader
    result["metadata"] = metadata

    start = _parse_dt(result.get("start_at") or result.get("start_date_time"))
    end = _parse_dt(result.get("end_at") or result.get("end_date_time"))
    if start is not None and end is not None and end < start:
        quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
        quality = dict(quality)
        flags = quality.get("quality_flags") if isinstance(quality.get("quality_flags"), list) else []
        flags = list(flags)
        if "END_BEFORE_START" not in flags:
            flags.append("END_BEFORE_START")
        details = quality.get("details") if isinstance(quality.get("details"), dict) else {}
        details = dict(details)
        details.update({
            "interval_issue": "end_before_start",
            "start_at": str(result.get("start_at") or result.get("start_date_time")),
            "end_at": str(result.get("end_at") or result.get("end_date_time")),
        })
        quality.update({
            "quality_status": "REVIEW_REQUIRED",
            "quality_flags": flags,
            "public_display_status": "LIST_ONLY",
            "details": details,
        })
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
        rows.append(writer.normalize_event(prepare_event_for_authority(event)))
    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        occurrence_id = row["occurrence_id"]
        if occurrence_id in seen:
            duplicates.append(occurrence_id)
        seen.add(occurrence_id)
    if duplicates:
        raise RuntimeError(f"duplicate OccurrenceIdentityV2 IDs in {dataset}: {len(duplicates)}")
    if not rows:
        raise RuntimeError(f"no canonical rows found for source dataset {dataset!r}")
    return rows


def _chunk_size(value: int) -> int:
    if value < MIN_CHUNK_SIZE or value > MAX_CHUNK_SIZE:
        raise ValueError(f"chunk size must be between {MIN_CHUNK_SIZE} and {MAX_CHUNK_SIZE}")
    return value


def _post_rpc(target_url: str, service_key: str, function_name: str, payload: dict[str, Any], timeout: int = 120):
    request = urllib.request.Request(
        f"{target_url}/rest/v1/rpc/{function_name}",
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={"apikey": service_key, "authorization": f"Bearer {service_key}", "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise writer.SupabaseRPCError(f"{function_name} failed with HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise writer.SupabaseRPCError(f"{function_name} connection failed: {exc.reason}") from exc
    result = json.loads(body)
    if not isinstance(result, dict) or result.get("transaction") != "committed":
        raise writer.SupabaseRPCError(f"{function_name} returned an invalid success document")
    return result


def run_sync(rows: list[dict[str, Any]], dataset: str, chunk_size: int, *, write_enabled: bool) -> dict[str, Any]:
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
    quality_changes = 0
    classification_changes = 0

    if not write_enabled:
        return {
            "run_type": "supabase_authority_sync_dry_run", "dataset": dataset,
            "input_count": expected_count, "chunk_size": chunk_size, "chunk_count": chunk_count,
            "sync_token_generated": True,
            "reader_metadata_rows": sum(1 for row in rows if isinstance(row.get("metadata", {}).get("reader"), dict)),
            "database_write_performed": False,
        }

    project_ref, target_url = writer.validate_write_target()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_key:
        raise writer.WriteGuardError("SUPABASE_SERVICE_ROLE_KEY is required in the environment")
    source_name = next(iter(source_names))

    for index in range(chunk_count):
        start = index * chunk_size
        chunk = copy.deepcopy(rows[start : start + chunk_size])
        result = writer.post_atomic_batch(target_url, service_key, {
            "p_events": chunk,
            "p_source_name": source_name,
            "p_allow_expire": False,
            "p_simulate_failure": False,
            "p_expected_project_ref": project_ref,
        })
        if result.get("newsroom_queue_delta") != 0:
            raise RuntimeError("Supabase sync mutated newsroom_queue")
        actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
        for action in aggregate:
            aggregate[action] += int(actions.get(action, 0) or 0)
        run_id = result.get("pipeline_run_id")
        if isinstance(run_id, int):
            pipeline_run_ids.append(run_id)
        quality_changes += int(result.get("quality_changes", 0) or 0)
        classification_changes += int(result.get("classification_changes", 0) or 0)
        staged = _post_rpc(target_url, service_key, "nycif_stage_event_dataset_membership", {
            "p_sync_token": token,
            "p_source_name": source_name,
            "p_source_dataset": dataset,
            "p_occurrence_ids": [row["occurrence_id"] for row in chunk],
            "p_expected_count": expected_count,
            "p_expected_project_ref": project_ref,
        })
        if int(staged.get("staged_count", 0)) > expected_count:
            raise RuntimeError("staged membership exceeded expected corpus count")

    finalized = _post_rpc(target_url, service_key, "nycif_finalize_event_dataset_sync", {
        "p_sync_token": token,
        "p_source_name": source_name,
        "p_source_dataset": dataset,
        "p_expected_count": expected_count,
        "p_expected_project_ref": project_ref,
    })
    final_actions = finalized.get("actions") if isinstance(finalized.get("actions"), dict) else {}
    aggregate["EXPIRE"] += int(final_actions.get("EXPIRE", 0) or 0)
    final_run_id = finalized.get("pipeline_run_id")
    if isinstance(final_run_id, int):
        pipeline_run_ids.append(final_run_id)

    return {
        "run_type": "supabase_authority_sync", "dataset": dataset, "input_count": expected_count,
        "chunk_size": chunk_size, "chunk_count": chunk_count,
        "duration_seconds": round(time.monotonic() - started, 3), "actions": aggregate,
        "source_rows_inactivated": int(finalized.get("source_rows_inactivated", 0) or 0),
        "quality_changes": quality_changes, "classification_changes": classification_changes,
        "pipeline_run_ids": pipeline_run_ids,
        "membership_staged_count": int(finalized.get("staged_count", 0) or 0),
        "database_write_performed": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--chunk-size", type=int, default=int(os.environ.get("NYCIF_SUPABASE_SYNC_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)))
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    rows = normalized_dataset_rows(Path(args.input), args.dataset)
    result = run_sync(rows, args.dataset, args.chunk_size, write_enabled=args.write)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
