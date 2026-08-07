#!/usr/bin/env python3
"""Package the reader-safe public artifact into a versioned shadow release.

This script is intentionally deployment-neutral: it writes only to a caller-supplied
filesystem root. It does not publish, configure hosting, DNS, credentials, or the
production /map/ route.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_public_runtime_artifacts import PublicArtifactError, build as build_public_artifact

SCHEMA = "nycif-public-shadow-release-v1"
HEALTH_SCHEMA = "nycif-public-health-v1"
CURRENT_SCHEMA = "nycif-public-current-pointer-v1"

ALLOWED_HEALTH_KEYS = {
    "release_sha",
    "generated_at",
    "schema_version",
    "event_count",
    "page_count",
    "major_event_count",
    "release_status",
}
DENIED_HEALTH_TOKENS = (
    "source",
    "provider",
    "pipeline",
    "review",
    "confidence",
    "ranking",
    "evidence",
    "sonar",
    "security",
    "private",
    "error",
    "failure",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_release_sha(value: str) -> str:
    value = str(value or "").strip().lower()
    if len(value) < 7 or len(value) > 64 or any(c not in "0123456789abcdef" for c in value):
        raise PublicArtifactError("release SHA must be 7-64 lowercase hexadecimal characters")
    return value


def validate_health(payload: dict[str, Any]) -> None:
    extra = set(payload) - ALLOWED_HEALTH_KEYS
    missing = ALLOWED_HEALTH_KEYS - set(payload)
    if extra or missing:
        raise PublicArtifactError(f"public health schema mismatch extra={sorted(extra)} missing={sorted(missing)}")
    encoded = json.dumps(payload, sort_keys=True).lower()
    for token in DENIED_HEALTH_TOKENS:
        if token in encoded:
            raise PublicArtifactError(f"public health denylist token present: {token}")


def relative_artifact_inventory(root: Path) -> list[dict[str, Any]]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    return [
        {
            "path": str(path.relative_to(root)).replace(os.sep, "/"),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in files
    ]


def atomic_replace_dir(staged: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.with_name(f".{destination.name}.previous-{uuid.uuid4().hex}")
    had_existing = destination.exists()
    if had_existing:
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except Exception:
        if had_existing and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def build_shadow_release(
    manifest: Path,
    major: Path,
    shadow_root: Path,
    release_sha: str,
    rollback_release_sha: str | None = None,
) -> dict[str, Any]:
    release_sha = validate_release_sha(release_sha)
    rollback = validate_release_sha(rollback_release_sha) if rollback_release_sha else None
    if rollback == release_sha:
        raise PublicArtifactError("rollback release must differ from current release")

    shadow_root.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="nycif-shadow-release-", dir=str(shadow_root)))
    try:
        release_stage = tmp / release_sha
        artifact_stage = tmp / "artifact"
        result = build_public_artifact(manifest, major, artifact_stage, release_sha)
        shutil.move(str(artifact_stage), str(release_stage))

        generated_at = datetime.now(timezone.utc).isoformat()
        health = {
            "release_sha": release_sha,
            "generated_at": generated_at,
            "schema_version": HEALTH_SCHEMA,
            "event_count": int(result["public_events"]),
            "page_count": int(result["page_count"]),
            "major_event_count": int(result["major_events"]),
            "release_status": "shadow_ready",
        }
        validate_health(health)
        write_json(release_stage / "health/public-summary.json", health)

        inventory = relative_artifact_inventory(release_stage)
        release_manifest = {
            "schema_version": SCHEMA,
            "release_sha": release_sha,
            "generated_at": generated_at,
            "rollback_release_sha": rollback,
            "file_count": len(inventory),
            "total_size_bytes": sum(item["size_bytes"] for item in inventory),
            "artifacts": inventory,
            "publication_authorized": False,
        }
        write_json(release_stage / "PUBLIC_DATA_SHADOW_RELEASE_MANIFEST.json", release_manifest)

        final_release = shadow_root / "releases" / release_sha
        final_release.parent.mkdir(parents=True, exist_ok=True)
        atomic_replace_dir(release_stage, final_release)

        current_stage = tmp / "current"
        current_stage.mkdir(parents=True, exist_ok=True)
        current_pointer = {
            "schema_version": CURRENT_SCHEMA,
            "release_sha": release_sha,
            "release_path": f"../releases/{release_sha}/",
            "rollback_release_sha": rollback,
            "generated_at": generated_at,
            "atomic_pointer": True,
            "publication_authorized": False,
        }
        write_json(current_stage / "release.json", current_pointer)
        atomic_replace_dir(current_stage, shadow_root / "current")

        return {
            "qa_pass": True,
            "release_sha": release_sha,
            "rollback_release_sha": rollback,
            "release_root": str(final_release),
            "current_pointer": str(shadow_root / "current/release.json"),
            "file_count": release_manifest["file_count"],
            "total_size_bytes": release_manifest["total_size_bytes"],
            "event_count": health["event_count"],
            "page_count": health["page_count"],
            "major_event_count": health["major_event_count"],
            "publication_authorized": False,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--major", type=Path, required=True)
    parser.add_argument("--shadow-root", type=Path, required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--rollback-release-sha")
    args = parser.parse_args()
    try:
        result = build_shadow_release(
            args.manifest,
            args.major,
            args.shadow_root,
            args.release_sha,
            args.rollback_release_sha,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (PublicArtifactError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"qa_pass": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
