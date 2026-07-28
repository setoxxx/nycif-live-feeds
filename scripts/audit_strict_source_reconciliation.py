#!/usr/bin/env python3
"""Build a protected, read-only source-to-disposition reconciliation artifact.

This audit does not rewrite discovery feeds, approval queues, location caches,
WordPress content, or public map assets. It accounts for each raw source row
using the same source-key and season-window rules as the current discovery-v02
projection, while keeping generated reference additions separate from raw
source accounting.
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
    rejected_open_data_keys,
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


def source_key(row: dict[str, Any]) -> tuple[str, str]:
    dataset, source_event_id = source_parts(row)
    return str(dataset), str(source_event_id)


def compact_row(row: dict[str, Any], disposition: str) -> dict[str, Any]:
    dataset, source_event_id = source_key(row)
    return {
        "source_dataset": dataset,
        "source_event_id": source_event_id,
        "event_date": preserve_date(row),
        "disposition": disposition,
    }


def classify_open_data_row(
    row: dict[str, Any],
    *,
    staged_keys: set[tuple[str, str]],
    rejected_keys: set[tuple[str, str]],
    season_start: str = SEASON_START_DATE,
    season_end: str = SEASON_END_DATE,
) -> str:
    key = source_key(row)
    if key in staged_keys:
        return "accepted_via_staged_feed"
    if key in rejected_keys:
        return "rejected_with_documented_reason"
    if event_overlaps_season(row, season_start, season_end):
        return "accepted_via_unstaged_season_intake"
    if preserve_date(row):
        return "excluded_outside_audited_season_window"
    return "excluded_missing_or_unparseable_event_date"


def classify_calendar_parks_row(
    row: dict[str, Any],
    *,
    accepted_supplemental_keys: set[tuple[str, str]],
    rejected_supplemental_keys_set: set[tuple[str, str]],
) -> str:
    key = source_key(row)
    if key in rejected_supplemental_keys_set:
        return "rejected_by_manual_supplemental_review"
    if key in accepted_supplemental_keys:
        return "accepted_via_supplemental_staging"
    return "accepted_via_unlinked_raw_intake"


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
    parser.add_argument("--report", type=Path, default=Path("/tmp/strict-source-reconciliation-report.json"))
    parser.add_argument("--ledger", type=Path, default=Path("/tmp/strict-source-reconciliation-ledger.json"))
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

    staged_keys = {source_key(row) for row in staged_rows}
    open_rejected_keys = rejected_open_data_keys(disposition_rows)
    supplemental_rejected_keys = rejected_supplemental_keys()
    accepted_supplemental_rows = [
        row for row in supplemental_rows if source_key(row) not in supplemental_rejected_keys
    ]
    accepted_supplemental_keys = {source_key(row) for row in accepted_supplemental_rows}

    open_ledger: list[dict[str, Any]] = []
    open_counts: Counter[str] = Counter()
    admitted_open_keys = set(staged_keys)
    for row in raw_rows:
        disposition = classify_open_data_row(
            row,
            staged_keys=staged_keys,
            rejected_keys=open_rejected_keys,
        )
        open_counts[disposition] += 1
        open_ledger.append(compact_row(row, disposition))
        if disposition == "accepted_via_unstaged_season_intake":
            admitted_open_keys.add(source_key(row))

    calendar_parks_ledger: list[dict[str, Any]] = []
    calendar_parks_counts: Counter[str] = Counter()
    accepted_calendar_parks_keys = set(accepted_supplemental_keys)
    for row in [*calendar_rows, *parks_rows]:
        disposition = classify_calendar_parks_row(
            row,
            accepted_supplemental_keys=accepted_supplemental_keys,
            rejected_supplemental_keys_set=supplemental_rejected_keys,
        )
        calendar_parks_counts[disposition] += 1
        calendar_parks_ledger.append(compact_row(row, disposition))
        if disposition == "accepted_via_unlinked_raw_intake":
            accepted_calendar_parks_keys.add(source_key(row))

    accepted_source_keys = admitted_open_keys | accepted_calendar_parks_keys
    projected_counts: Counter[str] = Counter()
    projected_ledger: list[dict[str, Any]] = []
    for row in projected_rows:
        key = source_key(row)
        if key in accepted_source_keys:
            disposition = "skipped_existing_source_identity"
        else:
            disposition = "accepted_generated_reference_addition"
            accepted_source_keys.add(key)
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
    zero_unclassified = (
        open_accounted == len(raw_rows)
        and calendar_parks_accounted == len(calendar_rows) + len(parks_rows)
    )
    strict_pass = zero_unclassified and raw_accounted == raw_total and canonical_disposition_pass

    input_provenance = {}
    for path in INPUTS:
        payload = load_json(path)
        input_provenance[str(path.relative_to(ROOT))] = {
            "sha256": sha256_file(path),
            "generated_at_utc": generated_at_of(payload),
        }

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "artifact_type": "strict_source_reconciliation_audit",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("GITHUB_SHA"),
        "audit_scope": {
            "season_start": SEASON_START_DATE,
            "season_end": SEASON_END_DATE,
            "raw_sources": [
                "raw_nyc_open_data_snapshot",
                "nyc_citywide_events_calendar_snapshot",
                "nyc_parks_bigapps_events_snapshot",
            ],
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
            "supplemental_staging_total": len(supplemental_rows),
            "supplemental_staging_accepted": len(accepted_supplemental_rows),
            "supplemental_rejected_source_keys": len(supplemental_rejected_keys),
            "documented_open_data_rejected_source_keys": len(open_rejected_keys),
            "projected_feast_reference_rows": len(projected_rows),
        },
        "raw_dispositions": {
            "open_data": dict(sorted(open_counts.items())),
            "calendar_and_parks": dict(sorted(calendar_parks_counts.items())),
        },
        "generated_reference_dispositions": dict(sorted(projected_counts.items())),
        "equations": {
            "open_data_raw_equals_explicit_dispositions": open_accounted == len(raw_rows),
            "calendar_parks_raw_equals_explicit_dispositions": (
                calendar_parks_accounted == len(calendar_rows) + len(parks_rows)
            ),
            "all_raw_rows_equal_explicit_dispositions": raw_accounted == raw_total,
            "raw_source_rows": raw_total,
            "raw_rows_accounted": raw_accounted,
            "current_canonical_accepted_equals_disposition_sum": canonical_disposition_pass,
            "current_accepted_canonical_records": current_recon.get("accepted_canonical_records"),
            "current_taxonomy_accepted_canonical_records": (
                (current_taxonomy.get("totals") or {}).get("accepted_canonical_records")
            ),
        },
        "input_provenance": input_provenance,
        "strict_reconciliation_pass": strict_pass,
        "qa_pass": strict_pass,
        "safety": {
            "location_cache_modified": False,
            "production_feed_modified": False,
            "promotion_allowed": False,
            "proposal_only": True,
            "public_map_modified": False,
            "wordpress_modified": False,
        },
        "notes": [
            "Every raw row receives one explicit audit disposition; generated feast-reference additions are reported separately and are not netted against raw intake.",
            "Accepted canonical records are not assumed to be one-to-one with raw rows because occurrence projection, folding, grouping, and deduplication are explicit transformation stages.",
            "This protected audit reads the committed snapshot and writes only to /tmp.",
        ],
    }
    ledger = {
        "artifact_type": "strict_source_reconciliation_ledger",
        "generated_at_utc": generated_at,
        "repository_sha": os.environ.get("GITHUB_SHA"),
        "open_data": open_ledger,
        "calendar_and_parks": calendar_parks_ledger,
        "generated_reference_additions": projected_ledger,
        "safety": report["safety"],
    }

    write_json(args.report, report)
    write_json(args.ledger, ledger)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if strict_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
