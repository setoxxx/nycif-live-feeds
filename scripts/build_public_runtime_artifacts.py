#!/usr/bin/env python3
"""Build reader-safe public map artifacts from NYCIF semantic discovery feeds.

This integrated version intentionally delegates location truth to
``pin_integrity.evaluate_map_eligibility`` and occurrence truth to
``occurrence_identity_contract``. It must not become a second implementation of
either authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from occurrence_identity_contract import (
    identity_precision,
    occurrence_key_v2,
    occurrence_key_v2_set,
)
from pin_integrity import evaluate_map_eligibility

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/schema-v1-discovery/approved/manifest.json"
DEFAULT_MAJOR = ROOT / "data/schema-v1-discovery/major/events.json"
DEFAULT_OUTPUT = ROOT / "public-data"
SCHEMA = "nycif-public-runtime-v1"
PUBLIC_MAJOR_FEED = "major/events.json"
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")

DENIED_KEYS = {
    "source",
    "source_url",
    "source_dataset",
    "source_event_id",
    "source_system",
    "ingestion_url",
    "confidence",
    "confidence_score",
    "priority_score",
    "ranking_score",
    "reviewer",
    "reviewer_id",
    "review_notes",
    "private_notes",
    "debug",
    "debug_info",
    "evidence",
    "evidence_bundle",
    "resolver_evidence",
    "location_evidence",
    "exact_pin_eligible",
    "validation_state",
    "source_provenance",
    "geocoder_provenance",
    "internal_prompt",
    "prompt",
}
DENIED_FRAGMENTS = (
    "raw.githubusercontent.com/setoxxx/",
    "github.com/setoxxx/",
    "setoxxx.github.io/nycif-field-desk",
    "localhost",
    "127.0.0.1",
)


class PublicArtifactError(RuntimeError):
    pass


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PublicArtifactError(f"cannot read JSON {path}: {exc}") from exc


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def text(value: Any, limit: int = 2000) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return value[:limit]


def nested_nycif(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("nycif") if isinstance(row.get("nycif"), dict) else {}


def event_role(row: dict[str, Any]) -> str:
    nested = nested_nycif(row)
    return str(row.get("event_role") or nested.get("event_role") or "").strip().lower()


def certified_claim(row: dict[str, Any]) -> bool:
    nested = nested_nycif(row)
    value = row.get("certified_pin")
    if value is None:
        value = nested.get("certified_pin")
    return value is True


def candidate_public_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        source_rows = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
        source_rows = [item for item in payload["events"] if isinstance(item, dict)]
    else:
        raise PublicArtifactError("unsupported event payload")
    return [
        row
        for row in source_rows
        if not row.get("parent_event_id") and event_role(row) == "public_event"
    ]


def validate_occurrence_identity(rows: list[dict[str, Any]], *, scope: str) -> None:
    ambiguous = [row for row in rows if identity_precision(row) == "AMBIGUOUS"]
    if ambiguous:
        raise PublicArtifactError(
            f"ambiguous public occurrence identity in {scope}: {len(ambiguous)} row(s)"
        )
    canonical = occurrence_key_v2_set(rows)
    if len(canonical) != len(rows):
        raise PublicArtifactError(f"duplicate canonical occurrence identity in {scope}")


def public_event_id(row: dict[str, Any]) -> str:
    if identity_precision(row) == "AMBIGUOUS":
        raise PublicArtifactError("public event occurrence identity is ambiguous")
    dataset, source_event_id, source_start = occurrence_key_v2(row)
    identity = "\x1f".join((dataset, source_event_id, source_start))
    return "evt_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def shared_location_decision(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return shared semantic decision and exact-publication agreement.

    The semantic authority decides eligibility. Public exact publication also
    requires the upstream semantic ``certified_pin`` claim to agree, preventing
    a downstream builder from silently minting certification on its own.
    """
    decision = evaluate_map_eligibility(row)
    exact = (
        decision.get("map_eligibility") == "MAP_READY"
        and decision.get("exact_pin_eligible") is True
        and certified_claim(row)
    )
    return decision, exact


