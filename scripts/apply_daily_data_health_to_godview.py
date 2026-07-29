#!/usr/bin/env python3
"""Apply the daily data health contract to God View project state.

Runs after the canonical God View generator so the News Desk live-data gate is
the visible company objective without duplicating the large project-state
builder.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "status"
HEALTH = STATUS / "nycif-daily-data-health.json"
STATE = STATUS / "nycif-godview-project-state-v02.json"
LEGACY = STATUS / "nycif-project-status.json"


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected object: {path}")
    return payload


def save(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def source_summary(health: dict[str, Any]) -> str:
    sources = health.get("sources") or []
    fresh = sum(1 for source in sources if source.get("fresh"))
    total = len(sources)
    return f"{fresh}/{total} official sources live and fresh; {len(health.get('blockers') or [])} blockers"


def blocker_messages(health: dict[str, Any]) -> list[str]:
    messages = []
    for item in health.get("blockers") or []:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or item.get("code") or "Daily data health blocker")
        artifact = str(item.get("artifact") or "").strip()
        messages.append(f"{message} [{artifact}]" if artifact else message)
    return messages


def main() -> int:
    health = load(HEALTH)
    previous_commit = os.environ.get("PREVIOUS_PUBLIC_FEED_SHA", "").strip()
    if previous_commit:
        health["rollback"] = {
            "previous_public_feed_commit": previous_commit,
            "strategy": "Failed runs do not commit; revert the READY refresh commit to restore this prior commit.",
        }
        save(HEALTH, health)

    state = load(STATE)
    ready = bool(health.get("release_ready")) and health.get("status") == "READY"
    summary = source_summary(health)
    messages = blocker_messages(health)

    command = state.setdefault("command_center", {})
    command.update(
        {
            "current_objective": "Keep the News Desk live-data pipeline complete, fresh, and duplicate-safe every day",
            "current_stage": f"Daily production data health: {health.get('status', 'UNKNOWN')}",
            "current_gate": "All official sources refreshed + strict reconciliation + duplicate gates",
            "next_gate": (
                "Verify the next scheduled daily refresh remains READY"
                if ready
                else "Resolve every daily-data blocker before any public-feed commit"
            ),
            "future_work_lock": "No unrelated platform expansion may displace the live-data reliability gate.",
            "health": "green" if ready else "red",
            "completion_percent": 100 if ready else 65,
        }
    )

    state["daily_data_health"] = health
    qa_gates = state.setdefault("qa_gates", {})
    qa_gates["daily_data_health"] = {
        "qa_pass": ready,
        "artifact": "status/nycif-daily-data-health.json",
        "generated_at_utc": health.get("generated_at_utc"),
        "status": health.get("status"),
    }

    existing_workstreams = [
        item for item in state.get("workstreams") or []
        if not (isinstance(item, dict) and item.get("id") == "daily_live_data")
    ]
    daily_workstream = {
        "id": "daily_live_data",
        "title": "News Desk daily live-data production",
        "status": "complete" if ready else "blocked",
        "summary": summary,
        "blockers": messages,
        "artifacts": [
            "status/nycif-daily-data-health.json",
            "data/events_discovery_reconciliation_v02.json",
            "data/reports/discovery_approved_dedupe_report.json",
            "data/schema-v1-discovery/shared-cems-occurrence-dedupe-summary.json",
        ],
    }
    state["workstreams"] = [daily_workstream, *existing_workstreams]

    existing_blockers = [
        item for item in state.get("blockers") or []
        if not (isinstance(item, dict) and str(item.get("source") or "") == "daily_data_health")
    ]
    health_blockers = [
        {"text": message, "severity": "high", "source": "daily_data_health"}
        for message in messages
    ]
    state["blockers"] = [*health_blockers, *existing_blockers]

    timeline = state.setdefault("timeline", {})
    now = [
        item for item in timeline.get("now") or []
        if not (isinstance(item, dict) and item.get("title") == "Daily News Desk data health")
    ]
    now.insert(
        0,
        {
            "title": "Daily News Desk data health",
            "status": "complete" if ready else "blocked",
            "summary": summary,
            "artifacts": ["status/nycif-daily-data-health.json"],
        },
    )
    timeline["now"] = now

    save(STATE, state)

    legacy = load(LEGACY)
    legacy.update(
        {
            "generated_at_utc": state.get("generated_at_utc"),
            "current_phase": command.get("current_stage"),
            "next_action": command.get("next_gate"),
            "health": command.get("health"),
            "completion_percent": command.get("completion_percent"),
            "daily_data_health": health,
            "status_summary": f"News Desk daily data health {health.get('status')}: {summary}.",
            "blockers": messages,
        }
    )
    save(LEGACY, legacy)

    print(json.dumps({"status": health.get("status"), "ready": ready, "summary": summary}, indent=2))
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
