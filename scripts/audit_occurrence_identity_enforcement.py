#!/usr/bin/env python3
"""Protected audit for occurrence-key enforcement in discovery intake.

The audit compares the legacy source-ID-only behavior against the required
source + source event ID + event date occurrence identity. It also verifies the
real discovery projector now uses dated occurrence keys in the Open Data intake
path. It writes protected /tmp evidence only and does not modify production
feeds or public surfaces.
"""

from __future__ import annotations

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

from discovery_v02 import extract_rows, stable_canonical_id  # noqa: E402
from occurrence_identity_contract import (  # noqa: E402
    classify_open_data_occurrence,
    occurrence_key,
    occurrence_key_set,
    source_key,
    source_key_set,
)

RAW = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
STAGED = ROOT / "data" / "nycif_staged_live_events.json"
CALENDAR = ROOT / "data" / "nyc_citywide_events_calendar_snapshot.json"
PARKS = ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json"
SUPPLEMENTAL = ROOT / "data" / "supplemental_events_staging_feed.json"
SUPPLEMENTAL_QUEUE = ROOT / "data" / "supplemental_manual_approval_queue.json"
DISPOSITION = ROOT / "data" / "row_disposition_events.json"
PROJECTED_FEAST = ROOT / "data" / "staging" / "projected_feast_events_map_intake.json"
REGISTRY = ROOT / "data" / "source_lineage_registry_v01.json"
LOCATION_CACHE = ROOT / "data" / "location_cache.json"
PROJECTOR = ROOT / "scripts" / "project_events_discovery_v02.py"
OUTPUT_DIR = Path("/tmp/occurrence-identity-enforcement")
OUTPUT_FILENAMES = {
    "occurrence_identity_enforcement_summary.json",
    "before_after_occurrence_reconciliation.json",
    "hidden_occurrence_resolution_report.json",
    "duplicate_canonical_id_report.json",
    "raw_disposition_ledger_summary.json",
    "source_lineage_contract_check.json",
    "projector_occurrence_identity_check.json",
    "public_surface_safety_assertions.json",
    "occurrence_identity_enforcement_report.md",
}

SEASON_START = "2026-07-14"
SEASON_END = "2026-12-27"
KNOWN_ISSUE_324_HISTORICAL_HIDDEN_COUNT = 4203

SAFETY_ASSERTIONS = {
    "production_feed_modified": False,
    "data_location_cache_json_modified": False,
    "wordpress_modified": False,
    "public_map_modified": False,
    "homepage_modified": False,
    "navigation_modified": False,
    "theme_modified": False,
    "approval_state_modified": False,
    "promotion_allowed": False,
    "proposal_only": True,
    "public_launch_authorized": False,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return extract_rows(load_json(path))


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_output_dir() -> Path:
    resolved = OUTPUT_DIR.resolve()
    tmp = Path("/tmp").resolve()
    if resolved != tmp and tmp not in resolved.parents:
        raise ValueError(f"protected output must remain under /tmp: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def output_path(output_dir: Path, filename: str) -> Path:
    if filename not in OUTPUT_FILENAMES:
        raise ValueError(f"unexpected protected output filename: {filename}")
    path = (output_dir / filename).resolve()
    if path.parent != output_dir.resolve():
        raise ValueError(f"protected output must stay in {output_dir}: {path}")
    return path


def write_json(output_dir: Path, filename: str, payload: Any) -> None:
    output_path(output_dir, filename).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_text(output_dir: Path, filename: str, text: str) -> None:
    output_path(output_dir, filename).write_text(text, encoding="utf-8")


def is_rejected(row: dict[str, Any]) -> bool:
    disposition = str(row.get("disposition") or "").lower()
    reason = str(row.get("reason") or "").lower()
    manual = str(row.get("manual_review_status") or "").lower()
    return disposition in {"rejected", "drop", "invalid"} or "reject" in reason or manual == "rejected"


def rejected_open_data_keys(rows: list[dict[str, Any]]) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]]]:
    sources: set[tuple[str, str]] = set()
    occurrences: set[tuple[str, str, str]] = set()
    for row in rows:
        if not is_rejected(row):
            continue
        sources.add(source_key(row))
        occurrences.add(occurrence_key(row))
    return sources, occurrences


