#!/usr/bin/env python3
"""Focused tests for the source repository lineage audit."""

from __future__ import annotations

import shutil
from pathlib import Path

from audit_source_repository_lineage import (
    CATALOG_RAW_INTAKE_PATHS,
    KNOWN_REPOSITORIES,
    ROLE_VOCABULARY,
    build_audit,
    build_repository_inventory,
    build_source_lineage,
    summarize_existing_inventory,
)


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    repos = build_repository_inventory()
    if len(repos) < 9:
        fail("expected at least nine known NYCIF repositories")
    names = {row["repository"] for row in repos}
    for required in {
        "setoxxx/nycif-live-feeds",
        "setoxxx/nycif-web-platform",
        "setoxxx/nycif-open-data",
        "setoxxx/nycif-data-pipeline",
        "setoxxx/-nycif-data-pipeline",
        "setoxxx/nycif-event-radar",
        "setoxxx/nycif-field-desk",
        "setoxxx/nycif-prompt-engine",
        "setoxxx/nycif-national-pilot",
    }:
        if required not in names:
            fail(f"missing repository classification for {required}")
    for row in repos:
        if row["primary_role"] not in ROLE_VOCABULARY:
            fail(f"unknown primary role for {row['repository']}")

    inventory = summarize_existing_inventory()
    if not inventory["uses_hardcoded_source_catalog"]:
        fail("expected current inventory script to use hardcoded SOURCE_CATALOG")
    if set(inventory["raw_intake_paths"]) != CATALOG_RAW_INTAKE_PATHS:
        fail("expected current raw-intake inventory to be limited to the three catalog paths")

    lineage = build_source_lineage()
    if len(lineage) < 16:
        fail("expected lineage to include existing catalog entries")
    raw_paths = {row["path"] for row in lineage if row.get("is_raw_intake") and row.get("repository") == "setoxxx/nycif-live-feeds"}
    if raw_paths != CATALOG_RAW_INTAKE_PATHS:
        fail("live-feeds raw-intake path classification changed unexpectedly")
    if not any(row.get("source_key") == "nyc_event_calendar_api" for row in lineage):
        fail("expected optional NYC Event Calendar API lane to be represented as missing from current inventory")
    if not any(row.get("repository") == "setoxxx/nycif-event-radar" for row in lineage):
        fail("expected event-radar source-manifest lineage expectation")

    out_dir = Path("/tmp/source-repository-lineage-test")
    shutil.rmtree(out_dir, ignore_errors=True)
    summary = build_audit(out_dir)
    expected_outputs = {
        "repository_inventory.json",
        "source_file_lineage.json",
        "cross_repo_dataflow.md",
        "unexplained_sources.json",
        "generated_output_double_counting_risks.json",
        "public_surface_mutation_safety.json",
        "audit_summary.json",
    }
    missing = [name for name in expected_outputs if not (out_dir / name).exists()]
    if missing:
        fail("missing protected outputs: " + ", ".join(sorted(missing)))
    if not summary["audit_execution_integrity_pass"]:
        fail("audit execution integrity should pass")
    if summary["launch_readiness_pass"]:
        fail("launch readiness must never be inferred by this audit")
    if summary["safety"]["proposal_only"] is not True:
        fail("audit must remain proposal-only")
    if summary["safety"]["location_cache_modified"] is not False:
        fail("audit must not modify location_cache")
    if summary["missing_from_existing_source_catalog_count"] <= 0:
        fail("expected missing cross-repo source paths to be flagged")

    print("source repository lineage audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
