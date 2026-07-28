#!/usr/bin/env python3
"""Protected audit for the Enigma source-lineage registry contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "source_lineage_registry_v01.json"

REQUIRED_FIELDS = [
    "id","repository","path_or_source","owner_role","primary_role","source_type","current_status","public_surface_risk",
    "can_affect_public_map","can_affect_event_list","can_affect_review_queue","can_affect_wordpress","can_affect_location_cache",
    "can_affect_generated_feeds","raw_intake_countable","generated_output","historical_only","duplicative_copy","review_only",
    "staging_only","public_ready","requires_occurrence_key","identity_granularity","date_window_policy","location_policy",
    "category_policy","dedupe_policy","performance_role","national_expansion_role","launch_gate_status","reason_code","notes",
]
PRIMARY_ROLES = {
    "raw_intake_source","raw_snapshot","processor","normalizer","enrichment_or_geocoding","review_queue","generated_feed",
    "page_shard_or_manifest","public_surface","staging_surface","editorial_signal","prompt_or_generation_support",
    "reference_cache","historical_snapshot","duplicative_copy","national_expansion_pilot","unknown_pending_review",
}
PERFORMANCE_ROLES = {
    "small_boot_feed","major_default_feed","paginated_approved_feed","paginated_review_feed","admin_only_feed",
    "generated_static_feed","live_api_source","offline_batch_source","cache_or_reference","not_for_runtime_load",
}
REQUIRED_REPOSITORIES = {
    "setoxxx/nycif-live-feeds","setoxxx/nycif-web-platform","setoxxx/nycif-open-data","setoxxx/nycif-data-pipeline",
    "setoxxx/-nycif-data-pipeline","setoxxx/nycif-event-radar","setoxxx/nycif-field-desk",
    "setoxxx/nycif-prompt-engine","setoxxx/nycif-national-pilot",
}
REQUIRED_PATHS = {
    "data/raw_nyc_open_data_snapshot.json","data/nyc_citywide_events_calendar_snapshot.json",
    "data/nyc_parks_bigapps_events_snapshot.json","data/nycif_staged_live_events.json",
    "data/supplemental_events_staging_feed.json","nycif_all_radar_map_events.json",
    "data/nycif_live_test_enriched_events.json","data/previous_staged_live_events_snapshot.json",
    "nycif_major_radar_map_events.json","data/row_disposition_events.json","data/events_schema_v1_staged.json",
    "data/events_schema_v1_supplemental_review.json","data/events_schema_v1_major.json",
    "data/schema-v1/approved/manifest.json","data/schema-v1/review/manifest.json","data/location_cache.json",
    "data/sources/source_registry.yml","scripts/pull_socrata.py","scripts/pull_nyc_event_calendar_api.py",
    "scripts/normalize_events.py","scripts/build_geojson.py","public/feeds/events-current.geojson",
    "public/feeds/live/events-live.geojson","config/source_manifest.csv","approved-export-preview.html","desk.html?previewExport=1",
}
EXPECTED_SAFETY = {
    "approval_state_modified": False,
    "data_location_cache_json_modified": False,
    "homepage_modified": False,
    "navigation_modified": False,
    "production_feed_modified": False,
    "promotion_allowed": False,
    "proposal_only": True,
    "public_launch_authorized": False,
    "public_map_modified": False,
    "theme_modified": False,
    "wordpress_modified": False,
}


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(path: Path):
    resolved = path.resolve()
    tmp = Path("/tmp").resolve()
    if resolved != tmp and tmp not in resolved.parents:
        raise ValueError(f"protected output must stay under /tmp: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def write_json(path: Path, payload):
    safe_path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str):
    safe_path(path).write_text(text, encoding="utf-8")


def load_entries(registry):
    fields = registry.get("entry_fields") or REQUIRED_FIELDS
    defaults = registry.get("entry_defaults") or {}
    entries = []
    for index, raw in enumerate(registry.get("entries") or []):
        row = dict(defaults)
        if isinstance(raw, dict):
            row.update(raw)
        elif isinstance(raw, list):
            if len(raw) != len(fields):
                raise ValueError(f"entry row {index} has {len(raw)} values; expected {len(fields)}")
            row.update(dict(zip(fields, raw)))
        else:
            raise TypeError(f"entry {index} must be object or row list")
        entries.append(row)
    return entries


def validate(registry, entries):
    errors = []
    seen = set()
    for i, e in enumerate(entries):
        missing = [field for field in REQUIRED_FIELDS if field not in e]
        extra = sorted(set(e) - set(REQUIRED_FIELDS))
        if missing:
            errors.append(f"entry {i} missing fields: {', '.join(missing)}")
        if extra:
            errors.append(f"{e.get('id', i)} has extra fields: {', '.join(extra)}")
        if e.get("id") in seen:
            errors.append(f"duplicate id: {e.get('id')}")
        seen.add(e.get("id"))
        if e.get("primary_role") not in PRIMARY_ROLES:
            errors.append(f"{e.get('id')} invalid primary_role {e.get('primary_role')}")
        if e.get("performance_role") not in PERFORMANCE_ROLES:
            errors.append(f"{e.get('id')} invalid performance_role {e.get('performance_role')}")
        for field in REQUIRED_FIELDS:
            if field.startswith("can_affect_") or field in {
                "raw_intake_countable","generated_output","historical_only","duplicative_copy","review_only",
                "staging_only","public_ready","requires_occurrence_key",
            }:
                if not isinstance(e.get(field), bool):
                    errors.append(f"{e.get('id')} field {field} must be boolean")
    if registry.get("safety_assertions") != EXPECTED_SAFETY:
        errors.append("safety assertions missing or incorrect")
    standard = registry.get("universal_occurrence_identity_standard") or {}
    minimum = standard.get("minimum_key") or []
    for key in ("source_namespace", "source_dataset_id", "source_record_id", "normalized_event_date"):
        if key not in minimum:
            errors.append(f"occurrence standard missing {key}")
    if standard.get("source_id_only_matching_allowed_for_recurring_event_feeds") is not False:
        errors.append("source-id-only matching must be rejected for recurring feeds")
    return errors


def compact(e):
    return {k: e[k] for k in ("id", "repository", "path_or_source", "primary_role", "reason_code", "launch_gate_status")}


def build_reports(entries):
    repos = {e["repository"] for e in entries}
    paths = {e["path_or_source"] for e in entries}
    coverage = {
        "entry_count": len(entries),
        "repository_count": len(repos),
        "covered_repositories": sorted(repos),
        "missing_required_repositories": sorted(REQUIRED_REPOSITORIES - repos),
        "missing_required_paths": sorted(REQUIRED_PATHS - paths),
    }
    raw_generated = {
        "raw_intake_countable_entries": [e["id"] for e in entries if e["raw_intake_countable"]],
        "generated_output_entries": [e["id"] for e in entries if e["generated_output"]],
        "generated_output_counted_as_raw": [e["id"] for e in entries if e["generated_output"] and e["raw_intake_countable"]],
        "historical_snapshot_counted_as_current_raw": [e["id"] for e in entries if e["historical_only"] and e["raw_intake_countable"]],
        "duplicative_copy_without_primary_role": [e["id"] for e in entries if e["duplicative_copy"] and e["primary_role"] != "duplicative_copy"],
    }
    raw_generated["raw_vs_generated_rules_pass"] = not (
        raw_generated["generated_output_counted_as_raw"]
        or raw_generated["historical_snapshot_counted_as_current_raw"]
        or raw_generated["duplicative_copy_without_primary_role"]
    )
    occurrence_risks = [
        e for e in entries
        if e["requires_occurrence_key"]
        and (
            e["identity_granularity"] == "source_id_only"
            or "risk" in e["identity_granularity"].lower()
            or "required" in e["identity_granularity"].lower()
            or "legacy" in e["identity_granularity"].lower()
        )
    ]
    occurrence = {
        "occurrence_key_required_count": sum(1 for e in entries if e["requires_occurrence_key"]),
        "source_id_only_violations": [e["id"] for e in occurrence_risks if e["identity_granularity"] == "source_id_only"],
        "occurrence_identity_risk_count": len(occurrence_risks),
        "occurrence_identity_risk_entries": [compact(e) | {"identity_granularity": e["identity_granularity"]} for e in occurrence_risks],
        "occurrence_identity_coverage_pass": not occurrence_risks,
    }
    surface_risks = [
        e for e in entries
        if e["public_surface_risk"] in {"medium", "high"} or e["can_affect_public_map"] or e["can_affect_wordpress"]
    ]
    public_surface = {
        "public_surface_risk_count": len(surface_risks),
        "public_surface_risks": [compact(e) | {"risk": e["public_surface_risk"]} for e in surface_risks],
        "review_only_marked_public_ready": [e["id"] for e in entries if e["review_only"] and e["public_ready"]],
    }
    public_surface["public_surface_gate_pass"] = not public_surface["review_only_marked_public_ready"]
    public_generated = [e for e in entries if e["generated_output"] and (e["can_affect_public_map"] or e["can_affect_event_list"])]
    performance_errors = [
        e for e in public_generated
        if e["performance_role"] not in {
            "small_boot_feed","major_default_feed","paginated_approved_feed","paginated_review_feed","generated_static_feed","admin_only_feed",
        }
    ]
    performance = {
        "performance_role_counts": dict(sorted(Counter(e["performance_role"] for e in entries).items())),
        "public_generated_outputs": [e["id"] for e in public_generated],
        "public_generated_outputs_without_runtime_role": [e["id"] for e in performance_errors],
        "performance_loading_risk_count": len(performance_errors),
        "performance_readiness_pass": not performance_errors,
    }
    national_blockers = [
        e for e in entries
        if any(word in e["national_expansion_role"].lower() for word in ("unknown", "required", "needs"))
    ]
    national = {
        "national_expansion_blocker_count": len(national_blockers),
        "national_expansion_blockers": [compact(e) | {"national_expansion_role": e["national_expansion_role"]} for e in national_blockers],
        "national_expansion_readiness_pass": not national_blockers,
    }
    unresolved_entries = [
        e for e in entries
        if e["primary_role"] == "unknown_pending_review"
        or any(word in e["current_status"].lower() for word in ("unknown", "needs", "blocked"))
        or "blocked" in e["launch_gate_status"].lower()
    ]
    unresolved = {
        "unresolved_lineage_item_count": len(unresolved_entries) + len(coverage["missing_required_repositories"]) + len(coverage["missing_required_paths"]),
        "unresolved_entries": [compact(e) | {"current_status": e["current_status"]} for e in unresolved_entries],
        "missing_required_repositories": coverage["missing_required_repositories"],
        "missing_required_paths": coverage["missing_required_paths"],
    }
    return coverage, raw_generated, occurrence, public_surface, performance, national, unresolved


def make_md(summary):
    return f"""# Enigma source-lineage contract audit

