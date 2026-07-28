#!/usr/bin/env python3
"""Build a protected cross-repository source-lineage audit artifact.

This audit is read-only. It classifies the known NYCIF repositories and the
current event-like source/feed paths, separates raw intake from generated output,
and writes protected evidence only under /tmp.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ROLE_VOCABULARY = {
    "raw_intake_source",
    "raw_snapshot",
    "processor",
    "enrichment_or_geocoding",
    "review_queue",
    "generated_feed",
    "page_shard_or_manifest",
    "public_surface",
    "staging_surface",
    "editorial_signal",
    "prompt_or_generation_support",
    "reference_cache",
    "historical_snapshot",
    "duplicative_copy",
    "national_expansion_pilot",
    "unknown_pending_review",
}

KNOWN_REPOSITORIES: list[dict[str, Any]] = [
    {
        "repository": "setoxxx/nycif-live-feeds",
        "primary_role": "processor",
        "secondary_roles": ["raw_snapshot", "generated_feed", "review_queue", "reference_cache"],
        "visibility": "public",
        "can_affect_public_map_output": True,
        "can_affect_event_list_output": True,
        "can_affect_wordpress_public_presentation": False,
        "supports_national_expansion_architecture": False,
        "current_gate_status": "included_in_parent_gate",
        "reason": "Current committed feed, GPS, discovery taxonomy, review, source inventory, schema-v1, and artifact evidence repository.",
    },
    {
        "repository": "setoxxx/nycif-web-platform",
        "primary_role": "public_surface",
        "secondary_roles": ["staging_surface", "prompt_or_generation_support"],
        "visibility": "private",
        "can_affect_public_map_output": True,
        "can_affect_event_list_output": True,
        "can_affect_wordpress_public_presentation": True,
        "supports_national_expansion_architecture": False,
        "current_gate_status": "included_in_parent_gate",
        "reason": "Planning, WordPress integration, map shell, SEO/mobile, public launch, and pre-launch gate repository.",
    },
    {
        "repository": "setoxxx/nycif-open-data",
        "primary_role": "raw_intake_source",
        "secondary_roles": ["processor", "generated_feed", "public_surface"],
        "visibility": "public",
        "can_affect_public_map_output": True,
        "can_affect_event_list_output": False,
        "can_affect_wordpress_public_presentation": True,
        "supports_national_expansion_architecture": True,
        "current_gate_status": "needs_explicit_lineage_link",
        "reason": "Open Data map/aggregation repository; queries Socrata and stores derived small artifacts rather than raw dumps.",
    },
    {
        "repository": "setoxxx/nycif-data-pipeline",
        "primary_role": "processor",
        "secondary_roles": ["raw_intake_source", "raw_snapshot", "enrichment_or_geocoding", "generated_feed"],
        "visibility": "private",
        "can_affect_public_map_output": True,
        "can_affect_event_list_output": True,
        "can_affect_wordpress_public_presentation": True,
        "supports_national_expansion_architecture": True,
        "current_gate_status": "missing_from_live_feeds_source_inventory",
        "reason": "Separate daily source verification, Socrata pull, normalization, geocoding, GeoJSON, prepublish, and live-feed release pipeline.",
    },
    {
        "repository": "setoxxx/-nycif-data-pipeline",
        "primary_role": "unknown_pending_review",
        "secondary_roles": [],
        "visibility": "private",
        "can_affect_public_map_output": False,
        "can_affect_event_list_output": False,
        "can_affect_wordpress_public_presentation": False,
        "supports_national_expansion_architecture": False,
        "current_gate_status": "empty_or_placeholder_pending_confirmation",
        "reason": "Placeholder/duplicate-name repository; must remain explicitly classified instead of ignored.",
    },
    {
        "repository": "setoxxx/nycif-event-radar",
        "primary_role": "editorial_signal",
        "secondary_roles": ["raw_intake_source", "review_queue", "generated_feed", "public_surface"],
        "visibility": "private",
        "can_affect_public_map_output": True,
        "can_affect_event_list_output": True,
        "can_affect_wordpress_public_presentation": True,
        "supports_national_expansion_architecture": True,
        "current_gate_status": "missing_from_live_feeds_source_inventory",
        "reason": "Backend event-intake and editorial radar workflow that can export public/admin map JSON, guides, calendars, and WordPress publishing material.",
    },
    {
        "repository": "setoxxx/nycif-field-desk",
        "primary_role": "public_surface",
        "secondary_roles": ["staging_surface"],
        "visibility": "public",
        "can_affect_public_map_output": True,
        "can_affect_event_list_output": True,
        "can_affect_wordpress_public_presentation": True,
        "supports_national_expansion_architecture": False,
        "current_gate_status": "included_as_frontend_dependency",
        "reason": "Frontend/map PWA that consumes live-feeds outputs and must not load review-only artifacts as public data.",
    },
    {
        "repository": "setoxxx/nycif-prompt-engine",
        "primary_role": "prompt_or_generation_support",
        "secondary_roles": ["editorial_signal"],
        "visibility": "private",
        "can_affect_public_map_output": False,
        "can_affect_event_list_output": False,
        "can_affect_wordpress_public_presentation": True,
        "supports_national_expansion_architecture": True,
        "current_gate_status": "supporting_editorial_system",
        "reason": "Private editorial/prompt/source-aware workflow; supports sourcing and publishing discipline but is not a canonical event feed.",
    },
    {
        "repository": "setoxxx/nycif-national-pilot",
        "primary_role": "national_expansion_pilot",
        "secondary_roles": ["processor"],
        "visibility": "private",
        "can_affect_public_map_output": False,
        "can_affect_event_list_output": False,
        "can_affect_wordpress_public_presentation": False,
        "supports_national_expansion_architecture": True,
        "current_gate_status": "fixture_only_read_only_boundary",
        "reason": "National expansion research repository; current production systems are read-only evidence sources and publication connectivity is disabled by default.",
    },
]

EXTERNAL_SOURCE_EXPECTATIONS: list[dict[str, Any]] = [
    {
        "repository": "setoxxx/nycif-data-pipeline",
        "path": "data/sources/source_registry.yml",
        "source_key": "nyc_permitted_event_information",
        "dataset_id": "tvpp-9vvx",
        "primary_role": "raw_intake_source",
        "identity_granularity": "source_record_id_plus_event_time_needed",
        "lineage_status": "missing_from_live_feeds_source_inventory",
        "risk": "parallel source registry can drift from live-feeds hardcoded SOURCE_CATALOG",
    },
    {
        "repository": "setoxxx/nycif-data-pipeline",
        "path": "data/sources/source_registry.yml",
        "source_key": "nyc_parks_public_events_14_days",
        "dataset_id": "w3wp-dpdi",
        "primary_role": "raw_intake_source",
        "identity_granularity": "source_record_id_plus_event_time_needed",
        "lineage_status": "missing_from_live_feeds_source_inventory",
        "risk": "parallel source registry can drift from live-feeds hardcoded SOURCE_CATALOG",
    },
    {
        "repository": "setoxxx/nycif-data-pipeline",
        "path": "scripts/pull_nyc_event_calendar_api.py",
        "source_key": "nyc_event_calendar_api",
        "dataset_id": "nyc_event_calendar_api",
        "primary_role": "raw_intake_source",
        "identity_granularity": "optional_api_record_plus_event_time_needed",
        "lineage_status": "missing_from_live_feeds_source_inventory",
        "risk": "optional API lane can add records outside the live-feeds hardcoded source inventory",
    },
    {
        "repository": "setoxxx/nycif-data-pipeline",
        "path": "public/feeds/events-current.geojson",
        "source_key": "events-current-geojson",
        "dataset_id": None,
        "primary_role": "generated_feed",
        "identity_granularity": "normalized_record_identity",
        "lineage_status": "missing_from_live_feeds_source_inventory",
        "risk": "generated public GeoJSON must not be double-counted as raw intake",
    },
    {
        "repository": "setoxxx/nycif-event-radar",
        "path": "config/source_manifest.csv",
        "source_key": "event-radar-source-manifest",
        "dataset_id": None,
        "primary_role": "editorial_signal",
        "identity_granularity": "source_url_plus_event_window_needed",
        "lineage_status": "missing_from_live_feeds_source_inventory",
        "risk": "manual/editorial radar sources can produce candidate public-map JSON outside the canonical inventory",
    },
    {
        "repository": "setoxxx/nycif-field-desk",
        "path": "approved-export-preview.html / desk.html?previewExport=1",
        "source_key": "supplemental-approved-export-preview",
        "dataset_id": None,
        "primary_role": "staging_surface",
        "identity_granularity": "display_only_preview",
        "lineage_status": "frontend_dependency_missing_from_source_inventory",
        "risk": "review/export previews must remain non-production and promotion_allowed=false",
    },
]

CATALOG_RAW_INTAKE_PATHS = {
    "data/raw_nyc_open_data_snapshot.json",
    "data/nyc_citywide_events_calendar_snapshot.json",
    "data/nyc_parks_bigapps_events_snapshot.json",
}

PUBLIC_MUTATION_PATHS = (
    "data/location_cache.json",
    "data/nycif_staged_live_events.json",
    "public/feeds/",
    "nycif_all_radar_map_events.json",
    "nycif_major_radar_map_events.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_protected_dir(path: Path) -> Path:
    resolved = path.resolve()
    tmp_root = Path("/tmp").resolve()
    if resolved != tmp_root and tmp_root not in resolved.parents:
        raise ValueError(f"protected audit output must remain under /tmp: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_source_catalog(script_path: Path) -> list[dict[str, Any]]:
    if not script_path.exists():
        return []
    tree = ast.parse(script_path.read_text(encoding="utf-8"), filename=str(script_path))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "SOURCE_CATALOG" for target in node.targets):
            value = ast.literal_eval(node.value)
            return value if isinstance(value, list) else []
    return []


def classify_catalog_entry(entry: dict[str, Any]) -> dict[str, Any]:
    file_path = str(entry.get("file_path") or "")
    status = str(entry.get("current_pipeline_status") or "")
    role = "unknown_pending_review"
    if status == "used" and file_path in CATALOG_RAW_INTAKE_PATHS:
        role = "raw_intake_source"
    elif status == "used":
        role = "generated_feed"
    elif status == "review_only":
        role = "review_queue"
    elif status == "generated_output":
        if "manifest" in file_path or "/pages/" in file_path:
            role = "page_shard_or_manifest"
        else:
            role = "generated_feed"
    elif status == "duplicative_source":
        role = "duplicative_copy"
    elif status == "historical_only":
        if "location_cache" in file_path:
            role = "reference_cache"
        else:
            role = "historical_snapshot"
    path = ROOT / file_path
    return {
        "repository": "setoxxx/nycif-live-feeds",
        "path": file_path,
        "dataset_key": entry.get("dataset_key"),
        "primary_role": role,
        "current_pipeline_status": status,
        "canonical_projection_status": entry.get("canonical_projection_status"),
        "included_in_existing_source_catalog": True,
        "is_raw_intake": file_path in CATALOG_RAW_INTAKE_PATHS,
        "is_generated_output": role in {"generated_feed", "page_shard_or_manifest"},
        "is_duplicative_or_historical": role in {"duplicative_copy", "historical_snapshot"},
        "identity_granularity": "unknown_or_mixed_from_catalog",
        "risk_flags": risk_flags_for_lineage_path(file_path, role),
        "exists_on_branch": path.exists(),
        "sha256": sha256_file(path),
    }


def risk_flags_for_lineage_path(path: str, role: str) -> list[str]:
    risks: list[str] = []
    if role in {"generated_feed", "page_shard_or_manifest"}:
        risks.append("do_not_count_as_raw_intake")
    if role in {"historical_snapshot", "duplicative_copy"}:
        risks.append("do_not_count_as_current_raw_intake")
    if path == "data/location_cache.json":
        risks.append("protected_reference_cache_never_rewrite_in_audit")
    if path in CATALOG_RAW_INTAKE_PATHS:
        risks.append("needs_occurrence_level_identity_check")
    return risks


def summarize_existing_inventory() -> dict[str, Any]:
    inventory_path = ROOT / "data" / "events_source_inventory_v02.json"
    doc_path = ROOT / "docs" / "events-source-inventory-v02.md"
    script_path = ROOT / "scripts" / "inventory_events_sources_v02.py"
    catalog = extract_source_catalog(script_path)
    inventory = load_json(inventory_path) if inventory_path.exists() else {}
    raw_paths = sorted(
        str(path)
        for path in ((inventory.get("counting_rules") or {}).get("raw_intake") or [])
    )
    script_text = script_path.read_text(encoding="utf-8") if script_path.exists() else ""
    return {
        "script_path": str(script_path.relative_to(ROOT)),
        "script_sha256": sha256_file(script_path),
        "inventory_path": str(inventory_path.relative_to(ROOT)),
        "inventory_sha256": sha256_file(inventory_path),
        "doc_path": str(doc_path.relative_to(ROOT)),
        "doc_sha256": sha256_file(doc_path),
        "source_catalog_entry_count": len(catalog),
        "inventory_source_file_count": inventory.get("source_file_count"),
        "inventory_generated_at_utc": inventory.get("generated_at_utc"),
        "raw_intake_paths": raw_paths,
        "raw_intake_limited_to_three_catalog_paths": set(raw_paths) == CATALOG_RAW_INTAKE_PATHS,
        "uses_hardcoded_source_catalog": "SOURCE_CATALOG" in script_text and "data/raw_nyc_open_data_snapshot.json" in script_text,
        "raw_intake_source_row_total": inventory.get("raw_intake_source_row_total"),
        "generated_output_row_total": inventory.get("generated_output_row_total"),
        "duplicative_source_row_total": inventory.get("duplicative_source_row_total"),
        "historical_only_row_total": inventory.get("historical_only_row_total"),
    }


def build_repository_inventory() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for repo in KNOWN_REPOSITORIES:
        primary = repo["primary_role"]
        if primary not in ROLE_VOCABULARY:
            raise ValueError(f"unknown role {primary} for {repo['repository']}")
        rows.append(
            {
                **repo,
                "role_is_known": primary in ROLE_VOCABULARY,
                "affects": {
                    "public_map_output": bool(repo["can_affect_public_map_output"]),
                    "event_list_output": bool(repo["can_affect_event_list_output"]),
                    "wordpress_public_presentation": bool(repo["can_affect_wordpress_public_presentation"]),
                    "national_expansion_architecture": bool(repo["supports_national_expansion_architecture"]),
                },
            }
        )
    return rows


def build_source_lineage() -> list[dict[str, Any]]:
    catalog_entries = [classify_catalog_entry(entry) for entry in extract_source_catalog(ROOT / "scripts" / "inventory_events_sources_v02.py")]
    external_entries = []
    current_catalog_keys = {str(entry.get("dataset_key") or entry.get("source_key") or "") for entry in catalog_entries}
    for entry in EXTERNAL_SOURCE_EXPECTATIONS:
        source_key = str(entry["source_key"])
        external_entries.append(
            {
                **entry,
                "included_in_existing_source_catalog": source_key in current_catalog_keys,
                "is_raw_intake": entry["primary_role"] == "raw_intake_source",
                "is_generated_output": entry["primary_role"] == "generated_feed",
                "is_duplicative_or_historical": False,
                "risk_flags": [entry["risk"]],
                "exists_on_branch": None,
                "sha256": None,
            }
        )
    return catalog_entries + external_entries


def build_double_counting_risks(lineage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks = []
    for row in lineage:
        if row.get("is_generated_output") or row.get("is_duplicative_or_historical"):
            risks.append(
                {
                    "repository": row.get("repository"),
                    "path": row.get("path"),
                    "source_key": row.get("source_key") or row.get("dataset_key"),
                    "role": row.get("primary_role"),
                    "risk": "would inflate raw-intake accounting if counted as an independent source",
                }
            )
    return risks


def build_unexplained_sources(repository_inventory: list[dict[str, Any]], lineage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unexplained = []
    for repo in repository_inventory:
        if repo.get("primary_role") == "unknown_pending_review" or repo.get("current_gate_status") in {"missing_from_live_feeds_source_inventory", "needs_explicit_lineage_link"}:
            unexplained.append(
                {
                    "type": "repository",
                    "repository": repo["repository"],
                    "role": repo["primary_role"],
                    "reason": repo["current_gate_status"],
                }
            )
    for row in lineage:
        if not row.get("included_in_existing_source_catalog"):
            unexplained.append(
                {
                    "type": "source_path",
                    "repository": row.get("repository"),
                    "path": row.get("path"),
                    "source_key": row.get("source_key") or row.get("dataset_key"),
                    "role": row.get("primary_role"),
                    "reason": row.get("lineage_status") or "not listed in current hardcoded SOURCE_CATALOG",
                }
            )
    return unexplained


def build_public_surface_safety() -> dict[str, Any]:
    return {
        "location_cache_modified": False,
        "production_feed_modified": False,
        "promotion_allowed": False,
        "proposal_only": True,
        "public_map_modified": False,
        "wordpress_modified": False,
        "homepage_modified": False,
        "navigation_modified": False,
        "theme_modified": False,
        "approval_state_modified": False,
        "protected_paths_not_written_by_audit": list(PUBLIC_MUTATION_PATHS),
    }


def build_markdown_report(summary: dict[str, Any], repos: list[dict[str, Any]], lineage: list[dict[str, Any]], unexplained: list[dict[str, Any]]) -> str:
    lines = [
        "# Source repository lineage audit",
        "",
        f"Generated: `{summary['generated_at_utc']}`",
        f"Repository SHA: `{summary['repository_sha']}`",
        "",
        "## Result",
        "",
        f"- Audit execution integrity: **{summary['audit_execution_integrity_pass']}**",
        f"- Source-lineage completeness: **{summary['source_lineage_completeness_pass']}**",
        f"- Launch readiness: **{summary['launch_readiness_pass']}**",
        f"- Repositories classified: **{summary['repository_count']}**",
        f"- Source/file lineage rows classified: **{summary['source_file_lineage_count']}**",
        f"- Unexplained sources/repositories: **{summary['unexplained_source_count']}**",
        f"- Public-surface risks: **{summary['public_surface_risk_count']}**",
        "",
        "## Repository roles",
        "",
    ]
    for repo in repos:
        lines.append(f"- `{repo['repository']}` — `{repo['primary_role']}` — {repo['current_gate_status']}")
    lines.extend(["", "## Source/file lineage", ""])
    for row in lineage:
        key = row.get("source_key") or row.get("dataset_key") or "unknown"
        lines.append(f"- `{row.get('repository')}` / `{row.get('path')}` — `{key}` — `{row.get('primary_role')}`")
    lines.extend(["", "## Unexplained / missing lineage", ""])
    if unexplained:
        for row in unexplained:
            lines.append(f"- `{row.get('type')}` — `{row.get('repository')}` — `{row.get('path') or row.get('source_key') or ''}` — {row.get('reason')}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Launch boundary",
            "",
            "This artifact is audit-only. It does not authorize launch, feed promotion, WordPress publication, public `/map/` changes, or `data/location_cache.json` writes.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_audit(out_dir: Path) -> dict[str, Any]:
    out_dir = ensure_protected_dir(out_dir)
    repository_inventory = build_repository_inventory()
    source_lineage = build_source_lineage()
    existing_inventory = summarize_existing_inventory()
    unexplained = build_unexplained_sources(repository_inventory, source_lineage)
    double_counting = build_double_counting_risks(source_lineage)
    safety = build_public_surface_safety()
    public_surface_risks = [
        row for row in repository_inventory if row.get("can_affect_public_map_output") or row.get("can_affect_wordpress_public_presentation")
    ]
    unknown_repo_count = sum(1 for row in repository_inventory if row["primary_role"] == "unknown_pending_review")
    missing_from_catalog_count = sum(1 for row in source_lineage if not row.get("included_in_existing_source_catalog"))
    source_lineage_completeness_pass = unknown_repo_count == 0 and missing_from_catalog_count == 0
    audit_execution_integrity_pass = (
        len(repository_inventory) >= 9
        and len(source_lineage) >= 16
        and existing_inventory["uses_hardcoded_source_catalog"] is True
        and existing_inventory["raw_intake_limited_to_three_catalog_paths"] is True
        and safety["proposal_only"] is True
    )
    summary = {
        "artifact_type": "source_repository_lineage_audit",
        "generated_at_utc": utc_now(),
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "audit_execution_integrity_pass": audit_execution_integrity_pass,
        "source_lineage_completeness_pass": source_lineage_completeness_pass,
        "launch_readiness_pass": False,
        "issue_132_gate_pass": False,
        "repository_count": len(repository_inventory),
        "source_file_lineage_count": len(source_lineage),
        "unexplained_source_count": len(unexplained),
        "public_surface_risk_count": len(public_surface_risks),
        "generated_output_double_counting_risk_count": len(double_counting),
        "unknown_repository_count": unknown_repo_count,
        "missing_from_existing_source_catalog_count": missing_from_catalog_count,
        "existing_inventory": existing_inventory,
        "safety": safety,
        "notes": [
            "Successful execution means the audit ran and wrote protected evidence; it does not mean source-lineage completeness passed.",
            "The current live-feeds source inventory is useful but hardcoded and limited to three raw-intake paths.",
            "External repository expectations are classified so they cannot be silently ignored before national expansion.",
            "This audit does not write production feeds, WordPress, public map code, approval state, or data/location_cache.json.",
        ],
    }
    write_json(out_dir / "repository_inventory.json", repository_inventory)
    write_json(out_dir / "source_file_lineage.json", source_lineage)
    write_json(out_dir / "unexplained_sources.json", unexplained)
    write_json(out_dir / "generated_output_double_counting_risks.json", double_counting)
    write_json(out_dir / "public_surface_mutation_safety.json", safety)
    write_json(out_dir / "audit_summary.json", summary)
    write_text(out_dir / "cross_repo_dataflow.md", build_markdown_report(summary, repository_inventory, source_lineage, unexplained))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/source-repository-lineage"))
    args = parser.parse_args()
    summary = build_audit(args.out_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["audit_execution_integrity_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
