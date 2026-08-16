#!/usr/bin/env python3
"""Private, repository-scoped state for the atomic daily refresh transaction."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / ".runtime"
FAILURE_JSON = RUNTIME_DIR / "nycif-daily-failure.json"


def prepare_runtime_dir() -> Path:
    """Create the private runtime directory without following a directory symlink."""
    if RUNTIME_DIR.is_symlink():
        raise RuntimeError("refresh runtime directory must not be a symlink")
    RUNTIME_DIR.mkdir(mode=0o700, parents=False, exist_ok=True)
    resolved_root = ROOT.resolve()
    resolved_runtime = RUNTIME_DIR.resolve(strict=True)
    try:
        resolved_runtime.relative_to(resolved_root)
    except ValueError as exc:
        raise RuntimeError("refresh runtime directory escaped the repository") from exc
    if not resolved_runtime.is_dir():
        raise RuntimeError("refresh runtime path is not a directory")
    resolved_runtime.chmod(0o700)
    return resolved_runtime


def atomic_write_failure(payload: dict[str, Any]) -> None:
    """Atomically replace the fixed failure artifact with private permissions."""
    runtime_dir = prepare_runtime_dir()
    if FAILURE_JSON.is_symlink():
        raise RuntimeError("refresh failure artifact must not be a symlink")

    descriptor, temporary_name = tempfile.mkstemp(
        dir=runtime_dir,
        prefix=".nycif-daily-failure-",
        suffix=".json.tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if FAILURE_JSON.is_symlink():
            raise RuntimeError("refresh failure artifact must not be a symlink")
        os.replace(temporary_path, FAILURE_JSON)
    finally:
        temporary_path.unlink(missing_ok=True)
