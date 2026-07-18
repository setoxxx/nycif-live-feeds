#!/usr/bin/env python3
"""Merge human-approved supplemental export into discovery approved layer."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

try:
    from scripts.coverage_gap_utils import DATA_DIR, load_json_file, repo_relative, save_json_file, utc_now_iso
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import DATA_DIR, load_json_file, repo_relative, save_json_file, utc_now_iso

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
STATUS_PATH = ROOT / "status" / "nycif-project-status.json"
MERGE_REPORT_PATH = DATA_DIR / "reports" / "supplemental_discovery_merge_report.json"


def norm_dataset(value: Any) -> str:
    return str(value or "").strip().lower()


def norm_id(value: Any) -> str:
    return str(value or "").strip()


def norm_date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def identity_key(dataset: Any, source_event_id: Any, day: Any) -> tuple[str, str, str]:
    return (norm_dataset(dataset), norm_id(source_event_id), norm_date(day))


def is_merge_authorized() -> bool:
    env = str(os.environ.get("NYCIF_SUPPLEMENTAL_DISCOVERY_MERGE_AUTHORIZED") or "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    payload = load_json_file(STATUS_PATH, {})
    safety = payload.get("safety") if isinstance(payload, dict) else {}
    if isinstance(safety, dict) and safety.get("supplemental_public_map_merge_authorized") is True:
        return True
    return False


def approved_identity_set(approved: list[dict]) -> set[tuple[str, str, str]]:
    identities: set[tuple[str, str, str]] = set()
    for event in approved:
        if not isinstance(event, dict):
            continue
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        day = norm_date(nycif.get("event_date") or event.get("start_date_time"))
        identities.add(identity_key(source.get("dataset"), source.get("source_event_id"), day))
    return identities


def sort_approved_events(events: list[dict]) -> list[dict]:
    def key(event: dict) -> tuple[str, str, str]:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        return (
            norm_date(nycif.get("event_date") or event.get("start_date_time")) or "9999-99-99",
            str(event.get("title") or "").lower(),
            str(event.get("id") or ""),
        )

    return sorted(events, key=key)


def fold_approved_supplemental_export(
    approved: list[dict],
    *,
    build_base_event,
    current_major_keys: set[tuple[str, str]] | None = None,
    authorized: bool | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Append net-new approved supplemental export rows to the approved discovery list."""
    authorized = is_merge_authorized() if authorized is None else bool(authorized)
    if not authorized:
        return approved, {
            "authorized": False,
            "merged": 0,
            "skipped_duplicate": 0,
            "skipped_not_approved": 0,
            "skipped_invalid": 0,
        }

    export = load_json_file(EXPORT_PATH, {})
    rows = export.get("events") if isinstance(export, dict) else []
    if not isinstance(rows, list):
        rows = []

    identities = approved_identity_set(approved)
    seen_ids = {e.get("id") for e in approved if isinstance(e, dict)}
    merged = 0
    skipped_duplicate = 0
    skipped_not_approved = 0
    skipped_invalid = 0
    merged_samples: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            skipped_invalid += 1
            continue
        if str(row.get("manual_review_status") or "").lower() != "approved":
            skipped_not_approved += 1
            continue
        key = identity_key(row.get("source_dataset"), row.get("source_event_id"), row.get("date"))
        if key in identities:
            skipped_duplicate += 1
            continue
        event = build_base_event(
            row,
            data_layer="approved_staged",
            index=200_000 + index,
            production_feed=True,
            current_major_keys=current_major_keys,
        )
        if event is None:
            skipped_invalid += 1
            continue
        eid = event.get("id")
        if eid in seen_ids:
            skipped_duplicate += 1
            continue

        nycif = dict(event.get("nycif") or {})
        nycif["public_supplemental"] = True
        nycif["supplemental_from"] = "supplemental_approved_export_feed"
        nycif["supplemental_merge_authorized"] = True
        nycif["manual_review_status"] = row.get("manual_review_status")
        nycif["manual_reviewer"] = row.get("manual_reviewer")
        nycif["manual_reviewed_at_utc"] = row.get("manual_reviewed_at_utc")
        nycif["approval_decision_reason"] = row.get("approval_decision_reason")
        nycif["geocoder_source"] = row.get("geocoder_source")
        nycif["geocoder_confidence"] = row.get("geocoder_confidence")
        nycif["confidence_reason"] = row.get("confidence_reason")
        nycif["promotion_allowed"] = False
        event["nycif"] = nycif

        approved.append(event)
        seen_ids.add(eid)
        identities.add(key)
        merged += 1
        if len(merged_samples) < 25:
            merged_samples.append(
                {
                    "id": eid,
                    "title": event.get("title"),
                    "date": nycif.get("event_date"),
                    "source_dataset": key[0],
                    "source_event_id": key[1],
                }
            )

    approved[:] = sort_approved_events(approved)
    stats = {
        "authorized": True,
        "export_event_count": len(rows),
        "merged": merged,
        "skipped_duplicate": skipped_duplicate,
        "skipped_not_approved": skipped_not_approved,
        "skipped_invalid": skipped_invalid,
        "approved_total_after_merge": len(approved),
        "sample_merged": merged_samples,
    }
    return approved, stats


def write_merge_report(
    stats: dict[str, Any],
    *,
    baseline_total: int,
    qa_pass: bool,
    errors: list[str],
) -> dict[str, Any]:
    report = {
        "artifact_type": "supplemental_discovery_merge_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_discovery_merge",
        "qa_pass": qa_pass,
        "merge_authorized": bool(stats.get("authorized")),
        "errors": errors,
        "baseline": {
            "approved_discovery_total_before": baseline_total,
            "approved_discovery_total_after": stats.get("approved_total_after_merge", baseline_total),
            "net_new_merged": stats.get("merged", 0),
        },
        "merge_stats": stats,
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
            "production_feed": True,
            "schema_v1_discovery_modified": bool(stats.get("merged", 0) > 0),
            "supplemental_export_path": repo_relative(EXPORT_PATH),
        },
    }
    save_json_file(MERGE_REPORT_PATH, report)
    return report
