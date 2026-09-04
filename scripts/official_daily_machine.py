#!/usr/bin/env python3
"""Daily factory machine: account for every official row, diff new vs gone, pin 100%.

This is the operator loop Howard has been doing by hand. Each Discovery /
catch-up run must:

1. Classify every snapshot row as accepted or rejected with a reason (no silent drops).
2. Diff today's occurrence IDs against yesterday's index (added / still present /
   gone from the city source).
3. Certify every pin-eligible official coordinate (Parks evidence, calendar
   snapshot coords, every public TVPP row). Calendar and feast may also pin
   from the official street/facility resolver; leftover borough-only rows
   stay unpinned.
4. Never expire, never edit location_cache.json, never publish to the public map.

Gone-from-city IDs are reported only. They are not deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import official_event_contract as contract
from scripts import sync_supabase_official_source_catchup as catchup

REPORT_SCHEMA = "official_daily_machine.v1"
INDEX_SCHEMA = "official_occurrence_index.v1"
REPORT_FILENAME = "official_daily_machine_report.json"
INDEX_FILENAME = "official_occurrence_index.json"
SAMPLE_LIMIT = 25


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_previous_index(path: Path | None = None) -> dict[str, Any]:
    target = path or (catchup.REPORTS_DIR / INDEX_FILENAME)
    if not target.exists():
        return {"schema": INDEX_SCHEMA, "datasets": {}}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"schema": INDEX_SCHEMA, "datasets": {}}
    return payload


def snapshot_items(dataset: str) -> list[Any]:
    path = {
        contract.DATASET_PARKS: catchup.PARKS_PATH,
        contract.DATASET_TVPP: catchup.TVPP_PATH,
        contract.DATASET_CALENDAR: catchup.CALENDAR_PATH,
        contract.DATASET_FEAST: catchup.FEAST_PATH,
    }[dataset]
    payload = catchup._load_json(path)
    if dataset in {contract.DATASET_PARKS, contract.DATASET_FEAST}:
        rows = payload.get("events", []) if isinstance(payload, dict) else payload
    elif dataset == contract.DATASET_TVPP:
        rows = payload if isinstance(payload, list) else payload.get("events", [])
    else:
        rows = payload if isinstance(payload, list) else payload.get("events", [])
    if not isinstance(rows, list):
        return []
    return rows


def snapshot_source_event_id(dataset: str, row: dict[str, Any]) -> str:
    if dataset == contract.DATASET_TVPP:
        return str(row.get("source_event_id") or row.get("event_id") or "").strip()
    if dataset == contract.DATASET_FEAST:
        return str(row.get("source_event_id") or row.get("projected_feast_key") or "").strip()
    return str(row.get("source_event_id") or row.get("guid") or row.get("id") or "").strip()


def pin_eligible_from_snapshot(dataset: str, row: dict[str, Any]) -> bool:
    if dataset in contract.PIN_NEVER:
        return False
    if dataset == contract.DATASET_TVPP:
        return True
    if dataset == contract.DATASET_PARKS:
        return catchup.official_parks_pin(row)[2] is True
    if dataset == contract.DATASET_CALENDAR:
        return contract.apply_pin_policy(
            dataset,
            row.get("lat") if row.get("lat") is not None else row.get("latitude"),
            row.get("lng") if row.get("lng") is not None else row.get("longitude"),
        )[2] is True
    return False


def _sample(rows: list[dict[str, Any]], limit: int = SAMPLE_LIMIT) -> list[dict[str, Any]]:
    return rows[:limit]


def _ids_for_dataset(index: dict[str, Any], dataset: str) -> set[str]:
    block = (index.get("datasets") or {}).get(dataset) or {}
    return {str(item) for item in (block.get("occurrence_ids") or []) if str(item)}


def build_machine_report(
    rows_by_dataset: dict[str, list[dict[str, Any]]],
    rejections_by_dataset: dict[str, list[dict[str, Any]]],
    previous_index: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    previous = previous_index if isinstance(previous_index, dict) else {"datasets": {}}
    baseline = not any(_ids_for_dataset(previous, name) for name in rows_by_dataset)
    failures: list[str] = []
    datasets: dict[str, Any] = {}
    new_index_datasets: dict[str, Any] = {}
    pin_misses: list[dict[str, Any]] = []
    invented_pins: list[dict[str, Any]] = []
    unaccounted: list[dict[str, Any]] = []

    for dataset, rows in rows_by_dataset.items():
        rejections = list(rejections_by_dataset.get(dataset) or [])
        items = snapshot_items(dataset)
        snapshot_rows = len(items)
        accepted = len(rows)
        rejected = len(rejections)
        accounted = accepted + rejected
        if accounted != snapshot_rows:
            failures.append(f"silent_drop:{dataset}")
            unaccounted.append(
                {
                    "source_dataset": dataset,
                    "snapshot_rows": snapshot_rows,
                    "accepted": accepted,
                    "rejected": rejected,
                    "unaccounted": snapshot_rows - accounted,
                }
            )

        eligible = 0
        rejected_ids = {
            str(item.get("source_event_id") or "").strip()
            for item in rejections
            if str(item.get("source_event_id") or "").strip()
        }
        for item in items:
            if not isinstance(item, dict) or not pin_eligible_from_snapshot(dataset, item):
                continue
            source_event_id = snapshot_source_event_id(dataset, item)
            if source_event_id and source_event_id in rejected_ids:
                continue
            eligible += 1
        if dataset == contract.DATASET_TVPP:
            eligible = accepted
        certified = sum(1 for row in rows if row.get("map_ready") is True)
        if dataset in contract.PIN_NEVER and certified:
            failures.append(f"list_only_dataset_pinned:{dataset}")
            invented_pins.append(
                {
                    "source_dataset": dataset,
                    "pin_eligible": 0,
                    "certified_pins": certified,
                    "extra": certified,
                    "reason": "dataset_must_stay_list_only",
                }
            )
        if certified < eligible:
            failures.append(f"pin_coverage_short:{dataset}")
            pin_misses.append(
                {
                    "source_dataset": dataset,
                    "pin_eligible": eligible,
                    "certified_pins": certified,
                    "missed": eligible - certified,
                }
            )
        if certified > eligible and dataset in {contract.DATASET_CALENDAR, contract.DATASET_FEAST}:
            # Official resolver fills are allowed on top of snapshot-coord eligibility.
            eligible = certified
        if certified > eligible:
            failures.append(f"invented_pins:{dataset}")
            invented_pins.append(
                {
                    "source_dataset": dataset,
                    "pin_eligible": eligible,
                    "certified_pins": certified,
                    "extra": certified - eligible,
                }
            )

        current_ids = [str(row.get("occurrence_id") or "") for row in rows if row.get("occurrence_id")]
        current_set = set(current_ids)
        previous_set = _ids_for_dataset(previous, dataset)
        added_ids = sorted(current_set - previous_set)
        removed_ids = sorted(previous_set - current_set)
        still_present = len(current_set & previous_set)
        list_only_reason = (
            "dataset_list_only_policy"
            if dataset in contract.PIN_NEVER
            else "no_official_in_bounds_coordinate"
        )
        list_only_no_pin = [
            {
                "occurrence_id": row.get("occurrence_id"),
                "title": row.get("title"),
                "display_location": row.get("display_location"),
                "reason": list_only_reason,
            }
            for row in rows
            if row.get("map_ready") is not True
        ]

        datasets[dataset] = {
            "snapshot_rows": snapshot_rows,
            "accepted": accepted,
            "rejected": rejected,
            "accounted": accounted,
            "unaccounted": snapshot_rows - accounted,
            "pin_eligible": eligible,
            "certified_pins": certified,
            "list_only": accepted - certified,
            "pin_coverage_pass": certified == eligible and (dataset not in contract.PIN_NEVER or certified == 0),
            "added": len(added_ids) if not baseline else accepted,
            "still_present": still_present if not baseline else 0,
            "removed_from_city": len(removed_ids) if not baseline else 0,
            "added_occurrence_id_samples": _sample(added_ids),
            "removed_from_city_occurrence_id_samples": _sample(removed_ids),
            "list_only_samples": _sample(list_only_no_pin),
            "rejection_samples": _sample(rejections),
        }
        new_index_datasets[dataset] = {
            "rows": accepted,
            "certified_pins": certified,
            "occurrence_ids": sorted(current_set),
        }

    qa_pass = not failures
    report = {
        "schema": REPORT_SCHEMA,
        "generated_at_utc": _now_iso(),
        "today_nyc": catchup.today_nyc(),
        "qa_pass": qa_pass,
        "failures": failures,
        "baseline_established": baseline,
        "expire_enabled": False,
        "promotion_allowed": False,
        "manual_review_status": "pending",
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "public_map_modified": False,
        "pin_rule": {
            "certified_pin_means": "official in-bounds city coordinates plus dataset pin policy",
            "tvpp": "every public tvpp-9vvx row must be a certified pin",
            "feast": "always list-only",
            "parks": "pin only with official Parks evidence",
            "calendar": "pin only when the snapshot already has official in-bounds coords",
            "removed_from_city": "reported, never expired",
        },
        "datasets": datasets,
        "pin_misses": pin_misses,
        "invented_pins": invented_pins,
        "unaccounted": unaccounted,
    }
    new_index = {
        "schema": INDEX_SCHEMA,
        "generated_at_utc": report["generated_at_utc"],
        "today_nyc": report["today_nyc"],
        "qa_pass": qa_pass,
        "datasets": new_index_datasets,
    }
    return report, new_index


def summary_for_catchup(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": report.get("schema"),
        "qa_pass": report.get("qa_pass"),
        "failures": report.get("failures") or [],
        "baseline_established": report.get("baseline_established"),
        "today_nyc": report.get("today_nyc"),
        "datasets": {
            name: {
                key: block.get(key)
                for key in (
                    "snapshot_rows",
                    "accepted",
                    "rejected",
                    "unaccounted",
                    "pin_eligible",
                    "certified_pins",
                    "list_only",
                    "pin_coverage_pass",
                    "added",
                    "still_present",
                    "removed_from_city",
                )
            }
            for name, block in (report.get("datasets") or {}).items()
        },
    }


def build_from_snapshots() -> tuple[dict[str, Any], dict[str, Any]]:
    rows_by_dataset: dict[str, list[dict[str, Any]]] = {}
    rejections_by_dataset: dict[str, list[dict[str, Any]]] = {}
    for dataset in contract.OFFICIAL_DATASETS:
        rows, rejections = catchup.normalize_dataset(dataset)
        rows_by_dataset[dataset] = rows
        rejections_by_dataset[dataset] = rejections
    return build_machine_report(rows_by_dataset, rejections_by_dataset, load_previous_index())


def persist(
    report: dict[str, Any],
    index: dict[str, Any],
    reports_dir: Path | None = None,
) -> tuple[Path, Path]:
    folder = reports_dir or catchup.REPORTS_DIR
    report_path = _write_json(folder / REPORT_FILENAME, report)
    index_path = _write_json(folder / INDEX_FILENAME, index)
    return report_path, index_path


def build_and_persist(
    rows_by_dataset: dict[str, list[dict[str, Any]]] | None = None,
    rejections_by_dataset: dict[str, list[dict[str, Any]]] | None = None,
    previous_index: dict[str, Any] | None = None,
    reports_dir: Path | None = None,
) -> dict[str, Any]:
    if rows_by_dataset is None:
        report, index = build_from_snapshots()
    else:
        report, index = build_machine_report(
            rows_by_dataset,
            rejections_by_dataset or {},
            previous_index if previous_index is not None else load_previous_index(),
        )
    persist(report, index, reports_dir=reports_dir)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-fail",
        action="store_true",
        help="Write the report even when qa_pass is false (Discovery records; catch-up still fails closed).",
    )
    args = parser.parse_args()
    report = build_and_persist()
    printable = {
        "qa_pass": report.get("qa_pass"),
        "failures": report.get("failures"),
        "baseline_established": report.get("baseline_established"),
        "today_nyc": report.get("today_nyc"),
        "datasets": {
            name: {
                key: block.get(key)
                for key in (
                    "snapshot_rows",
                    "accepted",
                    "rejected",
                    "unaccounted",
                    "pin_eligible",
                    "certified_pins",
                    "added",
                    "still_present",
                    "removed_from_city",
                    "pin_coverage_pass",
                )
            }
            for name, block in (report.get("datasets") or {}).items()
        },
    }
    print(json.dumps(printable, indent=2))
    if report.get("qa_pass") is True:
        return 0
    return 0 if args.allow_fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
