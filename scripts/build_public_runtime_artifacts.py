#!/usr/bin/env python3
"""Build reader-safe public map artifacts from private NYCIF discovery feeds."""
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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/schema-v1-discovery/approved/manifest.json"
DEFAULT_MAJOR = ROOT / "data/schema-v1-discovery/major/events.json"
DEFAULT_OUTPUT = ROOT / "public-data"
SCHEMA = "nycif-public-runtime-v1"
PUBLIC_MAJOR_FEED = "major/events.json"

EXACT_TIERS = {
    "exact_source_coordinate",
    "exact_address",
    "exact_intersection",
    "certified_street_segment",
    "certified_facility",
    "tier_1_certified_segment",
    "tier_2_geosearch_midpoint",
}

DENIED_KEYS = {
    "source", "source_url", "source_dataset", "source_event_id", "source_system",
    "ingestion_url", "confidence", "confidence_score", "priority_score", "ranking_score",
    "reviewer", "reviewer_id", "review_notes", "private_notes", "debug", "debug_info",
    "evidence", "evidence_bundle", "resolver_evidence", "location_evidence",
    "exact_pin_eligible", "validation_state", "source_provenance", "geocoder_provenance",
    "internal_prompt", "prompt",
}
DENIED_FRAGMENTS = (
    "raw.githubusercontent.com/setoxxx/", "github.com/setoxxx/",
    "setoxxx.github.io/nycif-field-desk", "localhost", "127.0.0.1"
)
DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


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


