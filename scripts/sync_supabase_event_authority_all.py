#!/usr/bin/env python3
"""Sync every source dataset in the canonical NYCIF event authority to Supabase.

The underlying sync remains dataset-scoped so membership finalization and expiration
cannot cross source-dataset boundaries. This orchestrator removes the historical
TVPP-only bootstrap assumption by enumerating every non-empty source dataset in the
post-Projector-V3 canonical corpus and running the existing bounded transaction for
each dataset.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from scripts import sync_supabase_event_authority as dataset_sync

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
DEFAULT_CHUNK_SIZE = 500


def source_dataset(event: dict[str, Any]) -> str:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return str(source.get("source_dataset") or source.get("dataset") or "").strip()


def canonical_datasets(path: Path) -> list[str]:
    datasets = sorted(
        {
            source_dataset(event)
            for event in dataset_sync.canonical_events(path)
            if isinstance(event, dict) and source_dataset(event)
        }
    )
    if not datasets:
        raise RuntimeError("canonical authority contains no source datasets")
    return datasets


def run_all(path: Path, chunk_size: int, *, write_enabled: bool) -> dict[str, Any]:
    datasets = canonical_datasets(path)
    results: list[dict[str, Any]] = []
    total_rows = 0
    total_reader_metadata_rows = 0
    aggregate_actions = {"INSERT": 0, "UPDATE": 0, "UNCHANGED": 0, "EXPIRE": 0}

    for dataset in datasets:
        rows = dataset_sync.normalized_dataset_rows(path, dataset)
        result = dataset_sync.run_sync(
            rows,
            dataset,
            chunk_size,
            write_enabled=write_enabled,
        )
        results.append(result)
        total_rows += int(result.get("input_count", 0) or 0)
        total_reader_metadata_rows += int(result.get("reader_metadata_rows", 0) or 0)
        actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
        for action in aggregate_actions:
            aggregate_actions[action] += int(actions.get(action, 0) or 0)

    return {
        "run_type": "supabase_authority_all_datasets_sync" if write_enabled else "supabase_authority_all_datasets_dry_run",
        "dataset_count": len(datasets),
        "datasets": datasets,
        "input_count": total_rows,
        "reader_metadata_rows": total_reader_metadata_rows,
        "actions": aggregate_actions,
        "database_write_performed": write_enabled,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=int(os.environ.get("NYCIF_SUPABASE_SYNC_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)),
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    result = run_all(Path(args.input), args.chunk_size, write_enabled=args.write)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
