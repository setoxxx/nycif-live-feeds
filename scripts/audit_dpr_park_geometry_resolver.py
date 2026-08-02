#!/usr/bin/env python3
"""Measure fail-closed DPR park-centroid rescue candidates for SHADOW-2."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from enigma.shadow2.location_evidence import classify_location_evidence  # noqa: E402
from enigma.shadow2.read_only_snapshot import ReadOnlySnapshot  # noqa: E402
from nycif.normalize.facility_resolver import resolve_facility_anchor  # noqa: E402
from nycif.normalize.park_geometry import (  # noqa: E402
    DEFAULT_LOOKUP_PATH,
    load_park_lookup,
    normalize_park_name,
)

BOROUGH_ALIASES = {
    "m": "Manhattan", "mn": "Manhattan", "manhattan": "Manhattan", "new york": "Manhattan",
    "b": "Brooklyn", "bk": "Brooklyn", "brooklyn": "Brooklyn",
    "q": "Queens", "qn": "Queens", "queens": "Queens",
    "x": "Bronx", "bx": "Bronx", "bronx": "Bronx", "the bronx": "Bronx",
    "r": "Staten Island", "si": "Staten Island", "staten island": "Staten Island",
}


def canonical_borough(value: Any) -> str | None:
    values = value if isinstance(value, list) else [value]
    matches = {
        BOROUGH_ALIASES.get(re.sub(r"\s+", " ", str(item or "").strip().casefold()))
        for item in values
    }
    matches.discard(None)
    return next(iter(matches)) if len(matches) == 1 else None


def source_identity(record: dict[str, Any]) -> tuple[str, str]:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return (
        str(record.get("source_dataset") or source.get("dataset") or "").strip(),
        str(record.get("source_event_id") or source.get("source_event_id") or "").strip(),
    )


def coordinate_status(record: dict[str, Any]) -> str:
    nycif = record.get("nycif") if isinstance(record.get("nycif"), dict) else {}
    return str(nycif.get("coordinate_status") or record.get("coordinate_status") or "unknown")


def _values(value: Any, *, split: bool = False) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [text for item in value for text in _values(item, split=split)]
    text = str(value or "").strip()
    if not text:
        return []
    if split:
        return [part.strip() for part in re.split(r"[,;|]", text) if part.strip()]
    return [text]


def raw_evidence_index(snapshot: ReadOnlySnapshot) -> dict[tuple[str, str], dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, set[str]]] = {}
    for wrapped in snapshot.read_raw_snapshots():
        record = wrapped.record
        identity = source_identity(record)
        if not all(identity):
            continue
        item = candidates.setdefault(identity, {"boroughs": set(), "park_ids": set(), "park_names": set()})
        for field in ("borough", "event_borough", "boroughs"):
            borough = canonical_borough(record.get(field))
            if borough:
                item["boroughs"].add(borough)
        for field in ("park_id", "park_ids", "parkid", "parkids"):
            item["park_ids"].update(value.upper() for value in _values(record.get(field), split=True))
        for field in ("park_name", "park_names", "parkname", "parknames"):
            item["park_names"].update(
                normalized
                for value in _values(record.get(field))
                if (normalized := normalize_park_name(value))
            )
    return {
        identity: {
            "borough": next(iter(values["boroughs"])) if len(values["boroughs"]) == 1 else None,
            "park_ids": sorted(values["park_ids"]),
            "park_names": sorted(values["park_names"]),
        }
        for identity, values in candidates.items()
    }


def build_delta(snapshot: ReadOnlySnapshot, lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raw_evidence = raw_evidence_index(snapshot)
    baseline = 0
    candidates: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    park_counts: Counter[str] = Counter()
    mismatch_reasons: Counter[str] = Counter()
    verification_counts: Counter[str] = Counter()

    for wrapped in snapshot.read_review_events():
        record = wrapped.record
        if coordinate_status(record) != "list_only":
            continue
        try:
            tier = classify_location_evidence(record).tier.value
        except Exception:
            continue
        if tier != "unresolved":
            continue
        baseline += 1
        probe = dict(record)
        probe["evidence_tier"] = "unresolved"
        resolved = resolve_facility_anchor(probe, lookup=lookup)
        if not resolved:
            continue

        dataset, source_event_id = source_identity(record)
        identity = (dataset, source_event_id)
        raw = raw_evidence.get(identity, {})
        event_borough = canonical_borough(record.get("borough") or record.get("event_borough"))
        borough_evidence_source = "projected_record" if event_borough else None
        if event_borough is None:
            event_borough = raw.get("borough")
            borough_evidence_source = "raw_source" if event_borough else None
        park_borough = canonical_borough(resolved.get("park_borough"))
        warnings: list[str] = []
        verification: list[str] = []

        if event_borough and park_borough:
            if event_borough != park_borough:
                warnings.append("borough_mismatch")
                mismatch_reasons["borough_mismatch"] += 1
            else:
                verification.append("borough_match")

        resolved_park_id = str(resolved.get("park_id") or "").upper()
        raw_park_ids = set(raw.get("park_ids") or [])
        raw_park_names = set(raw.get("park_names") or [])
        resolved_names = {
            normalize_park_name(resolved.get("park_name")),
            normalize_park_name(resolved.get("park_query_name")),
        }
        resolved_names.discard("")
        if raw_park_ids:
            if resolved_park_id in raw_park_ids:
                verification.append("raw_park_id_match")
            else:
                warnings.append("raw_park_id_mismatch")
                mismatch_reasons["raw_park_id_mismatch"] += 1
        elif raw_park_names:
            if resolved_names & raw_park_names:
                verification.append("raw_park_name_match")
            else:
                warnings.append("raw_park_name_mismatch")
                mismatch_reasons["raw_park_name_mismatch"] += 1

        if not (-74.2591 <= float(resolved["longitude"]) <= -73.7004):
            warnings.append("longitude_outside_nyc")
            mismatch_reasons["longitude_outside_nyc"] += 1
        if not (40.4774 <= float(resolved["latitude"]) <= 40.9176):
            warnings.append("latitude_outside_nyc")
            mismatch_reasons["latitude_outside_nyc"] += 1

        verification_state = "mismatch" if warnings else ("verified" if verification else "unverified")
        verification_counts[verification_state] += 1
        source_counts[dataset or "unknown"] += 1
        park_counts[resolved_park_id or "unknown"] += 1
        candidates.append(
            {
                "id": record.get("id"),
                "title": record.get("title"),
                "location": record.get("location") or record.get("display_location"),
                "borough": event_borough,
                "borough_evidence_source": borough_evidence_source,
                "source_dataset": dataset,
                "source_event_id": source_event_id,
                "coordinate_precision": "park_level_anchor",
                "coordinate_status": "approximate",
                "display_disposition": "approximate_marker",
                "coordinate_source": "dpr_parks_properties_centroid",
                "latitude": resolved["latitude"],
                "longitude": resolved["longitude"],
                "park_id": resolved.get("park_id"),
                "park_name": resolved.get("park_name"),
                "park_borough": park_borough,
                "park_query_name": resolved.get("park_query_name"),
                "park_match_type": resolved.get("park_match_type"),
                "verification_state": verification_state,
                "verification_evidence": verification,
                "raw_park_ids": sorted(raw_park_ids),
                "raw_park_names": sorted(raw_park_names),
                "potential_mismatch_reasons": warnings,
                "promotion_allowed": False,
                "automatic_feed_promotion": False,
                "public_map_modified": False,
            }
        )

    potential_mismatch_count = verification_counts["mismatch"]
    return {
        "schema_version": "shadow2-dpr-park-geometry-delta-v1",
        "safety": {
            "read_only_measurement": True,
            "coordinates_written_to_feeds": False,
            "coordinate_statuses_written_to_feeds": False,
            "automatic_promotion": False,
            "public_map_modified": False,
            "promotion_allowed": False,
        },
        "dataset": {
            "name": "NYC Parks Properties",
            "dataset_id": "enfh-gkve",
            "lookup_aliases": len(lookup),
        },
        "baseline_unresolved": baseline,
        "park_level_anchor_candidates": len(candidates),
        "remain_truly_unresolvable": baseline - len(candidates),
        "potential_incorrect_match_count": potential_mismatch_count,
        "unverified_match_count": verification_counts["unverified"],
        "verification_state_distribution": dict(sorted(verification_counts.items())),
        "raw_source_identity_count": len(raw_evidence),
        "potential_mismatch_reason_distribution": dict(sorted(mismatch_reasons.items())),
        "source_distribution": dict(sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))),
        "matched_park_distribution": dict(sorted(park_counts.items(), key=lambda item: (-item[1], item[0]))),
        "records": candidates,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# SHADOW-2 DPR Park Geometry Delta",
            "",
            "Read-only measurement. No feed, map, promotion, or production state was changed.",
            "",
            f"- Baseline unresolved: **{report['baseline_unresolved']:,}**",
            f"- Park-level anchor candidates: **{report['park_level_anchor_candidates']:,}**",
            f"- Remain truly unresolvable: **{report['remain_truly_unresolvable']:,}**",
            f"- Potential incorrect matches: **{report['potential_incorrect_match_count']:,}**",
            f"- Matches without independent borough/park evidence: **{report['unverified_match_count']:,}**",
            "",
            "Every candidate remains `promotion_allowed: false`, uses `coordinate_status: approximate`, and is not written to a public feed by this audit.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookup", type=Path, default=DEFAULT_LOOKUP_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/shadow2-audit"))
    args = parser.parse_args(argv)
    lookup = load_park_lookup(args.lookup)
    if not lookup:
        raise SystemExit(f"empty or missing park lookup: {args.lookup}")
    report = build_delta(ReadOnlySnapshot(), lookup)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "shadow2-park-geometry-delta.json"
    md_path = args.output_dir / "shadow2-park-geometry-delta.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "qa_pass": report["potential_incorrect_match_count"] == 0,
        "baseline_unresolved": report["baseline_unresolved"],
        "park_level_anchor_candidates": report["park_level_anchor_candidates"],
        "remain_truly_unresolvable": report["remain_truly_unresolvable"],
        "potential_incorrect_match_count": report["potential_incorrect_match_count"],
        "unverified_match_count": report["unverified_match_count"],
        "outputs": [str(json_path), str(md_path)],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
