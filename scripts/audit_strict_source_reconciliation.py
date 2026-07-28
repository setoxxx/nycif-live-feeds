#!/usr/bin/env python3
"""Build a protected source-to-disposition reconciliation artifact.

The audit is read-only. It reconciles raw source occurrences by dataset,
source event ID, and event date; keeps generated reference additions separate;
and writes only protected /tmp evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import extract_rows, preserve_date, source_parts  # noqa: E402
from project_events_discovery_v02 import (  # noqa: E402
    SEASON_END_DATE,
    SEASON_START_DATE,
    event_overlaps_season,
    rejected_supplemental_keys,
)

RAW = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
STAGED = ROOT / "data" / "nycif_staged_live_events.json"
CALENDAR = ROOT / "data" / "nyc_citywide_events_calendar_snapshot.json"
PARKS = ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json"
SUPPLEMENTAL = ROOT / "data" / "supplemental_events_staging_feed.json"
SUPPLEMENTAL_QUEUE = ROOT / "data" / "supplemental_manual_approval_queue.json"
DISPOSITION = ROOT / "data" / "row_disposition_events.json"
PROJECTED_FEAST = ROOT / "data" / "staging" / "projected_feast_events_map_intake.json"
CURRENT_RECON = ROOT / "data" / "events_discovery_reconciliation_v02.json"
CURRENT_TAXONOMY = ROOT / "data" / "events_discovery_taxonomy_v02_audit.json"

INPUTS = (
    RAW,
    STAGED,
    CALENDAR,
    PARKS,
    SUPPLEMENTAL,
    SUPPLEMENTAL_QUEUE,
    DISPOSITION,
    PROJECTED_FEAST,
    CURRENT_RECON,
    CURRENT_TAXONOMY,
)

SourceKey = tuple[str, str]
OccurrenceKey = tuple[str, str, str]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return extract_rows(load_json(path))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_key(row: dict[str, Any]) -> SourceKey:
    dataset, source_event_id = source_parts(row)
    return str(dataset), str(source_event_id)


def occurrence_key(row: dict[str, Any]) -> OccurrenceKey:
    dataset, source_event_id = source_key(row)
    return dataset, source_event_id, preserve_date(row) or "undated"


def compact_row(row: dict[str, Any], disposition: str) -> dict[str, Any]:
    dataset, source_event_id, event_date = occurrence_key(row)
    return {
        "source_dataset": dataset,
        "source_event_id": source_event_id,
        "event_date": None if event_date == "undated" else event_date,
        "disposition": disposition,
    }


def is_rejected_disposition(row: dict[str, Any]) -> bool:
    disposition = str(row.get("disposition") or "").lower()
    reason = str(row.get("reason") or "").lower()
    return disposition in {"rejected", "drop", "invalid"} or "reject" in reason


def rejected_open_data_occurrences(
    rows: list[dict[str, Any]],
) -> tuple[set[OccurrenceKey], set[SourceKey]]:
    occurrence_keys: set[OccurrenceKey] = set()
    source_keys: set[SourceKey] = set()
    for row in rows:
        if not is_rejected_disposition(row):
            continue
        key = source_key(row)
        source_keys.add(key)
        day = preserve_date(row)
        if day:
            occurrence_keys.add((key[0], key[1], day))
    return occurrence_keys, source_keys


def classify_open_data_row(
    row: dict[str, Any],
    *,
    staged_occurrence_keys: set[OccurrenceKey],
    staged_source_keys: set[SourceKey],
    rejected_occurrence_keys: set[OccurrenceKey],
    rejected_source_keys: set[SourceKey],
    season_start: str = SEASON_START_DATE,
    season_end: str = SEASON_END_DATE,
) -> str:
    occurrence = occurrence_key(row)
    source = source_key(row)
    if occurrence in staged_occurrence_keys:
        return "represented_by_staged_occurrence"
    if occurrence in rejected_occurrence_keys or source in rejected_source_keys:
        return "rejected_with_documented_reason"
    if event_overlaps_season(row, season_start, season_end):
        if source in staged_source_keys:
            return "in_window_occurrence_hidden_by_source_id_match"
        return "accepted_via_current_unstaged_season_intake"
    if preserve_date(row):
        return "excluded_outside_audited_season_window"
    return "excluded_missing_or_unparseable_event_date"


def classify_calendar_parks_row(
    row: dict[str, Any],
    *,
    accepted_supplemental_occurrences: set[OccurrenceKey],
    all_supplemental_source_keys: set[SourceKey],
    rejected_supplemental_source_keys: set[SourceKey],
) -> str:
    occurrence = occurrence_key(row)
    source = source_key(row)
    if source in rejected_supplemental_source_keys:
        return "rejected_by_manual_supplemental_review"
    if occurrence in accepted_supplemental_occurrences:
        return "represented_by_supplemental_occurrence"
    if source in all_supplemental_source_keys:
        return "occurrence_hidden_by_supplemental_source_id_match"
    return "accepted_via_current_unlinked_raw_intake"


def ensure_protected_output(path: Path) -> Path:
    resolved = path.resolve()
    tmp_root = Path("/tmp").resolve()
    if resolved != tmp_root and tmp_root not in resolved.parents:
        raise ValueError(f"protected audit output must remain under /tmp: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def write_json(path: Path, payload: Any) -> None:
    protected = ensure_protected_output(path)
    protected.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def generated_at_of(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("generated_at_utc") or payload.get("generated_at")
    return str(value) if value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("/tmp/strict-source-reconciliation-report.json"),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("/tmp/strict-source-reconciliation-ledger.json"),
    )
    args = parser.parse_args()

    missing = [str(path.relative_to(ROOT)) for path in INPUTS if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required audit inputs: " + ", ".join(missing))

    raw_rows = load_rows(RAW)
    staged_rows = load_rows(STAGED)
    calendar_rows = load_rows(CALENDAR)
    parks_rows = load_rows(PARKS)
    supplemental_rows = load_rows(SUPPLEMENTAL)
    disposition_rows = load_rows(DISPOSITION)
    projected_rows = load_rows(PROJECTED_FEAST)

    staged_occurrences = {occurrence_key(row) for row in staged_rows}
    staged_sources = {source_key(row) for row in staged_rows}
    rejected_open_occurrences, rejected_open_sources = rejected_open_data_occurrences(
        disposition_rows
    )

    rejected_supplemental_sources = rejected_supplemental_keys()
    accepted_supplemental_rows = [
        row
        for row in supplemental_rows
        if source_key(row) not in rejected_supplemental_sources
    ]
    accepted_supplemental_occurrences = {
        occurrence_key(row) for row in accepted_supplemental_rows
    }
    all_supplemental_sources = {source_key(row) for row in supplemental_rows}

    open_ledger: list[dict[str, Any]] = []
    open_counts: Counter[str] = Counter()
    admitted_occurrences = set(staged_occurrences)
    for row in raw_rows:
        disposition = classify_open_data_row(
            row,
            staged_occurrence_keys=staged_occurrences,
            staged_source_keys=staged_sources,
            rejected_occurrence_keys=rejected_open_occurrences,
            rejected_source_keys=rejected_open_sources,
        )
        open_counts[disposition] += 1
        open_ledger.append(compact_row(row, disposition))
        if disposition == "accepted_via_current_unstaged_season_intake":
            admitted_occurrences.add(occurrence_key(row))

    calendar_parks_ledger: list[dict[str, Any]] = []
    calendar_parks_counts: Counter[str] = Counter()
    admitted_occurrences.update(accepted_supplemental_occurrences)
    for row in [*calendar_rows, *parks_rows]:
        disposition = classify_calendar_parks_row(
            row,
            accepted_supplemental_occurrences=accepted_supplemental_occurrences,
            all_supplemental_source_keys=all_supplemental_sources,
            rejected_supplemental_source_keys=rejected_supplemental_sources,
        )
        calendar_parks_counts[disposition] += 1
        calendar_parks_ledger.append(compact_row(row, disposition))
        if disposition == "accepted_via_current_unlinked_raw_intake":
            admitted_occurrences.add(occurrence_key(row))

    projected_counts: Counter[str] = Counter()
    projected_ledger: list[dict[str, Any]] = []
    for row in projected_rows:
        occurrence = occurrence_key(row)
        if occurrence in admitted_occurrences:
            disposition = "skipped_existing_occurrence"
        else:
            disposition = "accepted_generated_reference_addition"
            admitted_occurrences.add(occurrence)
        projected_counts[disposition] += 1
        projected_ledger.append(compact_row(row, disposition))

    current_recon = load_json(CURRENT_RECON)
    current_taxonomy = load_json(CURRENT_TAXONOMY)
    canonical_disposition_pass = bool(
        (current_recon.get("equations") or {}).get("accepted_equals_disposition_sum")
    )

    open_accounted = sum(open_counts.values())
    calendar_parks_accounted = sum(calendar_parks_counts.values())
    raw_total = len(raw_rows) + len(calendar_rows) + len(parks_rows)
    raw_accounted = open_accounted + calendar_parks_accounted
    strict_accounting_pass = (
        open_accounted == len(raw_rows)
        and calendar_parks_accounted == len(calendar_rows) + len(parks_rows)
        and raw_accounted == raw_total
    )
    hidden_open = open_counts.get("in_window_occurrence_hidden_by_source_id_match", 0)
    hidden_calendar_parks = calendar_parks_counts.get(
        "occurrence_hidden_by_supplemental_source_id_match", 0
    )
    pipeline_completeness_pass = hidden_open == 0 and hidden_calendar_parks == 0
    strict_reconciliation_pass = (
        strict_accounting_pass
        and canonical_disposition_pass
        and pipeline_completeness_pass
    )
    audit_integrity_pass = strict_accounting_pass and canonical_disposition_pass

    input_provenance = {}
    for path in INPUTS:
        payload = load_json(path)
        input_provenance[str(path.relative_to(ROOT))] = {
            "sha256": sha256_file(path),
            "generated_at_utc": generated_at_of(payload),
        }

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    audit_source_sha = os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA")
    report = {
        "artifact_type": "strict_source_reconciliation_audit",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": audit_source_sha,
        "audit_scope": {
            "season_start": SEASON_START_DATE,
            "season_end": SEASON_END_DATE,
            "raw_sources": [
                "raw_nyc_open_data_snapshot",
                "nyc_citywide_events_calendar_snapshot",
                "nyc_parks_bigapps_events_snapshot",
            ],
            "matching_granularity": "dataset + source_event_id + event_date",
            "generated_reference_inputs_separated_from_raw": True,
        },
        "source_rows": {
            "raw_nyc_open_data": len(raw_rows),
            "calendar": len(calendar_rows),
            "parks_bigapps": len(parks_rows),
            "raw_total": raw_total,
        },
        "stage_rows": {
            "staged_live_events": len(staged_rows),
            "staged_unique_occurrences": len(staged_occurrences),
            "supplemental_staging_total": len(supplemental_rows),
            "supplemental_staging_accepted": len(accepted_supplemental_rows),
            "supplemental_rejected_source_keys": len(rejected_supplemental_sources),
            "documented_open_data_rejected_occurrences": len(rejected_open_occurrences),
            "documented_open_data_rejected_source_keys": len(rejected_open_sources),
            "projected_feast_reference_rows": len(projected_rows),
        },
        "raw_dispositions": {
            "open_data": dict(sorted(open_counts.items())),
            "calendar_and_parks": dict(sorted(calendar_parks_counts.items())),
        },
        "generated_reference_dispositions": dict(sorted(projected_counts.items())),
        "blocking_dispositions": {
            "open_data_in_window_hidden_by_source_id": hidden_open,
            "calendar_parks_hidden_by_supplemental_source_id": hidden_calendar_parks,
        },
        "equations": {
            "open_data_raw_equals_explicit_dispositions": open_accounted == len(raw_rows),
            "calendar_parks_raw_equals_explicit_dispositions": (
                calendar_parks_accounted == len(calendar_rows) + len(parks_rows)
            ),
            "all_raw_rows_equal_explicit_dispositions": raw_accounted == raw_total,
            "raw_source_rows": raw_total,
            "raw_rows_accounted": raw_accounted,
            "current_canonical_accepted_equals_disposition_sum": canonical_disposition_pass,
            "current_accepted_canonical_records": current_recon.get(
                "accepted_canonical_records"
            ),
            "current_taxonomy_accepted_canonical_records": (
                (current_taxonomy.get("totals") or {}).get(
                    "accepted_canonical_records"
                )
            ),
        },
        "input_provenance": input_provenance,
        "strict_accounting_pass": strict_accounting_pass,
        "pipeline_completeness_pass": pipeline_completeness_pass,
        "strict_reconciliation_pass": strict_reconciliation_pass,
        "issue_132_pipeline_gate_pass": strict_reconciliation_pass,
        "qa_pass": audit_integrity_pass,
        "safety": {
            "location_cache_modified": False,
            "production_feed_modified": False,
            "promotion_allowed": False,
            "proposal_only": True,
            "public_map_modified": False,
            "wordpress_modified": False,
        },
        "notes": [
            "Every raw occurrence receives one explicit audit disposition; generated feast-reference additions are reported separately and are not netted against raw intake.",
            "A successful audit run confirms accounting integrity, not that the issue #132 pipeline-completeness gate passed.",
            "Any in-window occurrence hidden by source-ID-only matching remains a blocker requiring a separately reviewed pipeline correction.",
            "This protected audit reads the committed snapshot and writes only to /tmp.",
        ],
    }
    ledger = {
        "artifact_type": "strict_source_reconciliation_ledger",
        "generated_at_utc": generated_at,
        "repository_sha": audit_source_sha,
        "open_data": open_ledger,
        "calendar_and_parks": calendar_parks_ledger,
        "generated_reference_additions": projected_ledger,
        "safety": report["safety"],
    }

    write_json(args.report, report)
    write_json(args.ledger, ledger)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if audit_integrity_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