def b(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def text(value: Any, limit: int = 2000) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    return value[:limit]


def nested_nycif(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("nycif") if isinstance(row.get("nycif"), dict) else {}


def location_evidence(row: dict[str, Any]) -> dict[str, Any]:
    evidence = row.get("location_evidence")
    if isinstance(evidence, dict):
        return evidence
    nested = nested_nycif(row).get("location_evidence")
    return nested if isinstance(nested, dict) else {}


def semantic_state(row: dict[str, Any]) -> str:
    nested = nested_nycif(row)
    evidence = location_evidence(row)
    value = (
        row.get("map_eligibility_state")
        or nested.get("map_eligibility_state")
        or evidence.get("map_eligibility_state")
    )
    return str(value or "").strip().upper()


def certified(row: dict[str, Any]) -> bool:
    nested = nested_nycif(row)
    evidence = location_evidence(row)
    value = row.get("certified_pin")
    if value is None:
        value = nested.get("certified_pin")
    if value is None:
        value = evidence.get("certified_pin")
    return b(value)


def role(row: dict[str, Any]) -> str:
    nested = nested_nycif(row)
    return str(row.get("event_role") or nested.get("event_role") or "").strip().lower()


def exact_evidence_authorized(row: dict[str, Any]) -> bool:
    """Re-check the semantic exact-pin evidence contract at the public boundary.

    The final integrated branch should replace this compatibility copy with the
    shared ``pin_integrity.evaluate_map_eligibility`` authority from PR #379.
    """
    if semantic_state(row) != "MAP_READY" or not certified(row):
        return False
    evidence = location_evidence(row)
    if not evidence:
        return False
    tier = str(evidence.get("tier") or evidence.get("location_tier") or "").strip().lower()
    validation_state = str(evidence.get("validation_state") or "").strip().lower()
    explicit_eligible = evidence.get("exact_pin_eligible") is True
    provenance = (
        evidence.get("source_provenance")
        or evidence.get("geocoder_provenance")
        or evidence.get("source")
        or evidence.get("provider")
    )
    return (
        tier in EXACT_TIERS
        and validation_state == "validated"
        and explicit_eligible
        and bool(provenance)
    )


def finite(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(row[key])
        except Exception:
            continue
        if value == value and abs(value) != float("inf"):
            return value
    return None


def occurrence_start(row: dict[str, Any]) -> str:
    when = row.get("when") if isinstance(row.get("when"), dict) else {}
    for value in (
        row.get("start_date_time"),
        when.get("start_date_time"),
        row.get("event_date"),
        when.get("event_date"),
    ):
        normalized = text(value, 100)
        if normalized:
            return normalized
    return "identity_ambiguous"


def public_event_id(row: dict[str, Any]) -> str:
    """Return an opaque, occurrence-sensitive public ID without source leakage."""
    source = row.get("source") if isinstance(row.get("source"), dict) else {}
    dataset = text(row.get("source_dataset") or source.get("dataset"), 300)
    source_event_id = text(row.get("source_event_id") or source.get("source_event_id"), 500)
    start = occurrence_start(row)
    if start == "identity_ambiguous":
        raise PublicArtifactError("public event occurrence identity is ambiguous")
    raw_id = text(row.get("id") or row.get("event_id"), 1000)
    if dataset and source_event_id:
        identity = f"v2|{dataset}|{source_event_id}|{start}"
    elif raw_id:
        identity = f"id|{raw_id}|{start}"
    else:
        raise PublicArtifactError("public event missing stable identity")
    return "evt_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def project_place(row: dict[str, Any], *, state: str, exact: bool) -> dict[str, Any]:
    source = row.get("place") if isinstance(row.get("place"), dict) else {}
    if state == "GENERAL_AREA":
        keys = (
            "general_area_label", "neighborhood", "borough", "locality", "city",
            "admin_area", "state", "country_code", "country",
        )
    else:
        keys = (
            "location", "neighborhood", "locality", "city", "admin_area", "state",
            "country_code", "country", "borough",
        )
    out: dict[str, Any] = {}
    for key in keys:
        value = source.get(key) if source.get(key) is not None else row.get(key)
        value = text(value)
        if value is not None:
            out[key] = value
    if exact:
        address = text(source.get("address") if source.get("address") is not None else row.get("address"))
        if address is not None:
            out["address"] = address
    return out


def project_event(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("parent_event_id") or role(row) != "public_event":
        return None
    title = text(row.get("title") or row.get("name"), 1000)
    if not title:
        return None

    exact = exact_evidence_authorized(row)
    state = semantic_state(row)
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
        "category", "event_type", "section", "description", "event_date",
        "start_date_time", "end_date_time", "timezone", "public_url", "url",
    ):
        value = text(row.get(key))
        if value is not None:
            out[key] = value
    for key in ("interests", "tags"):
        if isinstance(row.get(key), list):
            out[key] = [v for v in (text(item, 200) for item in row[key]) if v]

    when_source = row.get("when") if isinstance(row.get("when"), dict) else {}
    when: dict[str, Any] = {}
    for key in ("event_date", "start_date_time", "end_date_time", "timezone"):
        value = text(when_source.get(key) if when_source.get(key) is not None else row.get(key))
        if value is not None:
            when[key] = value
    if when:
        out["when"] = when

    place = project_place(row, state=state, exact=exact)
    if place:
        out["place"] = place

    if exact:
        lat = finite(row, "latitude", "lat")
        lng = finite(row, "longitude", "lng", "lon")
        if lat is None or lng is None:
            raise PublicArtifactError(f"authorized MAP_READY event missing coordinates: {out['id']}")
        out["latitude"], out["longitude"] = lat, lng

    return out


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [item for item in payload["events"] if isinstance(item, dict)]
    raise PublicArtifactError("unsupported event payload")


def project(payload: Any) -> list[dict[str, Any]]:
    return [value for value in (project_event(item) for item in rows(payload)) if value is not None]


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
    """Promote staged output with rollback restoration on a failed final rename."""
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
            public_rows = project(load(manifest_path.parent / "pages" / name))
            ensure_unique_public_ids(public_rows, scope=name)
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

        major_events = project(load(major_path))
        ensure_unique_public_ids(major_events, scope="major")
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
