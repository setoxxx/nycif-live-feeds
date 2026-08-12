#!/usr/bin/env python3
"""Shared fail-closed path handling for BORG command-line tools.

CLI file arguments are treated as untrusted input. Every path is syntax-checked,
resolved against the current workspace, and required to remain inside that
workspace after canonicalization, including symlink resolution. Filesystem I/O
is kept behind this module so CLI callers never use user-controlled path values
at filesystem sinks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SAFE_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


def _workspace_root() -> Path:
    return Path.cwd().resolve()


def _validated_relative_path(raw: str) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("CLI file path is required")
    if not _SAFE_RELATIVE_PATH.fullmatch(value):
        raise ValueError("CLI file path contains unsupported characters")

    candidate = Path(value)
    if candidate.is_absolute():
        raise ValueError("CLI file path must be relative to the workspace")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("CLI file path cannot contain empty, dot, or parent segments")
    return candidate


def resolve_workspace_file(raw: str, *, must_exist: bool) -> Path:
    """Return a canonical workspace-confined file path.

    Inputs must exist as regular files. Output parents must already exist and
    outputs may not name directories. Paths that escape through symlinks fail.
    """

    candidate = _validated_relative_path(raw)
    root = _workspace_root()
    try:
        resolved = (root / candidate).resolve(strict=must_exist)
        resolved.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ValueError("CLI file path must resolve inside the workspace") from exc

    if must_exist:
        if not resolved.is_file():
            raise ValueError("CLI input path must name an existing regular file")
        return resolved

    try:
        parent = resolved.parent.resolve(strict=True)
        parent.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ValueError("CLI output parent must exist inside the workspace") from exc

    if resolved.exists() and not resolved.is_file():
        raise ValueError("CLI output path must name a regular file")
    return resolved


def workspace_relative(path: Path) -> str:
    """Return a stable workspace-relative representation for provenance."""

    root = _workspace_root()
    return path.resolve().relative_to(root).as_posix()


def read_workspace_json(raw: str) -> Any:
    """Read JSON only after the requested CLI path passes workspace confinement."""

    path = resolve_workspace_file(raw, must_exist=True)
    return json.loads(path.read_text())


def read_workspace_json_with_relative(raw: str) -> tuple[Any, str]:
    """Read confined JSON and return its stable workspace-relative provenance name."""

    path = resolve_workspace_file(raw, must_exist=True)
    return json.loads(path.read_text()), workspace_relative(path)


def write_workspace_json(raw: str, payload: Any) -> None:
    """Write formatted JSON only after the requested CLI path passes confinement."""

    path = resolve_workspace_file(raw, must_exist=False)
    path.write_text(json.dumps(payload, indent=2) + "\n")
