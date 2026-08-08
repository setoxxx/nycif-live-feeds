#!/usr/bin/env python3
"""Build the BORG -> Enigma pre-filter observation handoff.

This module sits between official-source acquisition and semantic processing.
It does not normalize, deduplicate, geocode, resolve identity, or publish.
Its only job is to prove that every acquired source row is registered in a
machine-readable receipt before downstream filtering begins.

Contract:
    BORG RECEIVES IT -> ENIGMA REMEMBERS IT -> SEMANTIC AUTHORITIES RESOLVE IT.

Coordinates, if present in a source row, are observations only. This handoff
never grants MAP_READY or exact-pin authority.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "borg_enigma_handoff_v1.json"

SOURCE_SPECS = (
    {
        "source_id": "nyc_open_data_permitted_events",
        "dataset_id": "tvpp-9vvx",
        "path": ROOT / "data" / "raw_nyc_open_data_snapshot.json",
        "row_keys": (),
        "native_id_candidates": ("event_id", "eventid", "eventid_1", "permit_id"),
    },
    {
        "source_id": "nyc_citywide_events_calendar",
        "dataset_id": "api.nyc.gov/calendar/search",
        # This is deliberately the raw pre-filter observation file, not the
        # active/deduplicated semantic snapshot. Every retrieved row belongs
        # in the intake ledger even if semantic projection later collapses it.
        "path": ROOT / "data" / "nyc_citywide_events_calendar_raw_observations.json",
        "row_keys": (),
        "native_id_candidates": ("id", "event_id", "eventId", "guid"),
    },
    {
        "source_id": "nyc_parks_bigapps_events",
        "dataset_id": "nyc-parks-bigapps",
        "path": ROOT / "data" / "nyc_parks_bigapps_events_snapshot.json",
        "row_keys": ("events", "items", "results"),
        "native_id_candidates": ("id", "event_id", "eventId", "eventid"),
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def rows_from_snapshot(payload: Any, row_keys: Iterable[str]) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in row_keys:
            rows = payload.get(key)
            if isinstance(rows, list):
                return rows
    raise TypeError("snapshot does not expose a supported row list")


def native_id(row: Any, candidates: Iterable[str]) -> str:
    if not isinstance(row, dict):
        return ""
    for key in candidates:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def build_source_receipt(spec: dict[str, Any]) -> dict[str, Any]:
    path: Path = spec["path"]
    if not path.exists():
        raise FileNotFoundError(f"BORG snapshot missing: {path.relative_to(ROOT)}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = rows_from_snapshot(payload, spec["row_keys"])
    observations = []
    for index, row in enumerate(rows):
        observations.append(
            {
                "ordinal": index,
                "source_record_id": native_id(row, spec["native_id_candidates"]),
                "content_sha256": sha256_json(row),
            }
        )
    return {
        "source_id": spec["source_id"],
        "dataset_id": spec["dataset_id"],
        "snapshot_path": str(path.relative_to(ROOT)),
        "snapshot_sha256": sha256_json(payload),
        "observed_row_count": len(rows),
        "registered_observation_count": len(observations),
        "rows_without_native_id": sum(1 for row in observations if not row["source_record_id"]),
        "observations": observations,
    }


def build_handoff() -> dict[str, Any]:
    sources = [build_source_receipt(spec) for spec in SOURCE_SPECS]
    observed = sum(source["observed_row_count"] for source in sources)
    registered = sum(source["registered_observation_count"] for source in sources)
    handoff = {
        "schema_id": "nycif-borg-enigma-handoff-v1",
        "generated_at_utc": utc_now(),
        "stage": "post_acquisition_pre_semantic_filter",
        "governing_rule": "STORE FIRST. IDENTIFY SECOND. RESOLVE THIRD. PUBLISH LAST.",
        "identity_authority": "OccurrenceIdentityV2",
        "exact_location_authority": "Projector V3",
        "coordinates_are_authority": False,
        "source_count": len(sources),
        "observed_row_count": observed,
        "registered_observation_count": registered,
        "unregistered_row_count": observed - registered,
        "qa_pass": observed == registered and observed > 0,
        "sources": sources,
    }
    if not handoff["qa_pass"]:
        raise RuntimeError(f"BORG/Enigma handoff accounting failed: {handoff}")
    return handoff


def main() -> int:
    handoff = build_handoff()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(handoff, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "BORG/Enigma handoff: "
        f"{handoff['registered_observation_count']}/{handoff['observed_row_count']} "
        "source rows registered before semantic filtering"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
