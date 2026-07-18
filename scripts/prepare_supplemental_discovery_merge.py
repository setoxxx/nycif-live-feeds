#!/usr/bin/env python3
"""M11 supplemental → discovery merge readiness (prep only).

Analyzes approved supplemental export against current schema-v1-discovery approved
feed. Writes staging/report artifacts only — does NOT modify schema-v1-discovery,
location_cache.json, staged feeds, or public map feeds=main.

Outputs:
- data/reports/supplemental_discovery_merge_readiness_report.json
- data/staging/supplemental_discovery_merge_proposal/summary.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )
except ModuleNotFoundError:  # pragma: no cover
    from coverage_gap_utils import (
        DATA_DIR,
        load_json_file,
        repo_relative,
        save_json_file,
        utc_now_iso,
        valid_nyc_lat_lng,
    )

EXPORT_PATH = DATA_DIR / "supplemental_approved_export_feed.json"
APPROVED_MANIFEST = DATA_DIR / "schema-v1-discovery" / "approved" / "manifest.json"
APPROVED_PAGES = DATA_DIR / "schema-v1-discovery" / "approved" / "pages"
VALIDATION_REPORT = DATA_DIR / "supplemental_manual_approval_validation_report.json"
OVERLAP_REPORT = DATA_DIR / "reports" / "supplemental_overlap_key_coord_conflict_audit_report.json"
PHASE2E_VERIFY = DATA_DIR / "reports" / "supplemental_phase2e_promotion_dry_run_report.json"
EXPORT_REPORT = DATA_DIR / "reports" / "supplemental_approved_export_feed_report.json"

READINESS_REPORT = DATA_DIR / "reports" / "supplemental_discovery_merge_readiness_report.json"
PROPOSAL_SUMMARY = DATA_DIR / "staging" / "supplemental_discovery_merge_proposal" / "summary.json"


def norm_dataset(value: Any) -> str:
    return str(value or "").strip().lower()


def norm_id(value: Any) -> str:
    return str(value or "").strip()


def norm_date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 else text


def identity_key(dataset: str, source_event_id: str, day: str) -> tuple[str, str, str]:
    return (norm_dataset(dataset), norm_id(source_event_id), norm_date(day))


def load_approved_identities() -> tuple[set[tuple[str, str, str]], int, Counter[str]]:
    manifest = load_json_file(APPROVED_MANIFEST, {})
    pages = manifest.get("pages") if isinstance(manifest, dict) else []
    identities: set[tuple[str, str, str]] = set()
    categories: Counter[str] = Counter()
    total = 0

    for page in pages or []:
        page_name = page.get("page") if isinstance(page, dict) else None
        if not page_name:
            continue
        payload = load_json_file(APPROVED_PAGES / page_name, {})
        events = payload.get("events") if isinstance(payload, dict) else []
        for event in events or []:
            if not isinstance(event, dict):
                continue
            total += 1
            source = event.get("source") if isinstance(event.get("source"), dict) else {}
            nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
            day = norm_date(nycif.get("event_date") or event.get("start_date_time"))
            identities.add(
                identity_key(source.get("dataset"), source.get("source_event_id"), day)
            )
            categories[str(event.get("category") or "unknown")] += 1
    return identities, total, categories


def gate_report(path: Path, *, field: str = "qa_pass") -> dict[str, Any]:
    payload = load_json_file(path, {})
    if not isinstance(payload, dict):
        return {"path": repo_relative(path), "present": False, "qa_pass": False}
    return {
        "path": repo_relative(path),
        "present": True,
        "qa_pass": bool(payload.get(field)),
        "artifact_type": payload.get("artifact_type"),
    }


def analyze_export_events(
    events: list[dict[str, Any]], approved_identities: set[tuple[str, str, str]]
) -> dict[str, Any]:
    net_new: list[dict[str, Any]] = []
    already_in_approved: list[dict[str, Any]] = []
    missing_coords = 0
    intake_counts: Counter[str] = Counter()
    borough_counts: Counter[str] = Counter()

    for row in events:
        intake_counts[str(row.get("intake_type") or "unknown")] += 1
        borough_counts[str(row.get("borough") or "unknown")] += 1
        if not valid_nyc_lat_lng(row.get("lat"), row.get("lng")):
            missing_coords += 1
            continue
        key = identity_key(row.get("source_dataset"), row.get("source_event_id"), row.get("date"))
        item = {
            "overlap_key": row.get("overlap_key"),
            "title": row.get("title"),
            "date": row.get("date"),
            "source_dataset": row.get("source_dataset"),
            "source_event_id": row.get("source_event_id"),
        }
        if key in approved_identities:
            already_in_approved.append(item)
        else:
            net_new.append(item)

    return {
        "export_event_count": len(events),
        "missing_coords": missing_coords,
        "already_in_approved_discovery": len(already_in_approved),
        "net_new_to_merge": len(net_new),
        "intake_counts": dict(intake_counts),
        "borough_counts": dict(borough_counts),
        "sample_net_new": net_new[:25],
        "sample_already_present": already_in_approved[:10],
    }


def build_readiness() -> dict[str, Any]:
    export = load_json_file(EXPORT_PATH, {})
    events = export.get("events") if isinstance(export, dict) else []
    if not isinstance(events, list):
        events = []

    approved_identities, approved_total, approved_categories = load_approved_identities()
    analysis = analyze_export_events(events, approved_identities)

    validation = gate_report(
        DATA_DIR / "supplemental_manual_approval_validation_report.json"
    )
    overlap = gate_report(OVERLAP_REPORT)
    export_gate = gate_report(EXPORT_REPORT)
    phase2e = load_json_file(PHASE2E_VERIFY, {})
    phase2e_blocked = int((phase2e.get("summary") or {}).get("blocked_from_promotion") or 0)

    validation_payload = load_json_file(VALIDATION_REPORT, {})
    pending = int(validation_payload.get("pending_count") or 0) if isinstance(validation_payload, dict) else -1

    errors: list[str] = []
    if export.get("production_feed") is True:
        errors.append("export production_feed=true")
    if pending != 0:
        errors.append(f"approval_queue_pending={pending}")
    if not validation.get("qa_pass"):
        errors.append("manual_approval_validation_not_pass")
    if not overlap.get("qa_pass"):
        errors.append("overlap_coord_conflict_audit_not_pass")
    if not export_gate.get("qa_pass"):
        errors.append("approved_export_report_not_pass")
    if phase2e_blocked != 0:
        errors.append(f"phase2e_blocked_from_promotion={phase2e_blocked}")
    if analysis["missing_coords"]:
        errors.append(f"export_missing_coords={analysis['missing_coords']}")

    try:
        from scripts.supplemental_discovery_merge import is_merge_authorized
    except ModuleNotFoundError:  # pragma: no cover
        from supplemental_discovery_merge import is_merge_authorized

    merge_authorized = is_merge_authorized()

    projected_approved_total = approved_total + analysis["net_new_to_merge"]
    qa_pass = not errors

    return {
        "artifact_type": "supplemental_discovery_merge_readiness_report",
        "generated_at_utc": utc_now_iso(),
        "phase": "m11_supplemental_discovery_merge_prep",
        "qa_pass": qa_pass,
        "merge_authorized": merge_authorized,
        "errors": errors,
        "baseline": {
            "approved_discovery_total": approved_total,
            "approved_discovery_categories": dict(approved_categories),
            "approved_manifest_path": repo_relative(APPROVED_MANIFEST),
        },
        "supplemental_export": {
            "path": repo_relative(EXPORT_PATH),
            "export_event_count": export.get("export_event_count"),
            **analysis,
        },
        "projected_after_merge": {
            "approved_discovery_total": projected_approved_total,
            "net_new_events": analysis["net_new_to_merge"],
            "duplicates_skipped": analysis["already_in_approved_discovery"],
        },
        "upstream_gates": {
            "manual_approval_validation": validation,
            "overlap_coord_conflict_audit": overlap,
            "approved_export_report": export_gate,
            "phase2e_dry_run_blocked": phase2e_blocked,
            "approval_queue_pending": pending,
        },
        "safety": {
            "public_map_modified": False,
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "promotion_allowed": False,
            "production_feed": False,
            "schema_v1_discovery_modified": False,
        },
        "next_required_step": (
            "Supplemental approved export merged into schema-v1-discovery approved pages. "
            "Deploy field-desk so feeds=main loads updated manifest on GitHub Pages."
        ),
        "long_island_note": "Long Island expansion is out of scope for M11; NYC five-borough supplemental only.",
    }


def main() -> int:
    report = build_readiness()
    save_json_file(READINESS_REPORT, report)

    proposal = {
        "artifact_type": "supplemental_discovery_merge_proposal_summary",
        "generated_at_utc": report["generated_at_utc"],
        "qa_pass": report["qa_pass"],
        "merge_authorized": report["merge_authorized"],
        "net_new_to_merge": report["supplemental_export"]["net_new_to_merge"],
        "projected_approved_total": report["projected_after_merge"]["approved_discovery_total"],
        "readiness_report": repo_relative(READINESS_REPORT),
    }
    save_json_file(PROPOSAL_SUMMARY, proposal)

    print(json.dumps({
        "qa_pass": report["qa_pass"],
        "net_new_to_merge": report["supplemental_export"]["net_new_to_merge"],
        "projected_approved_total": report["projected_after_merge"]["approved_discovery_total"],
        "readiness_report": repo_relative(READINESS_REPORT),
    }, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
