"""Fail-closed, read-only access to NYCIF artifacts for SHADOW-2.

The reader performs no network calls and exposes no write methods. Malformed or
unreadable artifacts raise ``SnapshotReadError`` so reconciliation cannot hide
silent loss.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class SnapshotReadError(RuntimeError):
    """Raised when a required audit artifact cannot be read safely."""


@dataclass(frozen=True, slots=True)
class SnapshotRecord:
    record: dict[str, Any]
    artifact_path: str
    collection: str
    record_index: int


class ReadOnlySnapshot:
    """Read-only view over approved, review, lineage, and raw artifacts."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        approved_pages_root: Path | None = Path("data/schema-v1-discovery/approved/pages"),
        review_pages_root: Path | None = Path("data/schema-v1-discovery/review/pages"),
        lineage_registry_path: Path | None = Path("data/source_lineage_registry_v01.json"),
        require_page_manifests: bool = True,
    ) -> None:
        self.repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
        self.approved_pages_root = self._resolve_optional(approved_pages_root)
        self.review_pages_root = self._resolve_optional(review_pages_root)
        self.lineage_registry_path = self._resolve_optional(lineage_registry_path)
        self.require_page_manifests = require_page_manifests

    def _resolve_optional(self, path: Path | None) -> Path | None:
        if path is None:
            return None
        candidate = path if path.is_absolute() else self.repo_root / path
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError as exc:
            raise SnapshotReadError(f"artifact escapes repository root: {path}") from exc
        return resolved

    @staticmethod
    def _load_json(path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError as exc:
            raise SnapshotReadError(f"required artifact missing: {path}") from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SnapshotReadError(f"unable to read JSON artifact {path}: {exc}") from exc

    def read_lineage_registry(self) -> dict[str, Any]:
        if self.lineage_registry_path is None:
            raise SnapshotReadError("lineage registry is disabled")
        payload = self._load_json(self.lineage_registry_path)
        if not isinstance(payload, dict):
            raise SnapshotReadError("source-lineage registry must be a JSON object")
        if payload.get("artifact_type") != "source_lineage_registry_v01":
            raise SnapshotReadError("unexpected source-lineage registry artifact_type")
        entries = payload.get("entries")
        if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
            raise SnapshotReadError("source-lineage registry entries must be an object list")
        return copy.deepcopy(payload)

    def _manifest_page_plan(self, root: Path, collection: str) -> tuple[list[tuple[Path, int | None]], int | None]:
        if not self.require_page_manifests:
            page_files = sorted(root.glob("page-*.json"))
            return [(page_file, None) for page_file in page_files], None

        manifest_path = root.parent / "manifest.json"
        manifest = self._load_json(manifest_path)
        if not isinstance(manifest, dict):
            raise SnapshotReadError(f"page manifest must be a JSON object: {manifest_path}")
        if manifest.get("layer") != collection:
            raise SnapshotReadError(f"page manifest layer mismatch for {collection}: {manifest_path}")
        pages = manifest.get("pages")
        if not isinstance(pages, list) or not all(isinstance(item, dict) for item in pages):
            raise SnapshotReadError(f"page manifest pages must be an object list: {manifest_path}")
        if manifest.get("page_count") != len(pages):
            raise SnapshotReadError(f"page manifest page_count mismatch: {manifest_path}")
        expected_total = manifest.get("total")
        if not isinstance(expected_total, int) or expected_total < 0:
            raise SnapshotReadError(f"page manifest total must be a nonnegative integer: {manifest_path}")

        plan: list[tuple[Path, int | None]] = []
        expected_names: set[str] = set()
        for item in pages:
            page_name = item.get("page")
            expected_count = item.get("count")
            if not isinstance(page_name, str) or not re.fullmatch(r"page-\d+\.json", page_name):
                raise SnapshotReadError(f"invalid page name in manifest: {manifest_path}")
            if not isinstance(expected_count, int) or expected_count < 0:
                raise SnapshotReadError(f"invalid page count for {page_name}: {manifest_path}")
            if page_name in expected_names:
                raise SnapshotReadError(f"duplicate page name in manifest: {page_name}")
            expected_names.add(page_name)
            plan.append((root / page_name, expected_count))

        actual_names = {path.name for path in root.glob("page-*.json")}
        if actual_names != expected_names:
            missing = sorted(expected_names - actual_names)
            extra = sorted(actual_names - expected_names)
            raise SnapshotReadError(
                f"page manifest/file mismatch in {root}; missing={missing}, extra={extra}"
            )
        return plan, expected_total

    def _read_page_directory(self, root: Path | None, collection: str) -> Iterator[SnapshotRecord]:
        if root is None:
            return
        if not root.is_dir():
            raise SnapshotReadError(f"required page directory missing: {root}")
        page_plan, expected_total = self._manifest_page_plan(root, collection)
        if not page_plan:
            raise SnapshotReadError(f"no page shards found in required directory: {root}")

        observed_total = 0
        for page_file, expected_count in page_plan:
            payload = self._load_json(page_file)
            if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
                raise SnapshotReadError(f"page shard must contain an events list: {page_file}")
            events = payload["events"]
            if expected_count is not None and len(events) != expected_count:
                raise SnapshotReadError(
                    f"page count mismatch for {page_file}: expected {expected_count}, observed {len(events)}"
                )
            observed_total += len(events)
            for index, event in enumerate(events):
                if not isinstance(event, dict):
                    raise SnapshotReadError(f"non-object event at {page_file} index {index}")
                yield SnapshotRecord(
                    record=copy.deepcopy(event),
                    artifact_path=str(page_file.relative_to(self.repo_root)),
                    collection=collection,
                    record_index=index,
                )
        if expected_total is not None and observed_total != expected_total:
            raise SnapshotReadError(
                f"manifest total mismatch for {collection}: expected {expected_total}, observed {observed_total}"
            )

    def read_approved_events(self) -> Iterator[SnapshotRecord]:
        yield from self._read_page_directory(self.approved_pages_root, "approved")

    def read_review_events(self) -> Iterator[SnapshotRecord]:
        yield from self._read_page_directory(self.review_pages_root, "review")

    def raw_snapshot_paths(self) -> tuple[Path, ...]:
        registry = self.read_lineage_registry()
        paths: list[Path] = []
        for entry in registry["entries"]:
            if entry.get("repository") != "setoxxx/nycif-live-feeds":
                continue
            if entry.get("raw_intake_countable") is not True:
                continue
            source_path = entry.get("path_or_source")
            if not isinstance(source_path, str) or not source_path.strip():
                raise SnapshotReadError(f"countable raw entry lacks path: {entry.get('id')}")
            resolved = self._resolve_optional(Path(source_path))
            if resolved is None:
                raise SnapshotReadError(f"countable raw entry resolved to no path: {entry.get('id')}")
            paths.append(resolved)
        if not paths:
            raise SnapshotReadError("source-lineage registry names no countable local raw snapshots")
        return tuple(sorted(set(paths)))

    @staticmethod
    def _records_from_json_payload(payload: Any, path: Path) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            list_keys = [key for key in ("events", "rows", "items", "data", "results") if isinstance(payload.get(key), list)]
            if len(list_keys) == 1:
                records = payload[list_keys[0]]
            elif len(list_keys) > 1:
                raise SnapshotReadError(f"ambiguous record collections in raw snapshot: {path}")
            else:
                records = [payload]
        else:
            raise SnapshotReadError(f"raw snapshot must contain an object or list: {path}")
        if not all(isinstance(record, dict) for record in records):
            raise SnapshotReadError(f"raw snapshot contains non-object records: {path}")
        return records

    def _read_raw_path(self, path: Path) -> Iterator[SnapshotRecord]:
        if not path.is_file():
            raise SnapshotReadError(f"required raw snapshot missing: {path}")
        suffix = path.suffix.lower()
        relative = str(path.relative_to(self.repo_root))
        if suffix == ".json":
            records = self._records_from_json_payload(self._load_json(path), path)
            for index, record in enumerate(records):
                yield SnapshotRecord(copy.deepcopy(record), relative, "raw", index)
            return
        if suffix not in {".jsonl", ".ndjson"}:
            raise SnapshotReadError(f"unsupported raw snapshot format: {path}")
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise SnapshotReadError(f"malformed JSONL at {path}:{line_number}") from exc
                    if not isinstance(record, dict):
                        raise SnapshotReadError(f"non-object JSONL record at {path}:{line_number}")
                    yield SnapshotRecord(copy.deepcopy(record), relative, "raw", line_number - 1)
        except (OSError, UnicodeDecodeError) as exc:
            raise SnapshotReadError(f"unable to read raw snapshot {path}: {exc}") from exc

    def read_raw_snapshots(self) -> Iterator[SnapshotRecord]:
        for path in self.raw_snapshot_paths():
            yield from self._read_raw_path(path)

    def event_counts(self) -> dict[str, int]:
        return {
            "approved": sum(1 for _ in self.read_approved_events()) if self.approved_pages_root is not None else 0,
            "review": sum(1 for _ in self.read_review_events()) if self.review_pages_root is not None else 0,
            "raw": sum(1 for _ in self.read_raw_snapshots()) if self.lineage_registry_path is not None else 0,
        }
