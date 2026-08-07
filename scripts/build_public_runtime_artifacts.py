#!/usr/bin/env python3
"""Build reader-safe public runtime artifacts from private NYCIF feed outputs.

This is the confidentiality boundary between the private engineering repository and
public browser-delivered data. It deliberately projects a small reader-facing
schema instead of copying source feed rows wholesale.

Safety invariants:
- only public_event rows without parent_event_id are emitted;
- exact coordinates/address are emitted only when semantic MAP_READY authority
  and certified_pin=true are both present;
- legacy coordinate_status/map_ready or mere coordinate presence never certifies
  a public exact location;
- source identifiers, ranking/confidence fields, reviewer/debug/evidence fields,
  private source details, and internal URLs are never emitted;
- output is staged in a temporary directory and swapped into place only after the
  complete artifact set passes the public-output scan.

Default source contract:
  data/schema-v1-discovery/approved/manifest.json
  data/schema-v1-discovery/approved/pages/*.json
  data/schema-v1-discovery/major/events.json

Default output contract:
  public-data/events/manifest.json
  public-data/events/pages/*.json
  public-data/events/major/events.json
  public-data/artifact-manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APPROVED_MANIFEST = ROOT / "data" / "schema-v1-discovery" / "approved" / "manifest.json"
DEFAULT_MAJOR_EVENTS = ROOT / "data" / "schema-v1-discovery" / "major" / "events.json"
DEFAULT_OUTPUT_ROOT = ROOT / "public-data"

PUBLIC_SCHEMA_VERSION = "nycif-public-runtime-v1"

DENIED_OUTPUT_KEYS = {
    "source",
    "source_url",
    "source_dataset",
    "source_event_id",
    "source_system",
    "source_name",
    "ingestion_url",
    "private_source",
    "private_source_url",
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
    "internal_reason",
    "internal_reason_code",
    "prompt",
    "internal_prompt",
}

DENIED_VALUE_FRAGMENTS = (
    "raw.githubusercontent.com/setoxxx/",
    "github.com/setoxxx/",
    "setoxxx.github.io/nycif-field-desk",
    "localhost",
    "127.0.0.1",
)

SAFE_TOP_LEVEL_TEXT_FIELDS = (
    "id",
    "title",
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
)

SAFE_LIST_FIELDS = ("interests", "tags")
SAFE_WHEN_FIELDS = ("event_date", "start_date_time", "end_date_time", "timezone")
SAFE_PLACE_FIELDS = (
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


class PublicArtifactError(RuntimeError):
    """Fail-closed public artifact build error."""


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise PublicArtifactError(f"required input missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PublicArtifactError(f"invalid JSON: {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pick(mapping: Any, *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return None


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def semantic_state(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    evidence = row.get("location_evidence") if isinstance(row.get("location_evidence"), dict) else {}
    value = pick(row, "map_eligibility_state") or pick(nycif, "map_eligibility_state") or pick(
        evidence, "map_eligibility_state"
    )
    return str(value or "").strip().upper()


def semantic_certified_pin(row: dict[str, Any]) -> bool:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    evidence = row.get("location_evidence") if isinstance(row.get("location_evidence"), dict) else {}
    value = row.get("certified_pin")
    if value is None:
        value = nycif.get("certified_pin")
    if value is None:
        value = evidence.get("certified_pin")
    return as_bool(value)


def exact_authorized(row: dict[str, Any]) -> bool:
    return semantic_state(row) == "MAP_READY" and semantic_certified_pin(row)


def reader_role(row: dict[str, Any]) -> str:
    nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return str(pick(row, "event_role") or pick(nycif, "event_role") or "public_event").strip().lower()


def first_finite(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number not in (float("inf"), float("-inf")):
            return number
    return None


def clean_text(value: Any, *, limit: int = 2000) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > limit:
        text = text[:limit]
    return text


def copy_text_fields(source: dict[str, Any], fields: Iterable[str], target: dict[str, Any]) -> None:
    for key in fields:
        value = clean_text(source.get(key))
        if value is not None:
            target[key] = value


def project_when(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("when") if isinstance(row.get("when"), dict) else {}
    result: dict[str, Any] = {}
    for key in SAFE_WHEN_FIELDS:
        value = clean_text(raw.get(key) if raw.get(key) is not None else row.get(key))
        if value is not None:
            result[key] = value
    return result


def project_place(row: dict[str, Any], *, exact: bool) -> dict[str, Any]:
    raw = row.get("place") if isinstance(row.get("place"), dict) else {}
    result: dict[str, Any] = {}
    for key in SAFE_PLACE_FIELDS:
        value = raw.get(key)
        if value is None:
            value = row.get(key)
        text = clean_text(value)
        if text is not None:
            result[key] = text

    # Exact street address is reader-safe only when exact publication is semantically authorized.
    if exact:
        address = clean_text(raw.get("address") if raw.get("address") is not None else row.get("address"))
        if address is not None:
            result["address"] = address

    return result


def project_event(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    if row.get("parent_event_id"):
        return None
    if reader_role(row) != "public_event":
        return None

    event_id = clean_text(pick(row, "id", "event_id"), limit=300)
    title = clean_text(pick(row, "title", "name"), limit=1000)
    if not event_id or not title:
        return None

    exact = exact_authorized(row)
    state = semantic_state(row)
    if state not in {"MAP_READY", "GENERAL_AREA", "LIST_ONLY", "REVIEW_REQUIRED"}:
        state = "LIST_ONLY"
    if state == "MAP_READY" and not exact:
        state = "REVIEW_REQUIRED"

    result: dict[str, Any] = {
        "id": event_id,
        "title": title,
        "event_role": "public_event",
        "map_eligibility_state": state,
        "certified_pin": exact,
    }
    copy_text_fields(row, SAFE_TOP_LEVEL_TEXT_FIELDS[2:], result)

    for key in SAFE_LIST_FIELDS:
        values = row.get(key)
        if isinstance(values, list):
            safe_values = [clean_text(v, limit=200) for v in values]
            result[key] = [value for value in safe_values if value]

    when = project_when(row)
    if when:
        result["when"] = when

    place = project_place(row, exact=exact)
    if place:
        result["place"] = place

    if exact:
        lat = first_finite(row, "latitude", "lat")
        lng = first_finite(row, "longitude", "lng", "lon")
        if lat is None or lng is None:
            raise PublicArtifactError(f"MAP_READY certified event missing coordinates: {event_id}")
        result["latitude"] = lat
        result["longitude"] = lng
    else:
        # Explicitly omit coordinates even when legacy rows contain them.
        result.pop("latitude", None)
        result.pop("longitude", None)

    return result


def events_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    raise PublicArtifactError("unsupported event page schema; expected list or object.events")


def project_payload(payload: Any) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for row in events_from_payload(payload):
        event = project_event(row)
        if event is not None:
            projected.append(event)
    return projected


def iter_scalars(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in DENIED_OUTPUT_KEYS:
                raise PublicArtifactError(f"denied public output key present: {key}")
            yield from iter_scalars(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_scalars(child)
    else:
        yield (None, value)


def scan_public_payload(payload: Any) -> None:
    for _key, value in iter_scalars(payload):
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        for fragment in DENIED_VALUE_FRAGMENTS:
            if fragment.lower() in lowered:
                raise PublicArtifactError(f"denied internal/public-repository URL fragment in output: {fragment}")


def aggregate_page_metadata(events: list[dict[str, Any]], page_name: str) -> dict[str, Any]:
    categories: Counter[str] = Counter()
    boroughs: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    dates: list[str] = []
    for event in events:
        category = clean_text(event.get("category"), limit=200) or "general"
        categories[category] += 1
        place = event.get("place") if isinstance(event.get("place"), dict) else {}
        borough = clean_text(place.get("borough"), limit=200) or "Other"
        boroughs[borough] += 1
        roles[event.get("event_role") or "public_event"] += 1
        when = event.get("when") if isinstance(event.get("when"), dict) else {}
        date = clean_text(when.get("event_date") or event.get("event_date"), limit=20)
        if date:
            dates.append(date[:10])
    return {
        "page": page_name,
        "count": len(events),
        "earliest_date": min(dates) if dates else None,
        "latest_date": max(dates) if dates else None,
        "categories": dict(sorted(categories.items())),
        "boroughs": dict(sorted(boroughs.items())),
        "roles": dict(sorted(roles.items())),
    }


def build(
    *,
    approved_manifest: Path,
    major_events: Path,
    output_root: Path,
    release_sha: str,
) -> dict[str, Any]:
    if not release_sha.strip():
        raise PublicArtifactError("release SHA is required")

    source_manifest = load_json(approved_manifest)
    if not isinstance(source_manifest, dict) or not isinstance(source_manifest.get("pages"), list):
        raise PublicArtifactError("approved discovery manifest missing pages[]")

    approved_dir = approved_manifest.parent
    source_pages_dir = approved_dir / "pages"
    generated_at = datetime.now(timezone.utc).isoformat()

    output_parent = output_root.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix="nycif-public-data-", dir=str(output_parent)))
    staged_root = temp_dir / output_root.name

    try:
        page_metadata: list[dict[str, Any]] = []
        total = 0
        for item in source_manifest["pages"]:
            if not isinstance(item, dict):
                raise PublicArtifactError("manifest page entry must be an object")
            page_name = clean_text(item.get("page"), limit=200)
            if not page_name or Path(page_name).name != page_name or not page_name.endswith(".json"):
                raise PublicArtifactError(f"unsafe manifest page name: {page_name!r}")
            source_page = source_pages_dir / page_name
            events = project_payload(load_json(source_page))
            payload = {
                "schema_version": PUBLIC_SCHEMA_VERSION,
                "release_sha": release_sha,
                "generated_at": generated_at,
                "events": events,
            }
            scan_public_payload(payload)
            write_json(staged_root / "events" / "pages" / page_name, payload)
            meta = aggregate_page_metadata(events, page_name)
            page_metadata.append(meta)
            total += len(events)

        public_manifest = {
            "schema_version": PUBLIC_SCHEMA_VERSION,
            "layer": "public-reader-safe",
            "release_sha": release_sha,
            "generated_at": generated_at,
            "total": total,
            "page_count": len(page_metadata),
            "pages": page_metadata,
        }
        scan_public_payload(public_manifest)
        write_json(staged_root / "events" / "manifest.json", public_manifest)

        major_projected = project_payload(load_json(major_events))
        major_payload = {
            "schema_version": PUBLIC_SCHEMA_VERSION,
            "release_sha": release_sha,
            "generated_at": generated_at,
            "events": major_projected,
        }
        scan_public_payload(major_payload)
        write_json(staged_root / "events" / "major" / "events.json", major_payload)

        artifact_files = sorted(path for path in staged_root.rglob("*") if path.is_file())
        artifact_manifest = {
            "schema_version": PUBLIC_SCHEMA_VERSION,
            "release_sha": release_sha,
            "generated_at": generated_at,
            "artifacts": [
                {
                    "path": str(path.relative_to(staged_root)).replace(os.sep, "/"),
                    "sha256": sha256_file(path),
                }
                for path in artifact_files
            ],
        }
        scan_public_payload(artifact_manifest)
        write_json(staged_root / "artifact-manifest.json", artifact_manifest)

        # Scan every staged JSON file after all artifacts are written.
        for path in staged_root.rglob("*.json"):
            scan_public_payload(load_json(path))

        if output_root.exists():
            shutil.rmtree(output_root)
        os.replace(staged_root, output_root)

        return {
            "schema_version": PUBLIC_SCHEMA_VERSION,
            "release_sha": release_sha,
            "generated_at": generated_at,
            "public_events": total,
            "major_events": len(major_projected),
            "page_count": len(page_metadata),
            "output_root": str(output_root),
            "qa_pass": True,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-manifest", type=Path, default=DEFAULT_APPROVED_MANIFEST)
    parser.add_argument("--major-events", type=Path, default=DEFAULT_MAJOR_EVENTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--release-sha", default=os.environ.get("GITHUB_SHA", ""))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build(
            approved_manifest=args.approved_manifest,
            major_events=args.major_events,
            output_root=args.output_root,
            release_sha=args.release_sha,
        )
    except PublicArtifactError as exc:
        print(json.dumps({"qa_pass": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
