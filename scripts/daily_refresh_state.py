#!/usr/bin/env python3
"""Private, repository-scoped state for the atomic daily refresh transaction."""

from __future__ import annotations

import json
import os
import re
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_NAME = ".runtime"
FAILURE_NAME = "nycif-daily-failure.json"
PREVIOUS_NAME = "nycif-previous-public-feed"
MAX_STATE_BYTES = 16 * 1024
_SHA_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REQUIRED_FAILURE_KEYS = {
    "schema_version",
    "generated_at_utc",
    "stage",
    "command_id",
    "exit_code",
    "exception_class",
    "error_summary",
    "public_feed_commit_occurred",
}
_OPTIONAL_FAILURE_KEYS = {"shell_line"}


@contextmanager
def runtime_directory_fd() -> Iterator[int]:
    """Hold a no-follow descriptor for the private repository runtime directory."""
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    root_fd = os.open(ROOT, directory_flags)
    try:
        try:
            os.mkdir(RUNTIME_NAME, mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        runtime_fd = os.open(RUNTIME_NAME, directory_flags, dir_fd=root_fd)
    finally:
        os.close(root_fd)

    try:
        metadata = os.fstat(runtime_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError("refresh runtime state is not a directory")
        if metadata.st_uid != os.geteuid():
            raise RuntimeError("refresh runtime directory has an unexpected owner")
        os.fchmod(runtime_fd, 0o700)
        yield runtime_fd
    finally:
        os.close(runtime_fd)


def validate_failure_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Reject semantically malformed failure state instead of coercing it."""
    if not isinstance(payload, dict):
        raise ValueError("failure payload must be an object")

    keys = set(payload)
    missing = _REQUIRED_FAILURE_KEYS - keys
    extras = keys - _REQUIRED_FAILURE_KEYS - _OPTIONAL_FAILURE_KEYS
    if missing or extras:
        raise ValueError(f"failure payload keys are invalid: missing={sorted(missing)}, extras={sorted(extras)}")
    if payload["schema_version"] != "1.0.0":
        raise ValueError("failure payload schema_version must be 1.0.0")
    if not isinstance(payload["generated_at_utc"], str) or not _UTC_PATTERN.fullmatch(
        payload["generated_at_utc"]
    ):
        raise ValueError("failure payload generated_at_utc must be second-precision UTC")
    for key in ("stage", "command_id"):
        value = payload[key]
        if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
            raise ValueError(f"failure payload field {key!r} must be a safe identifier")
    if payload["stage"] == "unknown_stage":
        raise ValueError("failure payload stage must not be unknown_stage")
    exception_class = payload["exception_class"]
    if not isinstance(exception_class, str) or not _IDENTIFIER_PATTERN.fullmatch(exception_class):
        raise ValueError("failure payload exception_class must be a safe identifier")
    summary = payload["error_summary"]
    if not isinstance(summary, str) or not 1 <= len(summary) <= 2048:
        raise ValueError("failure payload error_summary must contain 1 to 2048 characters")
    try:
        summary.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("failure payload error_summary must be valid UTF-8 text") from exc

    exit_code = payload.get("exit_code")
    if type(exit_code) is not int or exit_code == 0 or not -(2**31) <= exit_code < 2**31:
        raise ValueError("failure payload exit_code must be a nonzero signed 32-bit integer")
    if type(payload["public_feed_commit_occurred"]) is not bool:
        raise ValueError("failure payload public_feed_commit_occurred must be boolean")

    shell_line = payload.get("shell_line")
    if shell_line is not None and (
        not isinstance(shell_line, str)
        or not (shell_line == "not_available" or (shell_line.isdecimal() and len(shell_line) <= 20))
    ):
        raise ValueError("failure payload shell_line must be a bounded non-empty string")

    return dict(payload)


def _existing_leaf_is_regular(runtime_fd: int, name: str) -> bool:
    try:
        metadata = os.stat(name, dir_fd=runtime_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError(f"refresh runtime leaf {name!r} must be a regular file")
    return True


def _atomic_write(name: str, content: bytes) -> None:
    if len(content) > MAX_STATE_BYTES:
        raise ValueError("refresh runtime state exceeds the size limit")

    with runtime_directory_fd() as runtime_fd:
        _existing_leaf_is_regular(runtime_fd, name)
        temporary_name = f".{name}.{secrets.token_hex(12)}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptor = os.open(temporary_name, flags, 0o600, dir_fd=runtime_fd)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            _existing_leaf_is_regular(runtime_fd, name)
            os.replace(
                temporary_name,
                name,
                src_dir_fd=runtime_fd,
                dst_dir_fd=runtime_fd,
            )
            os.fsync(runtime_fd)
        finally:
            try:
                os.unlink(temporary_name, dir_fd=runtime_fd)
            except FileNotFoundError:
                pass


def _read(name: str) -> bytes | None:
    with runtime_directory_fd() as runtime_fd:
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        try:
            descriptor = os.open(name, flags, dir_fd=runtime_fd)
        except FileNotFoundError:
            return None
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(f"refresh runtime leaf {name!r} must be a regular file")
            if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
                raise RuntimeError(f"refresh runtime leaf {name!r} is not private")
            content = handle.read(MAX_STATE_BYTES + 1)
        if len(content) > MAX_STATE_BYTES:
            raise ValueError("refresh runtime state exceeds the size limit")
        return content


def atomic_write_failure(payload: dict[str, Any]) -> None:
    validated = validate_failure_payload(payload)
    _atomic_write(
        FAILURE_NAME,
        (json.dumps(validated, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def read_failure() -> dict[str, Any] | None:
    content = _read(FAILURE_NAME)
    if content is None:
        return None
    try:
        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate failure payload key: {key}")
                result[key] = value
            return result

        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("failure context is not valid UTF-8 JSON") from exc
    return validate_failure_payload(payload)


def atomic_write_previous_commit(commit_sha: str) -> None:
    normalized = commit_sha.strip().lower()
    if not _SHA_PATTERN.fullmatch(normalized):
        raise ValueError("previous public feed commit must be a full lowercase SHA")
    _atomic_write(PREVIOUS_NAME, f"{normalized}\n".encode("ascii"))


def read_previous_commit() -> str | None:
    content = _read(PREVIOUS_NAME)
    if content is None:
        return None
    try:
        commit_sha = content.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("previous public feed commit is not ASCII") from exc
    if not _SHA_PATTERN.fullmatch(commit_sha):
        raise ValueError("previous public feed commit is malformed")
    return commit_sha


def clear_runtime_state() -> None:
    with runtime_directory_fd() as runtime_fd:
        for name in (FAILURE_NAME, PREVIOUS_NAME):
            try:
                metadata = os.stat(name, dir_fd=runtime_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(f"refresh runtime leaf {name!r} must be a regular file")
            os.unlink(name, dir_fd=runtime_fd)
        os.fsync(runtime_fd)


def failure_exists() -> bool:
    return read_failure() is not None


def clear_failure() -> None:
    _clear_leaf(FAILURE_NAME)


def clear_previous_commit() -> None:
    _clear_leaf(PREVIOUS_NAME)


def _clear_leaf(name: str) -> None:
    with runtime_directory_fd() as runtime_fd:
        try:
            metadata = os.stat(name, dir_fd=runtime_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"refresh runtime leaf {name!r} must be a regular file")
        os.unlink(name, dir_fd=runtime_fd)
        os.fsync(runtime_fd)
