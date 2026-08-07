#!/usr/bin/env python3
"""Build reader-safe public map artifacts from private NYCIF discovery feeds."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "data/schema-v1-discovery/approved/manifest.json"
DEFAULT_MAJOR = ROOT / "data/schema-v1-discovery/major/events.json"
DEFAULT_OUTPUT = ROOT / "public-data"
SCHEMA = "nycif-public-runtime-v1"
DENIED_KEYS = {
    "source", "source_url", "source_dataset", "source_event_id", "source_system",
    "ingestion_url", "confidence", "confidence_score", "priority_score", "ranking_score",
    "reviewer", "reviewer_id", "review_notes", "private_notes", "debug", "debug_info",
    "evidence", "evidence_bundle", "resolver_evidence", "internal_prompt", "prompt"
}
DENIED_FRAGMENTS = (
    "raw.githubusercontent.com/setoxxx/", "github.com/setoxxx/",
    "setoxxx.github.io/nycif-field-desk", "localhost", "127.0.0.1"
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
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")

def b(value: Any) -> bool:
    if isinstance(value, bool): return value
    if isinstance(value, str): return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)

def semantic_state(row: dict[str, Any]) -> str:
    nested = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    evidence = row.get("location_evidence") if isinstance(row.get("location_evidence"), dict) else {}
    value = row.get("map_eligibility_state") or nested.get("map_eligibility_state") or evidence.get("map_eligibility_state")
    return str(value or "").upper()

def certified(row: dict[str, Any]) -> bool:
    nested = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    evidence = row.get("location_evidence") if isinstance(row.get("location_evidence"), dict) else {}
    value = row.get("certified_pin")
    if value is None: value = nested.get("certified_pin")
    if value is None: value = evidence.get("certified_pin")
    return b(value)

def role(row: dict[str, Any]) -> str:
    nested = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
    return str(row.get("event_role") or nested.get("event_role") or "public_event").lower()

def text(value: Any, limit: int = 2000) -> str | None:
    if value is None: return None
    value = str(value).strip()
    if not value: return None
    return value[:limit]

def finite(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        try:
            value = float(row[key])
        except Exception:
            continue
        if value == value and abs(value) != float("inf"): return value
    return None

def project_event(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("parent_event_id") or role(row) != "public_event":
        return None
    event_id = text(row.get("id") or row.get("event_id"), 300)
    title = text(row.get("title") or row.get("name"), 1000)
    if not event_id or not title:
        return None
    exact = semantic_state(row) == "MAP_READY" and certified(row)
    state = semantic_state(row)
    if state not in {"MAP_READY", "GENERAL_AREA", "LIST_ONLY", "REVIEW_REQUIRED"}: state = "LIST_ONLY"
    if state == "MAP_READY" and not exact: state = "REVIEW_REQUIRED"
    out: dict[str, Any] = {
        "id": event_id, "title": title, "event_role": "public_event",
        "map_eligibility_state": state, "certified_pin": exact,
    }
    for key in ("category", "event_type", "section", "description", "event_date", "start_date_time", "end_date_time", "timezone", "public_url", "url"):
        value = text(row.get(key))
        if value is not None: out[key] = value
    for key in ("interests", "tags"):
        if isinstance(row.get(key), list): out[key] = [text(v, 200) for v in row[key] if text(v, 200)]
    when_src = row.get("when") if isinstance(row.get("when"), dict) else {}
    when = {}
    for key in ("event_date", "start_date_time", "end_date_time", "timezone"):
        value = text(when_src.get(key) if when_src.get(key) is not None else row.get(key))
        if value is not None: when[key] = value
    if when: out["when"] = when
    place_src = row.get("place") if isinstance(row.get("place"), dict) else {}
    place = {}
    for key in ("location", "neighborhood", "locality", "city", "admin_area", "state", "country_code", "country", "borough"):
        value = text(place_src.get(key) if place_src.get(key) is not None else row.get(key))
        if value is not None: place[key] = value
    if exact:
        address = text(place_src.get("address") if place_src.get("address") is not None else row.get("address"))
        if address is not None: place["address"] = address
        lat, lng = finite(row, "latitude", "lat"), finite(row, "longitude", "lng", "lon")
        if lat is None or lng is None: raise PublicArtifactError(f"certified MAP_READY row missing coordinates: {event_id}")
        out["latitude"], out["longitude"] = lat, lng
    if place: out["place"] = place
    return out

def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list): return [x for x in payload["events"] if isinstance(x, dict)]
    raise PublicArtifactError("unsupported event payload")

def project(payload: Any) -> list[dict[str, Any]]:
    return [v for v in (project_event(x) for x in rows(payload)) if v is not None]

def scan(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in DENIED_KEYS: raise PublicArtifactError(f"denied output key: {key}")
            scan(child)
    elif isinstance(value, list):
        for child in value: scan(child)
    elif isinstance(value, str):
        low = value.lower()
        for fragment in DENIED_FRAGMENTS:
            if fragment.lower() in low: raise PublicArtifactError(f"denied internal URL fragment: {fragment}")

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def build(manifest_path: Path, major_path: Path, output: Path, release_sha: str) -> dict[str, Any]:
    if not release_sha: raise PublicArtifactError("release SHA required")
    manifest = load(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list): raise PublicArtifactError("manifest missing pages[]")
    generated = datetime.now(timezone.utc).isoformat()
    parent = output.parent; parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="nycif-public-", dir=str(parent))) / output.name
    total = 0; page_meta = []
    try:
        for item in manifest["pages"]:
            name = text(item.get("page"), 200) if isinstance(item, dict) else None
            if not name or Path(name).name != name or not name.endswith(".json"): raise PublicArtifactError(f"unsafe page name: {name}")
            public_rows = project(load(manifest_path.parent / "pages" / name))
            payload = {"schema_version": SCHEMA, "release_sha": release_sha, "generated_at": generated, "events": public_rows}
            scan(payload); write(temp / "events/pages" / name, payload)
            total += len(public_rows)
            page_meta.append({"page": name, "count": len(public_rows)})
        public_manifest = {"schema_version": SCHEMA, "layer": "public-reader-safe", "release_sha": release_sha, "generated_at": generated, "total": total, "page_count": len(page_meta), "pages": page_meta}
        scan(public_manifest); write(temp / "events/manifest.json", public_manifest)
        major = {"schema_version": SCHEMA, "release_sha": release_sha, "generated_at": generated, "events": project(load(major_path))}
        scan(major); write(temp / "events/major/events.json", major)
        files = sorted(p for p in temp.rglob("*") if p.is_file())
        artifact_manifest = {"schema_version": SCHEMA, "release_sha": release_sha, "generated_at": generated, "artifacts": [{"path": str(p.relative_to(temp)), "sha256": sha(p)} for p in files]}
        scan(artifact_manifest); write(temp / "artifact-manifest.json", artifact_manifest)
        for path in temp.rglob("*.json"): scan(load(path))
        if output.exists(): shutil.rmtree(output)
        os.replace(temp, output)
        return {"qa_pass": True, "release_sha": release_sha, "public_events": total, "page_count": len(page_meta), "output_root": str(output)}
    finally:
        shutil.rmtree(temp.parent, ignore_errors=True)

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
