#!/usr/bin/env python3
"""Run one daily-refresh command with structured, sanitized failure reporting."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import deque
from datetime import datetime, timezone
from typing import Sequence

try:
    from scripts import daily_refresh_state as state
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import daily_refresh_state as state
SUMMARY_LIMIT = 1600

_SECRET_PATTERNS = (
    re.compile(r"(?i)([?&](?:access_token|api[_-]?key|auth|authorization|key|sig|signature|token)=)[^&\s]+"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\b((?:api[_-]?key|authorization|password|secret|token)\s*[:=]\s*)\S+"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sanitize_text(value: str) -> str:
    """Redact common secret shapes while preserving log line structure."""
    cleaned = "".join(
        character
        for character in value
        if character in "\n\t"
        or (ord(character) >= 32 and not 0xD800 <= ord(character) <= 0xDFFF)
    )
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            cleaned = pattern.sub(r"\1[REDACTED]", cleaned)
        else:
            cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def sanitize_summary(value: str, *, limit: int = SUMMARY_LIMIT) -> str:
    """Return a bounded, single-purpose error summary with common secrets redacted."""
    cleaned = sanitize_text(value).strip()
    if not cleaned:
        return "No stderr or exception text was captured. See the GitHub Actions job log."
    if len(cleaned) > limit:
        cleaned = cleaned[-limit:]
        cleaned = f"[truncated] {cleaned}"
    return cleaned


def failure_payload(
    *,
    stage: str,
    command_id: str,
    exit_code: int,
    exception_class: str,
    error_summary: str,
    public_feed_commit_occurred: bool = False,
    shell_line: str | int | None = None,
) -> dict:
    normalized_stage = stage.strip() or "platform_or_uninstrumented_failure"
    if normalized_stage == "unknown_stage":
        normalized_stage = "platform_or_uninstrumented_failure"
    payload = {
        "schema_version": "1.0.0",
        "generated_at_utc": utc_now(),
        "stage": normalized_stage,
        "command_id": command_id.strip() or "unspecified_command",
        "exit_code": int(exit_code),
        "exception_class": exception_class.strip() or "ProcessFailure",
        "error_summary": sanitize_summary(error_summary),
        "public_feed_commit_occurred": bool(public_feed_commit_occurred),
    }
    if shell_line is not None:
        payload["shell_line"] = str(shell_line)
    return payload


def run_command(
    command: Sequence[str],
    *,
    stage: str,
    command_id: str,
) -> int:
    if not command:
        payload = failure_payload(
            stage=stage,
            command_id=command_id,
            exit_code=2,
            exception_class="ArgumentError",
            error_summary="No executable command was supplied.",
        )
        state.atomic_write_failure(payload)
        return 2

    tail: deque[str] = deque(maxlen=80)
    try:
        process = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        stdout = process.stdout
        if stdout is None:
            process.kill()
            raise RuntimeError("captured process stdout was unavailable")
        for line in stdout:
            safe_line = sanitize_text(line)
            print(safe_line, end="", flush=True)
            tail.append(safe_line)
        return_code = process.wait()
    except Exception as exc:  # pragma: no cover - platform launch failures are environment-specific.
        payload = failure_payload(
            stage=stage,
            command_id=command_id,
            exit_code=127,
            exception_class=exc.__class__.__name__,
            error_summary=str(exc),
        )
        state.atomic_write_failure(payload)
        print(payload["error_summary"], file=sys.stderr)
        return 127

    if return_code != 0:
        payload = failure_payload(
            stage=stage,
            command_id=command_id,
            exit_code=return_code,
            exception_class="ProcessExitError",
            error_summary="".join(tail),
        )
        state.atomic_write_failure(payload)
    return return_code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--command-id", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_command(
        args.command,
        stage=args.stage,
        command_id=args.command_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
