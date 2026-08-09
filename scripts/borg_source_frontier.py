#!/usr/bin/env python3
"""Build a deterministic BORG public-source acquisition frontier.

The planner does not perform network requests. It converts information gaps and
registered source state into ordered acquisition actions while respecting source
rights, tier, freshness, sensitivity, and retry state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT = "nycif.borg-source-frontier.v1"
ALLOWED_ACTIONS = {"FETCH", "RETRY", "REVIEW", "NO_ACTION"}

PRIORITY_WEIGHT = {
    "PUBLIC_SAFETY_OR_CIVIC_TIME_SENSITIVITY": 700,
    "KNOWN_COVERAGE_GAP": 600,
    "REQUIRED_TIER_A_SOURCE_STALE_OR_FAILED": 550,
    "HIGH_PUBLIC_INTEREST": 500,
    "OFFICIAL_CORROBORATION_NEEDED": 400,
    "NEW_SCHEMA_OR_SOURCE_DISCOVERED": 300,
    "LONG_HORIZON_ENRICHMENT": 100,
}
TIER_WEIGHT = {"A": 80, "B": 60, "C": 40, "D": 10}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _action(source: dict[str, Any], now: datetime) -> tuple[str, list[str]]:
    reasons: list[str] = []
    rights = source.get("rights") or {}
    if not rights.get("retrieval_allowed"):
        return "REVIEW", ["RETRIEVAL_NOT_APPROVED"]
    if source.get("authentication_mode") in {"UNKNOWN", "PRIVATE", "UNRESOLVED"}:
        return "REVIEW", ["AUTHENTICATION_UNRESOLVED"]
    if source.get("network_scope") in {"PRIVATE", "LOOPBACK", "LINK_LOCAL"}:
        return "REVIEW", ["NON_PUBLIC_NETWORK_TARGET"]
    if source.get("health") == "FAILED":
        return "RETRY", ["SOURCE_FAILED"]

    last_success = _parse_time(source.get("last_success_at"))
    freshness_hours = float(source.get("freshness_sla_hours", 24))
    if last_success is None:
        reasons.append("NEVER_FETCHED")
        return "FETCH", reasons
    age_hours = max(0.0, (now - last_success).total_seconds() / 3600.0)
    if age_hours > freshness_hours:
        reasons.append("STALE")
        return "FETCH", reasons
    return "NO_ACTION", ["FRESH"]


def build_frontier(*, gaps: list[dict[str, Any]], sources: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    for gap in gaps:
        gap_id = str(gap["gap_id"])
        priority_class = gap.get("priority_class", "LONG_HORIZON_ENRICHMENT")
        candidate_ids = set(gap.get("candidate_source_ids") or [])
        for source in sources:
            source_id = str(source["source_id"])
            if candidate_ids and source_id not in candidate_ids:
                continue
            action, reasons = _action(source, now)
            score = PRIORITY_WEIGHT.get(priority_class, 0) + TIER_WEIGHT.get(source.get("source_tier"), 0)
            if action == "RETRY":
                score += 30
            elif action == "FETCH":
                score += 20
            elif action == "REVIEW":
                score -= 100
            material = f"{gap_id}|{source_id}|{action}|{source.get('canonical_url','')}"
            actions.append({
                "frontier_item_id": hashlib.sha256(material.encode()).hexdigest(),
                "gap_id": gap_id,
                "source_id": source_id,
                "source_tier": source.get("source_tier"),
                "canonical_url": source.get("canonical_url"),
                "action": action,
                "priority_score": score,
                "reasons": reasons,
                "rights_state": source.get("rights"),
                "parser_version": source.get("parser_version"),
            })

    actions.sort(key=lambda row: (-row["priority_score"], row["gap_id"], row["source_id"]))
    counts = {action: sum(1 for row in actions if row["action"] == action) for action in sorted(ALLOWED_ACTIONS)}
    return {
        "contract": CONTRACT,
        "generated_at": now.isoformat(),
        "gap_count": len(gaps),
        "source_count": len(sources),
        "frontier_item_count": len(actions),
        "action_accounting": counts,
        "items": actions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gaps", required=True)
    parser.add_argument("--sources", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_frontier(
        gaps=json.loads(Path(args.gaps).read_text()),
        sources=json.loads(Path(args.sources).read_text()),
        now=datetime.now(timezone.utc),
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