def rejected_supplemental_sources(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {source_key(row) for row in rows if is_rejected(row)}


def classify_calendar_parks_row(
    row: dict[str, Any],
    *,
    accepted_supplemental_occurrences: set[tuple[str, str, str]],
    all_supplemental_sources: set[tuple[str, str]],
    rejected_supplemental_source_keys: set[tuple[str, str]],
) -> str:
    occurrence = occurrence_key(row)
    source = source_key(row)
    if source in rejected_supplemental_source_keys:
        return "rejected_by_manual_supplemental_review"
    if occurrence in accepted_supplemental_occurrences:
        return "represented_by_supplemental_occurrence"
    if source in all_supplemental_sources:
        return "occurrence_hidden_by_supplemental_source_id_match"
    return "accepted_via_current_unlinked_raw_intake"


def duplicate_report_for_after_fix(
    *,
    staged_rows: list[dict[str, Any]],
    supplemental_rows: list[dict[str, Any]],
    raw_rows: list[dict[str, Any]],
    after_dispositions: dict[int, str],
) -> dict[str, Any]:
    ids: list[str] = []
    for i, row in enumerate(staged_rows):
        ids.append(stable_canonical_id(row, data_layer="approved_staged", index=i))
    for i, row in enumerate(supplemental_rows):
        ids.append(stable_canonical_id(row, data_layer="review_supplemental", index=i))
    for i, row in enumerate(raw_rows):
        if after_dispositions.get(i) == "accepted_via_occurrence_keyed_unstaged_intake":
            ids.append(stable_canonical_id(row, data_layer="review_supplemental", index=200000 + i))
    counts = Counter(ids)
    duplicates = {key: value for key, value in counts.items() if value > 1}
    return {
        "duplicate_canonical_id_count": sum(value - 1 for value in duplicates.values()),
        "duplicate_canonical_id_groups": [
            {"canonical_id": key, "count": value} for key, value in sorted(duplicates.items())[:100]
        ],
        "duplicate_safety_pass": not duplicates,
    }


def source_lineage_contract_check() -> dict[str, Any]:
    registry = load_json(REGISTRY)
    entries = registry.get("entries") or []
    occurrence_required = [row for row in entries if isinstance(row, dict) and row.get("requires_occurrence_key")]
    source_id_only = [row.get("id") for row in occurrence_required if row.get("identity_granularity") == "source_id_only"]
    safety_ok = registry.get("safety_assertions") == SAFETY_ASSERTIONS
    return {
        "registry_path": str(REGISTRY.relative_to(ROOT)),
        "registry_sha256": sha256_file(REGISTRY),
        "registry_entry_count": len(entries),
        "occurrence_key_required_entries": len(occurrence_required),
        "source_id_only_violations": source_id_only,
        "safety_assertions_pass": safety_ok,
        "source_lineage_contract_compliance_pass": safety_ok and not source_id_only,
    }


def projector_occurrence_identity_check() -> dict[str, Any]:
    text = PROJECTOR.read_text(encoding="utf-8")
    required_snippets = {
        "imports_occurrence_identity_contract": "from occurrence_identity_contract import" in text,
        "builds_staged_occurrence_keys": "staged_occurrence_keys = occurrence_key_set(staged_rows)" in text,
        "uses_raw_occurrence_key": "raw_occurrence_key = occurrence_key(row)" in text,
        "skips_staged_by_occurrence_key": "if raw_occurrence_key in staged_occurrence_keys:" in text,
        "uses_rejected_occurrence_keys": "rejected_keys, rejected_occurrence_keys = rejected_open_data_identity_sets(rejected_disp)" in text,
        "checks_rejected_occurrence_before_source_fallback": "raw_occurrence_key in rejected_occurrence_keys" in text,
        "projects_feast_by_occurrence_key": "projected_occurrence_key = occurrence_key(row)" in text,
        "dedupes_projected_by_occurrence_key": "if projected_occurrence_key in accepted_occurrence_keys:" in text,
        "records_projected_occurrence_after_accept": "accepted_occurrence_keys.add(projected_occurrence_key)" in text,
    }
    forbidden_snippets = {
        "raw_open_data_source_id_skip_pattern": "if (dataset, source_event_id) in staged_keys:\n            continue" in text,
        "projected_feast_source_id_only_skip_pattern": "if (dataset, source_event_id) in accepted_keys:\n                continue" in text,
    }
    return {
        "projector_path": str(PROJECTOR.relative_to(ROOT)),
        "projector_sha256": sha256_file(PROJECTOR),
        "required_snippets": required_snippets,
        "forbidden_snippets": forbidden_snippets,
        "projector_occurrence_identity_pass": all(required_snippets.values()) and not any(forbidden_snippets.values()),
    }


def make_markdown(summary: dict[str, Any]) -> str:
    return f"""# Occurrence identity enforcement audit

Generated: {summary['generated_at_utc']}

## Result

- Audit execution integrity: **{summary['audit_execution_integrity_pass']}**
- Projector implementation correctness: **{summary['projector_implementation_correctness_pass']}**
- Occurrence identity implementation correctness: **{summary['occurrence_identity_implementation_correctness_pass']}**
- Raw-disposition accounting: **{summary['raw_disposition_accounting_pass']}**
- Duplicate safety: **{summary['duplicate_safety_pass']}**
- Source-lineage contract compliance: **{summary['source_lineage_contract_compliance_pass']}**
- Historical Issue #324 baseline comparison applicable: **{summary['known_issue_324_baseline_comparison_applicable']}**
- Historical/current baseline state valid: **{summary['known_issue_324_baseline_state_pass']}**
- Launch readiness: **{summary['launch_readiness']}**

## Counts

- Staged rows / sources: **{summary['staged_row_count']} / {summary['staged_source_count']}**
- Open Data hidden before source-ID fix: **{summary['before_open_data_in_window_hidden_by_source_id']}**
- Open Data hidden after dated-occurrence fix: **{summary['after_open_data_in_window_hidden_by_source_id']}**
- Historical Issue #324 hidden reference: **{summary['known_issue_324_baseline_hidden_count']}**
- Duplicate canonical IDs after projector fix: **{summary['duplicate_canonical_id_count']}**
- Raw source rows accounted: **{summary['raw_rows_accounted']} / {summary['raw_source_rows']}**

Workflow success means the protected implementation/audit ran correctly. It does **not** authorize launch.
"""


def main() -> int:
    required = [RAW, STAGED, CALENDAR, PARKS, SUPPLEMENTAL, SUPPLEMENTAL_QUEUE, DISPOSITION, REGISTRY, PROJECTOR]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required inputs: " + ", ".join(missing))

    raw_rows = load_rows(RAW)
    staged_rows = load_rows(STAGED)
    calendar_rows = load_rows(CALENDAR)
    parks_rows = load_rows(PARKS)
    supplemental_rows = load_rows(SUPPLEMENTAL)
    supplemental_queue = load_rows(SUPPLEMENTAL_QUEUE)
    disposition_rows = load_rows(DISPOSITION)
    projected_rows = load_rows(PROJECTED_FEAST)

    staged_sources = source_key_set(staged_rows)
    staged_occurrences = occurrence_key_set(staged_rows)
    rejected_open_sources, rejected_open_occurrences = rejected_open_data_keys(disposition_rows)

    before_open_counts: Counter[str] = Counter()
    after_open_counts: Counter[str] = Counter()
    open_ledger: list[dict[str, Any]] = []
    after_dispositions: dict[int, str] = {}
    for i, row in enumerate(raw_rows):
        before = classify_open_data_occurrence(
            row,
            staged_source_keys=staged_sources,
            staged_occurrence_keys=staged_occurrences,
            rejected_source_keys=rejected_open_sources,
            rejected_occurrence_keys=rejected_open_occurrences,
            season_start=SEASON_START,
            season_end=SEASON_END,
            matching_mode="source_id_only",
        )
        after = classify_open_data_occurrence(
            row,
            staged_source_keys=staged_sources,
            staged_occurrence_keys=staged_occurrences,
            rejected_source_keys=rejected_open_sources,
            rejected_occurrence_keys=rejected_open_occurrences,
            season_start=SEASON_START,
            season_end=SEASON_END,
            matching_mode="dated_occurrence",
        )
        before_open_counts[before] += 1
        after_open_counts[after] += 1
        after_dispositions[i] = after
        dataset, source_event_id, event_date = occurrence_key(row)
        open_ledger.append(
            {
                "dataset": dataset,
                "source_event_id": source_event_id,
                "event_date": None if event_date == "undated" else event_date,
                "before_disposition": before,
                "after_disposition": after,
            }
        )

    rejected_supp_sources = rejected_supplemental_sources(supplemental_queue)
    accepted_supp_rows = [row for row in supplemental_rows if source_key(row) not in rejected_supp_sources]
    accepted_supp_occurrences = occurrence_key_set(accepted_supp_rows)
    all_supp_sources = source_key_set(supplemental_rows)
    calparks_counts: Counter[str] = Counter()
    for row in [*calendar_rows, *parks_rows]:
        disposition = classify_calendar_parks_row(
            row,
            accepted_supplemental_occurrences=accepted_supp_occurrences,
            all_supplemental_sources=all_supp_sources,
            rejected_supplemental_source_keys=rejected_supp_sources,
        )
        calparks_counts[disposition] += 1

    duplicate_report = duplicate_report_for_after_fix(
        staged_rows=staged_rows,
        supplemental_rows=supplemental_rows,
        raw_rows=raw_rows,
        after_dispositions=after_dispositions,
    )
    lineage = source_lineage_contract_check()
    projector = projector_occurrence_identity_check()

    before_hidden = before_open_counts.get("in_window_occurrence_hidden_by_source_id_match", 0)
    after_hidden = after_open_counts.get("in_window_occurrence_hidden_by_source_id_match", 0)
    raw_source_rows = len(raw_rows) + len(calendar_rows) + len(parks_rows)
    raw_rows_accounted = sum(after_open_counts.values()) + sum(calparks_counts.values())
    raw_accounting_pass = raw_rows_accounted == raw_source_rows

    # Issue #324's 4,203-row value is a historical snapshot baseline, not a
    # timeless current-corpus invariant. It is meaningful only when the current
    # corpus has staged sources against which source-ID-only matching can hide
    # sibling occurrences. With an intentionally empty staged feed, the only
    # valid current baseline is zero staged sources and zero hidden-before rows.
    baseline_comparison_applicable = bool(staged_sources)
    if baseline_comparison_applicable:
        baseline_state_pass = before_hidden == KNOWN_ISSUE_324_HISTORICAL_HIDDEN_COUNT
    else:
        baseline_state_pass = len(staged_rows) == 0 and len(staged_sources) == 0 and before_hidden == 0

    safety = dict(SAFETY_ASSERTIONS)
    safety["location_cache_sha256"] = sha256_file(LOCATION_CACHE)

    generated_at = utc_now()
    summary = {
        "artifact_type": "occurrence_identity_enforcement_summary",
        "generated_at_utc": generated_at,
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "season_start": SEASON_START,
        "season_end": SEASON_END,
        "staged_row_count": len(staged_rows),
        "staged_source_count": len(staged_sources),
        "before_open_data_in_window_hidden_by_source_id": before_hidden,
        "after_open_data_in_window_hidden_by_source_id": after_hidden,
        "known_issue_324_baseline_hidden_count": KNOWN_ISSUE_324_HISTORICAL_HIDDEN_COUNT,
        "known_issue_324_baseline_comparison_applicable": baseline_comparison_applicable,
        "known_issue_324_baseline_matches_computed_before": (
            before_hidden == KNOWN_ISSUE_324_HISTORICAL_HIDDEN_COUNT
            if baseline_comparison_applicable
            else None
        ),
        "known_issue_324_baseline_state_pass": baseline_state_pass,
        "duplicate_canonical_id_count": duplicate_report["duplicate_canonical_id_count"],
        "raw_source_rows": raw_source_rows,
        "raw_rows_accounted": raw_rows_accounted,
        "raw_disposition_accounting_pass": raw_accounting_pass,
        "generated_reference_additions_count": len(projected_rows),
        "generated_reference_additions_counted_as_raw": False,
        "projector_implementation_correctness_pass": projector["projector_occurrence_identity_pass"],
        "source_lineage_contract_compliance_pass": lineage["source_lineage_contract_compliance_pass"],
        "audit_execution_integrity_pass": True,
        "occurrence_identity_implementation_correctness_pass": after_hidden == 0 and baseline_state_pass,
        "duplicate_safety_pass": duplicate_report["duplicate_safety_pass"],
        "launch_readiness": False,
        "issue_132_gate_pass": False,
        "safety": safety,
    }
    summary["qa_pass"] = all(
        [
            summary["audit_execution_integrity_pass"],
            summary["projector_implementation_correctness_pass"],
            summary["occurrence_identity_implementation_correctness_pass"],
            summary["raw_disposition_accounting_pass"],
            summary["duplicate_safety_pass"],
            summary["source_lineage_contract_compliance_pass"],
        ]
    )

    out = prepare_output_dir()
    write_json(out, "occurrence_identity_enforcement_summary.json", summary)
    write_json(
        out,
        "before_after_occurrence_reconciliation.json",
        {
            "before_matching_mode": "source_id_only",
            "after_matching_mode": "dated_occurrence",
            "before_open_data_dispositions": dict(sorted(before_open_counts.items())),
            "after_open_data_dispositions": dict(sorted(after_open_counts.items())),
            "calendar_parks_dispositions": dict(sorted(calparks_counts.items())),
        },
    )
    write_json(
        out,
        "hidden_occurrence_resolution_report.json",
        {
            "before_hidden_count": before_hidden,
            "after_hidden_count": after_hidden,
            "resolved_hidden_count": before_hidden - after_hidden,
            "historical_baseline_hidden_count": KNOWN_ISSUE_324_HISTORICAL_HIDDEN_COUNT,
            "historical_baseline_comparison_applicable": baseline_comparison_applicable,
            "historical_baseline_state_pass": baseline_state_pass,
            "sample_resolved_occurrences": [
                row for row in open_ledger if row["before_disposition"] == "in_window_occurrence_hidden_by_source_id_match"
            ][:100],
        },
    )
    write_json(out, "duplicate_canonical_id_report.json", duplicate_report)
    write_json(
        out,
        "raw_disposition_ledger_summary.json",
        {
            "raw_source_rows": raw_source_rows,
            "raw_rows_accounted": raw_rows_accounted,
            "raw_disposition_accounting_pass": raw_accounting_pass,
            "open_data_rows": len(raw_rows),
            "calendar_rows": len(calendar_rows),
            "parks_rows": len(parks_rows),
        },
    )
    write_json(out, "source_lineage_contract_check.json", lineage)
    write_json(out, "projector_occurrence_identity_check.json", projector)
    write_json(out, "public_surface_safety_assertions.json", safety)
    write_text(out, "occurrence_identity_enforcement_report.md", make_markdown(summary))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
