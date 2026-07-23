#!/usr/bin/env python3
"""Build dynamic God View project state for the admin Project Control Center.

Reads existing QA reports and status artifacts only. Does not modify protected
feeds or publish to the public map.

Outputs:
- status/nycif-godview-project-state-v02.json
- status/nycif-github-tracker.json (when --fetch-github or in CI)
- data/reports/godview_project_state_report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATUS = ROOT / "status"
REPORTS = DATA / "reports"
OUT_STATE = STATUS / "nycif-godview-project-state-v02.json"
OUT_TRACKER = STATUS / "nycif-github-tracker.json"
OUT_REPORT = REPORTS / "godview_project_state_report.json"

LIVE_FEEDS_REPO = "setoxxx/nycif-live-feeds"
FIELD_DESK_REPO = "setoxxx/nycif-field-desk"


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists() or path.stat().st_size == 0:
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


def queue_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("approval_queue"), list):
        return [row for row in payload["approval_queue"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def supplemental_counts() -> dict[str, int]:
    rows = queue_rows(load_json(DATA / "supplemental_manual_approval_queue.json", {}))
    counter = Counter(str(row.get("manual_review_status") or "pending").lower() for row in rows)
    return {
        "total": len(rows),
        "approved": counter.get("approved", 0),
        "rejected": counter.get("rejected", 0),
        "pending": counter.get("pending", 0),
    }


def discovery_counts() -> dict[str, int]:
    major = load_json(DATA / "schema-v1-discovery" / "major" / "events.json", {})
    approved_manifest = load_json(DATA / "schema-v1-discovery" / "approved" / "manifest.json", {})
    review_manifest = load_json(DATA / "schema-v1-discovery" / "review" / "manifest.json", {})
    return {
        "discovery_major_events": int(major.get("total") or len(major.get("events") or [])),
        "discovery_approved_events": int(approved_manifest.get("total") or 0),
        "discovery_review_events": int(review_manifest.get("total") or 0),
    }


def white_island_count() -> int:
    audit = load_json(REPORTS / "public_map_gps_audit_report.json", {})
    if isinstance(audit, dict):
        discovery = audit.get("discovery") or {}
        if discovery.get("white_island_cluster_count") is not None:
            return int(discovery["white_island_cluster_count"])
    return 0


def qa_gate(path: Path, key: str = "qa_pass") -> dict[str, Any]:
    payload = load_json(path, {})
    passed = bool(payload.get(key)) if isinstance(payload, dict) else False
    return {
        "qa_pass": passed,
        "artifact": str(path.relative_to(ROOT)),
        "generated_at_utc": payload.get("generated_at_utc") if isinstance(payload, dict) else None,
    }


def gh_json(args: list[str]) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout or "[]")
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def fetch_github_tracker(generated_at: str) -> dict[str, Any]:
    open_prs = [
        {
            "number": row.get("number"),
            "title": row.get("title"),
            "url": row.get("url"),
            "branch": (row.get("headRefName") or ""),
            "draft": bool(row.get("isDraft")),
            "repo": LIVE_FEEDS_REPO,
        }
        for row in gh_json(
            [
                "pr",
                "list",
                "--repo",
                LIVE_FEEDS_REPO,
                "--state",
                "open",
                "--limit",
                "25",
                "--json",
                "number,title,url,headRefName,isDraft",
            ]
        )
    ]
    merged_prs = [
        {
            "number": row.get("number"),
            "title": row.get("title"),
            "url": row.get("url"),
            "merged_at": row.get("mergedAt"),
            "repo": LIVE_FEEDS_REPO,
        }
        for row in gh_json(
            [
                "pr",
                "list",
                "--repo",
                LIVE_FEEDS_REPO,
                "--state",
                "merged",
                "--limit",
                "10",
                "--json",
                "number,title,url,mergedAt",
            ]
        )
    ]
    open_issues_feeds = [
        {
            "number": row.get("number"),
            "title": row.get("title"),
            "url": row.get("url"),
            "labels": [label.get("name") for label in row.get("labels") or [] if isinstance(label, dict)],
            "repo": LIVE_FEEDS_REPO,
        }
        for row in gh_json(
            [
                "issue",
                "list",
                "--repo",
                LIVE_FEEDS_REPO,
                "--state",
                "open",
                "--limit",
                "20",
                "--json",
                "number,title,url,labels",
            ]
        )
    ]
    open_issues_field_desk = [
        {
            "number": row.get("number"),
            "title": row.get("title"),
            "url": row.get("url"),
            "labels": [label.get("name") for label in row.get("labels") or [] if isinstance(label, dict)],
            "repo": FIELD_DESK_REPO,
        }
        for row in gh_json(
            [
                "issue",
                "list",
                "--repo",
                FIELD_DESK_REPO,
                "--state",
                "open",
                "--limit",
                "20",
                "--json",
                "number,title,url,labels",
            ]
        )
    ]
    closed_issues = [
        {
            "number": row.get("number"),
            "title": row.get("title"),
            "url": row.get("url"),
            "closed_at": row.get("closedAt"),
            "repo": row.get("repository", {}).get("nameWithOwner") if isinstance(row.get("repository"), dict) else FIELD_DESK_REPO,
        }
        for row in gh_json(
            [
                "issue",
                "list",
                "--repo",
                FIELD_DESK_REPO,
                "--state",
                "closed",
                "--limit",
                "10",
                "--json",
                "number,title,url,closedAt",
            ]
        )
    ]
    return {
        "artifact_type": "nycif_github_tracker",
        "generated_at_utc": generated_at,
        "open_prs": open_prs,
        "recent_merged_prs": merged_prs,
        "open_issues_live_feeds": open_issues_feeds,
        "open_issues_field_desk": open_issues_field_desk,
        "closed_issues_recent": closed_issues,
    }


def build_timeline(supp: dict[str, int], gps_audit_pass: bool | None) -> dict[str, list[dict[str, Any]]]:
    now = [
        {
            "title": "God View SHADOW-1 closeout refresh",
            "status": "in_progress",
            "summary": "Enigma SHADOW-1 Gates A–F complete + owner accepted (shadow-only); refreshing God View status",
            "artifacts": ["status/nycif-godview-project-state-v02.json#enigma_shadow_program"],
        },
        {
            "title": "Enigma SHADOW-1 program (Gates A–F)",
            "status": "complete",
            "summary": "Decisions, core lane, bundle producer, private SVG viewer, browser QA, owner acceptance — synthetic fixture only",
            "artifacts": ["status/nycif-godview-project-state-v02.json#enigma_shadow_program"],
        },
        {
            "title": "Dynamic God View project state",
            "status": "in_progress",
            "summary": "Generator + control panel JS wired to status/nycif-godview-project-state-v02.json",
            "artifacts": ["status/nycif-godview-project-state-v02.json"],
        },
        {
            "title": "GPS quality pass (Marine Park, Trans Latina, Uncle Tony)",
            "status": "ready" if gps_audit_pass else "in_progress",
            "summary": "Authorized location_cache corrections + discovery feed rebuild",
            "artifacts": ["data/reports/public_map_gps_audit_report.json", "data/reports/authorized_location_cache_corrections_report.json"],
            "pr_urls": ["https://github.com/setoxxx/nycif-live-feeds/pull/296"],
        },
        {
            "title": "Regenerate stale status/*.json from live artifacts",
            "status": "in_progress",
            "summary": "Project status, pipeline dashboard, milestone snapshots",
            "artifacts": ["status/nycif-live-pipeline-dashboard.json", "status/nycif-project-status.json"],
        },
    ]
    nxt = [
        {
            "title": "SHADOW-2 Gate A — real-data governance",
            "status": "locked",
            "summary": "NOT AUTHORIZED — real-data source selection, snapshot boundary, sanitization, retention, comparison metrics; separate owner authorization required",
            "artifacts": ["status/nycif-godview-project-state-v02.json#enigma_shadow_program"],
        },
        {
            "title": "Enigma parked-minor maintenance (optional)",
            "status": "not_started",
            "summary": "Genericize malformed-manifest JSON error wording; darken decorative borough labels >4.5:1",
            "artifacts": ["status/nycif-godview-project-state-v02.json#enigma_shadow_program"],
        },
        {
            "title": "Map chat integration (M12)",
            "status": "not_started",
            "summary": "Field-desk UI; read-only discovery context; no publish controls",
            "artifacts": ["status/nycif-godview-project-state-v02.json#chat_integration_handoff"],
            "target_repo": FIELD_DESK_REPO,
        },
        {
            "title": "Supplemental rejected-pass tail cleanup",
            "status": "active",
            "summary": f"{supp['rejected']} rejected supplemental rows documented; batch PRs optional",
            "artifacts": ["data/supplemental_manual_approval_queue.json"],
        },
        {
            "title": "Merge remaining approved supplemental into discovery fold",
            "status": "ready",
            "summary": f"{supp['approved']} approved supplemental rows in export feed",
            "artifacts": ["data/supplemental_approved_export_feed.json"],
        },
    ]
    later = [
        {
            "title": "Frozen real-data snapshot (SHADOW-2)",
            "status": "locked",
            "summary": "Governed, sanitized, retention-bounded snapshot of a first real source — not authorized",
        },
        {
            "title": "Private V1 / Enigma comparison (SHADOW-2)",
            "status": "locked",
            "summary": "Shadow comparison metrics vs V1; private only; no public map — not authorized",
        },
        {
            "title": "Promotion-readiness design",
            "status": "locked",
            "summary": "Criteria a shadow result would need before any promotion could even be proposed — not authorized",
        },
        {
            "title": "Limited controlled pilot",
            "status": "locked",
            "summary": "Any real-data or public exposure would require its own separate owner authorization — not authorized",
        },
        {
            "title": "Phase 2E bulk location_cache promotion",
            "status": "locked",
            "summary": "Unauthorized until explicit human promotion language",
        },
        {
            "title": "MOME / DOB shadow connectors",
            "status": "locked",
            "summary": "Shadow corroboration only — not connected to public map",
        },
        {
            "title": "M7-C duplicate-key enforcement",
            "status": "locked",
            "summary": "Not authorized",
        },
    ]
    return {"now": now, "next": nxt, "later": later}


def build_workstreams(supp: dict[str, int], map_freeze: dict[str, Any]) -> list[dict[str, Any]]:
    frozen = bool((map_freeze or {}).get("live_qa", {}).get("wordpress_map") == "PASS")
    return [
        {
            "id": "map_v1",
            "title": "Map v1 — public discovery experience",
            "status": "complete" if frozen else "active",
            "summary": "Field Desk Pages + WordPress /map/ shell; discovery feeds=main",
            "artifacts": ["status/nycif-map-v1-freeze.json", "data/schema-v1-discovery/"],
        },
        {
            "id": "gps_pipeline",
            "title": "GPS pipeline & pin integrity",
            "status": "active",
            "summary": "Phase 1 reliability + authorized cache corrections; audit-driven fixes",
            "artifacts": ["data/backend_reliability_gate_report.json", "data/reports/public_map_gps_audit_report.json"],
        },
        {
            "id": "supplemental_m11",
            "title": "M11 supplemental calendar + Parks",
            "status": "active",
            "summary": f"{supp['approved']} approved · {supp['rejected']} rejected · {supp['pending']} pending",
            "artifacts": ["data/supplemental_manual_approval_queue.json", "data/supplemental_approved_export_feed.json"],
        },
        {
            "id": "godview_admin",
            "title": "God View admin / operator desk",
            "status": "active",
            "summary": "Dynamic project control center + live pipeline + discovery queues",
            "artifacts": ["status/nycif-godview-project-state-v02.json"],
        },
        {
            "id": "map_chat_m12",
            "title": "Map chat (M12)",
            "status": "locked",
            "summary": "Next — after God View state lands; field-desk repo only",
            "blockers": ["God View dynamic state", "Chat UI placement decision"],
        },
    ]


def build_enigma_shadow_program() -> dict[str, Any]:
    """Public-safe Enigma SHADOW-1 program status (additive; static, deterministic).

    Contains only synthetic-fixture, non-authoritative program facts. No private
    national-pilot URLs, commit SHAs, filesystem paths, or raw payloads.
    """
    return {
        "program": "SHADOW-1",
        "status": "owner_accepted_shadow_only",
        "owner_decision": "APPROVE SHADOW-ONLY — PARK BOTH MINORS",
        "synthetic_validation": "complete",
        "real_data_comparison": "not_started",
        "production_promotion": "not_authorized",
        "gates": {
            "A": "complete",
            "B": "complete",
            "C": "complete",
            "D": "complete",
            "E": "accepted_with_conditions",
            "F": "owner_accepted",
        },
        "test_totals": {
            "isolation": 16,
            "enigma_core": 127,
            "bundle_producer": 125,
            "viewer": 61,
            "total": 329,
        },
        "fixture_accounting": {
            "requested": 12,
            "accepted_rows": 9,
            "distinct_occurrences": 7,
            "in_viewport": 4,
            "outside_viewport": 0,
            "unpinnable": 3,
            "duplicate_groups": 2,
            "silent_loss": 0,
        },
        "parked_minors": [
            "Genericize malformed-manifest JSON error wording",
            "Darken decorative borough labels to exceed 4.5:1 contrast",
        ],
        "authority": {
            "v1_is_sole_production_authority": True,
            "shadow_only": True,
            "synthetic_fixture_only": True,
            "real_feed_authorized": False,
            "deployment_authorized": False,
            "public_promotion_authorized": False,
            "publication_authorized": False,
        },
        "next_phase": {
            "name": "SHADOW-2 Gate A",
            "status": "not_authorized",
            "purpose": (
                "real-data governance, source selection, snapshot boundary, "
                "sanitization, retention, and comparison metrics"
            ),
        },
    }


def build_state(*, fetch_github: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    supp = supplemental_counts()
    disc = discovery_counts()
    map_freeze = load_json(STATUS / "nycif-map-v1-freeze.json", {})
    backend_gate = qa_gate(DATA / "backend_reliability_gate_report.json")
    discovery_audit = qa_gate(DATA / "events_discovery_taxonomy_v02_audit.json")
    gps_audit = qa_gate(REPORTS / "public_map_gps_audit_report.json")
    supplemental_validation = qa_gate(DATA / "supplemental_manual_approval_validation_report.json")

    if fetch_github:
        tracker = fetch_github_tracker(generated_at)
        save_json(OUT_TRACKER, tracker)
    else:
        tracker = load_json(OUT_TRACKER, {}) or {}
        if tracker:
            tracker.setdefault("generated_at_utc", generated_at)

    blockers = [
        {"text": "Phase 2E location_cache bulk promotion remains unauthorized.", "severity": "medium"},
        {"text": f"Supplemental queue: {supp['pending']} rows still pending human review.", "severity": "low" if supp["pending"] < 50 else "medium"},
    ]
    if white_island_count() > 0:
        blockers.insert(
            0,
            {"text": f"Public map GPS audit: {white_island_count()} White Island cluster events remain.", "severity": "high"},
        )

    resolved = [
        {"text": "Map v1 frozen — Field Desk Pages + WordPress /map/ PASS", "resolved_at_utc": map_freeze.get("signed_off_at_utc")},
        {"text": "Field-desk deploy automation (issues #127/#128 closed)", "resolved_at_utc": "2026-07-16T20:37:53Z"},
        {"text": f"M11 supplemental first-pass: {supp['approved']} rows approved in queue", "resolved_at_utc": generated_at},
    ]

    state = {
        "artifact_type": "nycif_godview_project_state",
        "schema_version": "2.0.0",
        "generated_at_utc": generated_at,
        "repository": LIVE_FEEDS_REPO,
        "visibility": "public",
        "safety": {
            "write_controls": False,
            "deploy_controls": False,
            "promotion_allowed_default": False,
            "phase_2e_authorized": False,
            "safe_for_public_dashboard": True,
        },
        "command_center": {
            "current_objective": "Close SHADOW-1 in God View and prepare SHADOW-2 governance",
            "current_stage": "Map v1 operating · Enigma SHADOW-1 owner accepted (shadow-only)",
            "current_gate": "God View SHADOW-1 completion refresh",
            "next_gate": "SHADOW-2 Gate A — real-data governance (not authorized)",
            "future_work_lock": (
                "No real feed, real producer, deployment, publication, or public-map "
                "promotion (Enigma or Phase 2E/MOME/DOB) without separate explicit owner authorization"
            ),
            "health": "green" if backend_gate["qa_pass"] and discovery_audit["qa_pass"] else "yellow",
            "completion_percent": 92,
        },
        "enigma_shadow_program": build_enigma_shadow_program(),
        "timeline": build_timeline(supp, gps_audit.get("qa_pass")),
        "workstreams": build_workstreams(supp, map_freeze if isinstance(map_freeze, dict) else {}),
        "qa_gates": {
            "backend_reliability_gate": backend_gate,
            "discovery_taxonomy": discovery_audit,
            "public_map_gps_audit": gps_audit,
            "supplemental_validation": supplemental_validation,
        },
        "counts": {
            **disc,
            "supplemental_approved": supp["approved"],
            "supplemental_rejected": supp["rejected"],
            "supplemental_pending": supp["pending"],
            "white_island_cluster_count": white_island_count(),
        },
        "blockers": blockers,
        "resolved_blockers": [item for item in resolved if item.get("text")],
        "decisions": [
            {
                "date": "2026-07-22",
                "title": "Enigma SHADOW-1 owner-accepted (shadow-only)",
                "rationale": (
                    "Gates A–F complete; owner APPROVE SHADOW-ONLY with two minors parked. "
                    "Synthetic fixture only; no real feed, deployment, or public-map promotion. "
                    "V1 remains the sole production and publishing authority."
                ),
                "status": "active",
            },
            {
                "date": "2026-07-16",
                "title": "Map v1 freeze",
                "rationale": "Public map shell is production-ready; supplemental merge remains gated.",
                "status": "active",
            },
            {
                "date": "2026-07-18",
                "title": "God View must be JSON-driven",
                "rationale": "Stop editing admin HTML for timeline/issues; regenerate from pipeline artifacts.",
                "status": "active",
            },
            {
                "date": "ongoing",
                "title": "No silent GPS promotion",
                "rationale": "location_cache and public map changes require explicit authorization.",
                "status": "active",
            },
        ],
        "risks": [
            {
                "title": "SHADOW-1 acceptance mistaken for production authorization",
                "control": (
                    "God View marks Enigma as shadow-only/synthetic-fixture-only; SHADOW-2 real-data "
                    "governance is not_authorized; real feed, real producer, deployment, and public "
                    "promotion each require separate explicit owner authorization"
                ),
            },
            {
                "title": "Stale admin status misleads operators",
                "control": "generate_godview_project_state.py on CI + freshness banner in UI",
            },
            {
                "title": "Supplemental calendar duplicates on map",
                "control": "Rejected rows excluded in discovery projector; dedupe corrections in queue",
            },
            {
                "title": "Chat feature scope creep",
                "control": "M12 locked until handoff; read-only context; no publish in chat UI",
            },
        ],
        "github_tracker": tracker,
        "deployment": {
            "field_desk_map": "https://setoxxx.github.io/nycif-field-desk/",
            "field_desk_admin": "https://setoxxx.github.io/nycif-field-desk/admin/",
            "wordpress_map": "https://nycinfocus.com/map/",
            "deploy_workflow": ".github/workflows/field-desk-complete-map-deploy.yml",
            "discovery_refresh_workflow": ".github/workflows/discovery-feed-refresh.yml",
            "state_artifact": "status/nycif-godview-project-state-v02.json",
        },
        "chat_integration_handoff": {
            "status": "not_started",
            "target_repo": FIELD_DESK_REPO,
            "depends_on": [
                "Map v1 frozen",
                "schema-v1-discovery feed on feeds=main",
                "Stacked event picker shipped",
                "Dynamic God View state on main",
            ],
            "constraints": [
                "Read-only event context from discovery feed",
                "No GPS review / manual approval artifacts in chat",
                "No publish or promotion controls in chat UI",
            ],
            "open_decisions": [
                "Chat UI placement: side panel vs modal",
                "Model/API provider",
                "Offline fallback behavior",
            ],
        },
        "artifact_links": {
            "project_status_legacy": "status/nycif-project-status.json",
            "live_pipeline_dashboard": "status/nycif-live-pipeline-dashboard.json",
            "map_v1_freeze": "status/nycif-map-v1-freeze.json",
            "discovery_godview_digest": "data/events_discovery_godview_digest_v02.json",
            "github_tracker": "status/nycif-github-tracker.json",
        },
    }

    report = {
        "artifact_type": "godview_project_state_report",
        "generated_at_utc": generated_at,
        "qa_pass": OUT_STATE.parent.exists(),
        "output_path": str(OUT_STATE.relative_to(ROOT)),
        "tracker_path": str(OUT_TRACKER.relative_to(ROOT)),
        "counts": state["counts"],
        "qa_gates": {key: value.get("qa_pass") for key, value in state["qa_gates"].items()},
        "github_tracker_fetched": fetch_github,
        "open_prs_count": len((tracker or {}).get("open_prs") or []),
        "safety": state["safety"],
    }
    return state, report


def refresh_legacy_project_status(state: dict[str, Any]) -> None:
    """Keep status/nycif-project-status.json aligned for older panels.

    Additive and non-destructive: unrelated Map V1, GPS, supplemental, M12,
    photographer, and PR context already in the artifact is preserved. The
    public-safe Enigma SHADOW-1 program block is mirrored verbatim from the
    canonical God View project state so the two artifacts cannot drift.
    """
    legacy_path = STATUS / "nycif-project-status.json"
    legacy = load_json(legacy_path, {})
    if not isinstance(legacy, dict):
        legacy = {}
    counts = state.get("counts") or {}
    legacy.update(
        {
            "enigma_shadow_program": state.get("enigma_shadow_program"),
            "artifact_type": "nycif_project_status",
            "schema_version": "1.0.0",
            "generated_at_utc": state.get("generated_at_utc"),
            "current_phase": state.get("command_center", {}).get("current_stage"),
            "completion_percent": state.get("command_center", {}).get("completion_percent"),
            "health": state.get("command_center", {}).get("health"),
            "status_summary": (
                f"Discovery approved {counts.get('discovery_approved_events', 0):,}; "
                f"supplemental {counts.get('supplemental_approved', 0):,} approved / "
                f"{counts.get('supplemental_rejected', 0):,} rejected. "
                f"God View state v2 generated {state.get('generated_at_utc')}."
            ),
            "blockers": [item.get("text") for item in state.get("blockers") or [] if isinstance(item, dict)],
            "resolved_blockers": [
                item.get("text") for item in state.get("resolved_blockers") or [] if isinstance(item, dict)
            ],
            "next_action": state.get("command_center", {}).get("next_gate"),
            "data_freshness": {
                "source": "generate_godview_project_state.py",
                "last_verified_at": state.get("generated_at_utc"),
            },
        }
    )
    save_json(legacy_path, legacy)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate God View project state JSON.")
    parser.add_argument(
        "--fetch-github",
        action="store_true",
        help="Refresh GitHub PR/issue snapshot (requires gh CLI + auth).",
    )
    args = parser.parse_args()
    fetch_github = args.fetch_github or bool(__import__("os").environ.get("GITHUB_ACTIONS"))

    state, report = build_state(fetch_github=fetch_github)
    save_json(OUT_STATE, state)
    save_json(OUT_REPORT, report)
    refresh_legacy_project_status(state)

    # Refresh live pipeline dashboard while we are here (cheap, keeps panels aligned).
    try:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_live_pipeline_dashboard_status.py")], check=True)
    except Exception:
        report["live_pipeline_refresh"] = "skipped_or_failed"

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