def project_place(row: dict[str, Any], *, state: str, exact: bool) -> dict[str, Any]:
    place = row.get("place") if isinstance(row.get("place"), dict) else {}
    if state == "GENERAL_AREA":
        keys = (
            "general_area_label",
            "neighborhood",
            "borough",
            "locality",
            "city",
            "admin_area",
            "state",
            "country_code",
            "country",
        )
    else:
        keys = (
            "location",
            "neighborhood",
            "locality",
            "city",
            "admin_area",
            "state",
            "country_code",
            "country",
            "borough",
        )
    out: dict[str, Any] = {}
    for key in keys:
        value = place.get(key) if place.get(key) is not None else row.get(key)
        normalized = text(value)
        if normalized is not None:
            out[key] = normalized
    if exact:
        address = text(place.get("address") if place.get("address") is not None else row.get("address"))
        if address is not None:
            out["address"] = address
    return out


def project_event(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("parent_event_id") or event_role(row) != "public_event":
        return None
    title = text(row.get("title") or row.get("name"), 1000)
    if not title:
        return None

    decision, exact = shared_location_decision(row)
    state = str(decision.get("map_eligibility") or "LIST_ONLY").upper()
    if state not in {"MAP_READY", "GENERAL_AREA", "LIST_ONLY", "REVIEW_REQUIRED"}:
        state = "LIST_ONLY"
    if state == "MAP_READY" and not exact:
        state = "REVIEW_REQUIRED"

    out: dict[str, Any] = {
        "id": public_event_id(row),
        "title": title,
        "event_role": "public_event",
        "map_eligibility_state": state,
        "certified_pin": exact,
    }

    for key in (
        "category",
        "event_type",
        "section",
        "description",
        "event_date",
        "start_date_time",
        "end_date_time",
        "timezone",
        "public_url",
        "url",
    ):
        normalized = text(row.get(key))
        if normalized is not None:
            out[key] = normalized

    for key in ("interests", "tags"):
        if isinstance(row.get(key), list):
            out[key] = [v for v in (text(item, 200) for item in row[key]) if v]

    when_source = row.get("when") if isinstance(row.get("when"), dict) else {}
    when: dict[str, Any] = {}
    for key in ("event_date", "start_date_time", "end_date_time", "timezone"):
        value = when_source.get(key) if when_source.get(key) is not None else row.get(key)
        normalized = text(value)
        if normalized is not None:
            when[key] = normalized
    if when:
        out["when"] = when

    place = project_place(row, state=state, exact=exact)
    if place:
        out["place"] = place

    if exact:
        lat = decision.get("normalized_lat")
        lng = decision.get("normalized_lng")
        if lat is None or lng is None:
            raise PublicArtifactError(f"shared MAP_READY decision missing normalized coordinates: {out['id']}")
        out["latitude"] = float(lat)
        out["longitude"] = float(lng)

    return out


def project(payload: Any, *, scope: str) -> list[dict[str, Any]]:
    rows = candidate_public_rows(payload)
    validate_occurrence_identity(rows, scope=scope)
    projected = [value for value in (project_event(row) for row in rows) if value is not None]
    ensure_unique_public_ids(projected, scope=scope)
    return projected


def public_day(event: dict[str, Any]) -> str | None:
    when = event.get("when") if isinstance(event.get("when"), dict) else {}
    for value in (
        event.get("event_date"),
        when.get("event_date"),
        event.get("start_date_time"),
        when.get("start_date_time"),
    ):
        candidate = text(value, 100)
        if not candidate:
            continue
        match = DATE_PREFIX.match(candidate)
        if match:
            return match.group(1)
    return None


def page_date_bounds(events: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    days = [day for day in (public_day(event) for event in events) if day]
    return (min(days), max(days)) if days else (None, None)


def ensure_unique_public_ids(events: list[dict[str, Any]], *, scope: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for event in events:
        event_id = str(event.get("id") or "")
        if event_id in seen:
            duplicates.add(event_id)
        seen.add(event_id)
    if duplicates:
        raise PublicArtifactError(f"duplicate public event id in {scope}: {sorted(duplicates)[:3]}")


def scan(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in DENIED_KEYS:
                raise PublicArtifactError(f"denied output key: {key}")
            scan(child)
    elif isinstance(value, list):
        for child in value:
            scan(child)
    elif isinstance(value, str):
        low = value.lower()
        for fragment in DENIED_FRAGMENTS:
            if fragment.lower() in low:
                raise PublicArtifactError(f"denied internal URL fragment: {fragment}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _publish_staged(staged: Path, output: Path) -> None:
    backup = output.with_name(f".{output.name}.previous-{uuid.uuid4().hex}")
    had_output = output.exists()
    if had_output:
        os.replace(output, backup)
    try:
        os.replace(staged, output)
    except Exception:
        if had_output and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


def build(manifest_path: Path, major_path: Path, output: Path, release_sha: str) -> dict[str, Any]:
    if not release_sha:
        raise PublicArtifactError("release SHA required")
    manifest = load(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
        raise PublicArtifactError("manifest missing pages[]")

    generated = datetime.now(timezone.utc).isoformat()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_parent = Path(tempfile.mkdtemp(prefix="nycif-public-", dir=str(output.parent)))
    staged = temp_parent / output.name
    total = 0
    page_meta: list[dict[str, Any]] = []
    all_page_ids: set[str] = set()

    try:
        for item in manifest["pages"]:
            name = text(item.get("page"), 200) if isinstance(item, dict) else None
            if not name or Path(name).name != name or not name.endswith(".json"):
                raise PublicArtifactError(f"unsafe page name: {name}")
            public_rows = project(load(manifest_path.parent / "pages" / name), scope=name)
            for event in public_rows:
                if event["id"] in all_page_ids:
                    raise PublicArtifactError(f"duplicate public event id across pages: {event['id']}")
                all_page_ids.add(event["id"])

            payload = {
                "schema_version": SCHEMA,
                "release_sha": release_sha,
                "generated_at": generated,
                "events": public_rows,
            }
            scan(payload)
            write(staged / "events/pages" / name, payload)
            earliest_date, latest_date = page_date_bounds(public_rows)
            total += len(public_rows)
            page_meta.append(
                {
                    "page": name,
                    "count": len(public_rows),
                    "earliest_date": earliest_date,
                    "latest_date": latest_date,
                }
            )

        public_manifest = {
            "schema_version": SCHEMA,
            "layer": "public-reader-safe",
            "release_sha": release_sha,
            "generated_at": generated,
            "major_feed": PUBLIC_MAJOR_FEED,
            "total": total,
            "page_count": len(page_meta),
            "pages": page_meta,
        }
        scan(public_manifest)
        write(staged / "events/manifest.json", public_manifest)

        major_events = project(load(major_path), scope="major")
        major = {
            "schema_version": SCHEMA,
            "release_sha": release_sha,
            "generated_at": generated,
            "events": major_events,
        }
        scan(major)
        write(staged / "events/major/events.json", major)

        files = sorted(path for path in staged.rglob("*") if path.is_file())
        artifact_manifest = {
            "schema_version": SCHEMA,
            "release_sha": release_sha,
            "generated_at": generated,
            "artifacts": [
                {"path": str(path.relative_to(staged)).replace(os.sep, "/"), "sha256": sha(path)}
                for path in files
            ],
        }
        scan(artifact_manifest)
        write(staged / "artifact-manifest.json", artifact_manifest)

        for path in staged.rglob("*.json"):
            scan(load(path))

        _publish_staged(staged, output)
        return {
            "qa_pass": True,
            "release_sha": release_sha,
            "public_events": total,
            "major_events": len(major_events),
            "page_count": len(page_meta),
            "output_root": str(output),
        }
    finally:
        shutil.rmtree(temp_parent, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--major", type=Path, default=DEFAULT_MAJOR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--release-sha", default=os.environ.get("GITHUB_SHA", ""))
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.manifest, args.major, args.output, args.release_sha), indent=2, sort_keys=True))
        return 0
    except PublicArtifactError as exc:
        print(json.dumps({"qa_pass": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
