#!/usr/bin/env python3
"""Timeout-safe dataset sync using exact live membership proof.

The existing dataset finalizer remains the only expiration authority. This helper
only skips that expensive anti-join when a service-role REST read proves that the
active `event_sources` occurrence-id set for the exact source_name/source_dataset
is already identical to the complete canonical set just staged. In that case the
finalizer has no rows it is allowed to expire, so cleanup of the temporary
membership token is sufficient and cannot weaken expiration semantics.
"""
from __future__ import annotations

import copy
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from scripts import supabase_event_writer as writer
from scripts import sync_supabase_event_authority as base

REST_PAGE_SIZE = 1000


def _service_request(
    target_url: str,
    service_key: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    prefer: str | None = None,
    timeout: int = 120,
) -> bytes:
    headers = {
        "apikey": service_key,
        "authorization": f"Bearer {service_key}",
    }
    if body is not None:
        headers["content-type"] = "application/json"
    if prefer:
        headers["prefer"] = prefer
    request = urllib.request.Request(
        target_url.rstrip("/") + path,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise writer.SupabaseRPCError(
            f"dataset membership REST {method} failed with HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise writer.SupabaseRPCError(
            f"dataset membership REST {method} connection failed: {exc.reason}"
        ) from exc


def active_dataset_occurrence_ids(
    target_url: str,
    service_key: str,
    source_name: str,
    dataset: str,
) -> set[str]:
    ids: set[str] = set()
    offset = 0
    while True:
        query = urllib.parse.urlencode(
            {
                "select": "occurrence_id",
                "source_name": f"eq.{source_name}",
                "source_dataset": f"eq.{dataset}",
                "source_active": "eq.true",
                "order": "occurrence_id.asc",
                "limit": str(REST_PAGE_SIZE),
                "offset": str(offset),
            }
        )
        body = _service_request(
            target_url,
            service_key,
            f"/rest/v1/event_sources?{query}",
        )
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, list):
            raise writer.SupabaseRPCError("event_sources membership read was not a JSON array")
        page: list[str] = []
        for row in payload:
            occurrence_id = row.get("occurrence_id") if isinstance(row, dict) else None
            if not isinstance(occurrence_id, str) or not occurrence_id:
                raise writer.SupabaseRPCError("event_sources membership row missing occurrence_id")
            page.append(occurrence_id)
        ids.update(page)
        if len(page) < REST_PAGE_SIZE:
            break
        offset += REST_PAGE_SIZE
    return ids


def cleanup_staged_membership(
    target_url: str,
    service_key: str,
    token: str,
    source_name: str,
    dataset: str,
) -> None:
    query = urllib.parse.urlencode(
        {
            "sync_token": f"eq.{token}",
            "source_name": f"eq.{source_name}",
            "source_dataset": f"eq.{dataset}",
        }
    )
    _service_request(
        target_url,
        service_key,
        f"/rest/v1/event_dataset_sync_membership?{query}",
        method="DELETE",
        prefer="return=minimal",
    )


def run_sync(
    rows: list[dict[str, Any]],
    dataset: str,
    chunk_size: int,
    *,
    write_enabled: bool,
) -> dict[str, Any]:
    chunk_size = base._chunk_size(chunk_size)
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
            "run_type": "supabase_authority_sync_dry_run",
            "dataset": dataset,
            "input_count": expected_count,
            "chunk_size": chunk_size,
            "chunk_count": chunk_count,
            "sync_token_generated": True,
            "reader_metadata_rows": sum(
                1 for row in rows if isinstance(row.get("metadata", {}).get("reader"), dict)
            ),
            "database_write_performed": False,
        }

    project_ref, target_url = writer.validate_write_target()
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_key:
        raise writer.WriteGuardError("SUPABASE_SERVICE_ROLE_KEY is required in the environment")
    source_name = next(iter(source_names))
    expected_ids = {row["occurrence_id"] for row in rows}
    if len(expected_ids) != expected_count:
        raise RuntimeError("duplicate occurrence IDs reached dataset sync")

    for index in range(chunk_count):
        start = index * chunk_size
        chunk = copy.deepcopy(rows[start : start + chunk_size])
        result = writer.post_atomic_batch(
            target_url,
            service_key,
            {
                "p_events": chunk,
                "p_source_name": source_name,
                "p_allow_expire": False,
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
        quality_changes += int(result.get("quality_changes", 0) or 0)
        classification_changes += int(result.get("classification_changes", 0) or 0)
        staged = base._post_rpc(
            target_url,
            service_key,
            "nycif_stage_event_dataset_membership",
            {
                "p_sync_token": token,
                "p_source_name": source_name,
                "p_source_dataset": dataset,
                "p_occurrence_ids": [row["occurrence_id"] for row in chunk],
                "p_expected_count": expected_count,
                "p_expected_project_ref": project_ref,
            },
        )
        if int(staged.get("staged_count", 0)) > expected_count:
            raise RuntimeError("staged membership exceeded expected corpus count")

    active_ids = active_dataset_occurrence_ids(target_url, service_key, source_name, dataset)
    finalizer_mode = "rpc_expiration_finalizer"
    source_rows_inactivated = 0
    membership_staged_count = expected_count

    if active_ids == expected_ids:
        # Exact set equality proves there are no absent active source rows for the
        # finalizer to expire. Clean only the temporary staging token.
        cleanup_staged_membership(target_url, service_key, token, source_name, dataset)
        finalizer_mode = "exact_membership_no_expiration"
    else:
        missing = sorted(expected_ids - active_ids)
        extra = sorted(active_ids - expected_ids)
        if missing:
            raise RuntimeError(
                f"active dataset membership missing {len(missing)} canonical occurrence IDs"
            )
        finalized = base._post_rpc(
            target_url,
            service_key,
            "nycif_finalize_event_dataset_sync",
            {
                "p_sync_token": token,
                "p_source_name": source_name,
                "p_source_dataset": dataset,
                "p_expected_count": expected_count,
                "p_expected_project_ref": project_ref,
            },
        )
        final_actions = finalized.get("actions") if isinstance(finalized.get("actions"), dict) else {}
        aggregate["EXPIRE"] += int(final_actions.get("EXPIRE", 0) or 0)
        final_run_id = finalized.get("pipeline_run_id")
        if isinstance(final_run_id, int):
            pipeline_run_ids.append(final_run_id)
        source_rows_inactivated = int(finalized.get("source_rows_inactivated", 0) or 0)
        membership_staged_count = int(finalized.get("staged_count", 0) or 0)
        finalizer_mode = f"rpc_expiration_finalizer_extra_{len(extra)}"

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
        "membership_staged_count": membership_staged_count,
        "finalizer_mode": finalizer_mode,
        "database_write_performed": True,
    }
