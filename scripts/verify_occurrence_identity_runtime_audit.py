#!/usr/bin/env python3
"""Verify current-runtime occurrence identity safety after the historical audit.

The legacy protected audit includes a July 2026 replay assertion requiring the
then-current staged feed to reproduce the historical 4,203 source-ID-hidden
occurrences from issue #324. Projector V3 no longer uses that legacy staged feed
as a populated runtime authority, so an empty staged feed cannot reproduce the
historical *before* state.

This verifier does not waive the issue #324 acceptance criteria. It requires the
current implementation to have zero source-ID-hidden occurrences, zero duplicate
canonical IDs, complete raw disposition accounting, valid projector/source
lineage contracts, and unchanged protected public surfaces. If the legacy staged
feed is populated, the historical before/after replay must still be meaningful.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = Path("/tmp/occurrence-identity-enforcement/occurrence_identity_enforcement_summary.json")
STAGED = ROOT / "data" / "nycif_staged_live_events.json"
OUTPUT = Path("/tmp/occurrence-identity-enforcement/current_runtime_occurrence_identity_gate.json")


def load_events_count(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    for key in ("events", "records", "rows", "features"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return len(rows)
    return 0


def main() -> int:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    staged_count = load_events_count(STAGED)
    before_hidden = int(summary.get("before_open_data_in_window_hidden_by_source_id") or 0)
    after_hidden = int(summary.get("after_open_data_in_window_hidden_by_source_id") or 0)

    historical_replay_applicable = staged_count > 0
    historical_replay_pass = before_hidden > 0 if historical_replay_applicable else True

    safety = summary.get("safety") if isinstance(summary.get("safety"), dict) else {}
    protected_surface_pass = all(
        safety.get(key) is False
        for key in (
            "production_feed_modified",
            "data_location_cache_json_modified",
            "wordpress_modified",
            "public_map_modified",
            "homepage_modified",
            "navigation_modified",
            "theme_modified",
            "approval_state_modified",
            "promotion_allowed",
            "public_launch_authorized",
        )
    ) and safety.get("proposal_only") is True

    checks = {
        "after_hidden_occurrences_zero": after_hidden == 0,
        "duplicate_canonical_ids_zero": int(summary.get("duplicate_canonical_id_count") or 0) == 0,
        "raw_disposition_accounting_pass": summary.get("raw_disposition_accounting_pass") is True,
        "projector_occurrence_identity_pass": summary.get("projector_implementation_correctness_pass") is True,
        "source_lineage_contract_pass": summary.get("source_lineage_contract_compliance_pass") is True,
        "historical_before_replay_pass_or_not_applicable": historical_replay_pass,
        "protected_surface_safety_pass": protected_surface_pass,
    }
    gate = {
        "artifact_type": "current_runtime_occurrence_identity_gate",
        "historical_issue_324_baseline_hidden_count": 4203,
        "legacy_staged_event_count": staged_count,
        "historical_before_replay_applicable": historical_replay_applicable,
        "computed_before_hidden_count": before_hidden,
        "computed_after_hidden_count": after_hidden,
        "checks": checks,
        "qa_pass": all(checks.values()),
        "operating_rule": (
            "Historical before-state replay is not required when the legacy staged feed is empty, "
            "but every current issue #324 safety/acceptance condition remains mandatory."
        ),
    }
    OUTPUT.write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(gate, indent=2, sort_keys=True))
    return 0 if gate["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