Generated: {summary['generated_at_utc']}

## Result

- Audit execution integrity: **{summary['audit_execution_integrity_pass']}**
- Source-lineage contract completeness: **{summary['source_lineage_contract_completeness_pass']}**
- Occurrence-identity coverage: **{summary['occurrence_identity_coverage_pass']}**
- Raw-vs-generated counting rules: **{summary['raw_vs_generated_rules_pass']}**
- Performance readiness: **{summary['performance_readiness_pass']}**
- National expansion readiness: **{summary['national_expansion_readiness_pass']}**
- Launch readiness: **{summary['launch_readiness']}**

## Counts

- Registry entries: **{summary['registry_entry_count']}**
- Repositories represented: **{summary['repository_count']}**
- Occurrence-identity risks: **{summary['occurrence_identity_risk_count']}**
- Public-surface risks: **{summary['public_surface_risk_count']}**
- Performance/loading risks: **{summary['performance_loading_risk_count']}**
- National expansion blockers: **{summary['national_expansion_blocker_count']}**
- Unresolved lineage items: **{summary['unresolved_lineage_item_count']}**

Workflow success means the contract audit ran correctly. It does **not** authorize launch.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/source-lineage-contract"))
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = load_entries(registry)
    schema_errors = validate(registry, entries)
    coverage, raw_generated, occurrence, public_surface, performance, national, unresolved = build_reports(entries)

    audit_ok = not schema_errors and not coverage["missing_required_repositories"] and not coverage["missing_required_paths"]
    summary = {
        "artifact_type": "source_lineage_registry_audit_summary",
        "generated_at_utc": utc_now(),
        "repository": "setoxxx/nycif-live-feeds",
        "repository_sha": os.environ.get("AUDIT_SOURCE_SHA") or os.environ.get("GITHUB_SHA"),
        "registry_path": str(REGISTRY.relative_to(ROOT)),
        "registry_sha256": sha256_file(REGISTRY),
        "registry_entry_count": len(entries),
        "repository_count": coverage["repository_count"],
        "schema_error_count": len(schema_errors),
        "schema_errors": schema_errors,
        "unresolved_lineage_item_count": unresolved["unresolved_lineage_item_count"],
        "occurrence_identity_risk_count": occurrence["occurrence_identity_risk_count"],
        "performance_loading_risk_count": performance["performance_loading_risk_count"],
        "national_expansion_blocker_count": national["national_expansion_blocker_count"],
        "public_surface_risk_count": public_surface["public_surface_risk_count"],
        "audit_execution_integrity_pass": audit_ok,
        "source_lineage_contract_completeness_pass": audit_ok and unresolved["unresolved_lineage_item_count"] == 0,
        "occurrence_identity_coverage_pass": occurrence["occurrence_identity_coverage_pass"],
        "raw_vs_generated_rules_pass": raw_generated["raw_vs_generated_rules_pass"],
        "public_surface_gate_pass": public_surface["public_surface_gate_pass"],
        "performance_readiness_pass": performance["performance_readiness_pass"],
        "national_expansion_readiness_pass": national["national_expansion_readiness_pass"],
        "launch_readiness": False,
        "issue_132_gate_pass": False,
        "safety": registry["safety_assertions"],
    }
    out = safe_path(args.out_dir)
    write_json(out / "source_lineage_registry_audit_summary.json", summary)
    write_json(out / "source_lineage_registry_expanded.json", {"entries": entries, "safety_assertions": registry["safety_assertions"]})
    write_json(out / "occurrence_identity_coverage.json", occurrence)
    write_json(out / "raw_vs_generated_counting_rules.json", raw_generated)
    write_json(out / "public_surface_risk_report.json", public_surface)
    write_json(out / "performance_loading_risk_report.json", performance)
    write_json(out / "national_expansion_readiness_report.json", national)
    write_json(out / "unresolved_lineage_items.json", unresolved)
    write_text(out / "cross_repo_contract_report.md", make_md(summary))
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if audit_ok and raw_generated["raw_vs_generated_rules_pass"] and public_surface["public_surface_gate_pass"] and performance["performance_readiness_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
