#!/usr/bin/env python3
"""Write a structured BLOCKED daily-data health artifact after a failed refresh.

The workflow invokes this only after resetting the working tree to current main,
so partial generated feeds cannot be published. Failure details are sanitized
before they enter a committed status artifact.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts import daily_refresh_state as state
    from scripts.run_daily_refresh_stage import sanitize_summary
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import daily_refresh_state as state
    from run_daily_refresh_stage import sanitize_summary

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "status" / "nycif-daily-data-health.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_stage(value: str) -> str:
    stage = value.strip() or "platform_or_uninstrumented_failure"
    if stage == "unknown_stage":
        return "platform_or_uninstrumented_failure"
    return stage


def load_failure_context() -> dict[str, Any]:
    path = state.FAILURE_JSON
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "stage": "platform_or_uninstrumented_failure",
            "command_id": "malformed_failure_context",
            "exit_code": 1,
            "exception_class": "MalformedFailureContext",
            "error_summary": "The structured failure context was missing or malformed. Review the workflow log.",
            "public_feed_commit_occurred": False,
        }
    return payload if isinstance(payload, dict) else {}

def build_payload(
    *,
    stage: str,
    command_id: str,
    exit_code: int,
    shell_line: str,
    exception_class: str,
    error_summary: str,
    previous_commit: str,
    public_feed_commit_occurred: bool,
) -> dict:
    normalized_stage = normalize_stage(stage)
    normalized_command = command_id.strip() or "workflow_platform_or_uninstrumented"
    normalized_exception = exception_class.strip() or "ProcessFailure"
    safe_summary = sanitize_summary(error_summary)
    message = (
        f"Daily production refresh failed at stage '{normalized_stage}' "
        f"(command '{normalized_command}', exit {int(exit_code)})."
    )
    if public_feed_commit_occurred:
        rollback_strategy = (
            "A public-feed commit was reported. Stop automation and review the candidate commit "
            "against previous_public_feed_commit before any rollback or republish."
        )
    else:
        rollback_strategy = (
            "No feed rollback was required because the failed transaction did not commit public feeds."
        )

    return {
        "artifact_type": "nycif_daily_data_health",
        "schema_version": "1.3.0",
        "generated_at_utc": utc_now(),
        "company_focus": "News Desk live-data completeness, freshness, and duplicate safety",
        "status": "BLOCKED",
        "release_ready": False,
        "daily_refresh_required": True,
        "sources": [],
        "derived_artifacts": [],
        "pipeline": {
            "strict_reconciliation": False,
            "canonical_identity_clean": False,
            "cross_source_dedupe_clean": False,
            "shared_cems_dedupe_clean": False,
        },
        "blockers": [
            {
                "code": "daily_refresh_stage_failed",
                "severity": "critical",
                "message": message,
                "artifact": ".github/workflows/discovery-feed-refresh.yml",
                "stage": normalized_stage,
                "command_id": normalized_command,
                "exit_code": int(exit_code),
                "shell_line": str(shell_line or "not_available"),
                "exception_class": normalized_exception,
                "error_summary": safe_summary,
                "public_feed_commit_occurred": bool(public_feed_commit_occurred),
            }
        ],
        "operating_rule": "Do not commit or publish a refreshed public feed unless status is READY.",
        "rollback_rule": "The previous serving commit remains authoritative until a later refresh is READY.",
        "rollback": {
            "previous_public_feed_commit": previous_commit,
            "public_feed_commit_occurred": bool(public_feed_commit_occurred),
            "strategy": rollback_strategy,
        },
        "enigma": {
            "production_authority": False,
            "mode": "shadow_only",
            "note": "V1 remains the sole production authority.",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="platform_or_uninstrumented_failure")
    parser.add_argument("--command-id", default="workflow_platform_or_uninstrumented")
    parser.add_argument("--exit-code", type=int, default=1)
    parser.add_argument("--line", default="not_available")
    parser.add_argument("--exception-class", default="ProcessFailure")
    parser.add_argument("--error-summary", default="No safe error summary was captured. Review the workflow log.")
    parser.add_argument("--previous-commit", required=True)
    parser.add_argument("--public-feed-commit-occurred", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = load_failure_context()
    payload = build_payload(
        stage=str(context.get("stage", args.stage)),
        command_id=str(context.get("command_id", args.command_id)),
        exit_code=int(context.get("exit_code", args.exit_code)),
        shell_line=str(context.get("shell_line", context.get("line", args.line))),
        exception_class=str(context.get("exception_class", args.exception_class)),
        error_summary=str(context.get("error_summary", args.error_summary)),
        previous_commit=args.previous_commit,
        public_feed_commit_occurred=bool(
            context.get("public_feed_commit_occurred", args.public_feed_commit_occurred)
        ),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
