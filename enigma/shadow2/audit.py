"""Deterministic read-only SHADOW-2 real-data audit and repair-queue builder."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from enigma.shadow2.location_evidence import classify_location_evidence
from enigma.shadow2.read_only_snapshot import ReadOnlySnapshot, SnapshotRecord

TIERS = (
    "exact_source_coordinate",
    "exact_address",
    "exact_intersection",
    "certified_street_segment",
    "certified_facility",
    "approximate_area",
    "unresolved",
    "malformed",
)
BOROUGH_ALIASES = {
    "mn": "Manhattan",
    "manhattan": "Manhattan",
    "new york": "Manhattan",
    "bk": "Brooklyn",
    "brooklyn": "Brooklyn",
    "qn": "Queens",
    "q": "Queens",
    "queens": "Queens",
    "bx": "Bronx",
    "bronx": "Bronx",
    "the bronx": "Bronx",
    "si": "Staten Island",
    "staten island": "Staten Island",
}
_BOROUGH_TEXT_PATTERNS = {
    "Staten Island": re.compile(r"\bStaten\s+Island\b", re.IGNORECASE),
    "Manhattan": re.compile(r"\bManhattan\b", re.IGNORECASE),
    "Brooklyn": re.compile(r"\bBrooklyn\b", re.IGNORECASE),
    "Queens": re.compile(r"\bQueens\b", re.IGNORECASE),
    "Bronx": re.compile(r"\b(?:The\s+)?Bronx\b", re.IGNORECASE),
}
_LAT_KEYS = ("latitude", "lat")
_LNG_KEYS = ("longitude", "lng", "lon", "long")
_FACILITY_PATTERNS = {
    "park": re.compile(r"\bpark\b", re.IGNORECASE),
    "playground": re.compile(r"\bplayground\b", re.IGNORECASE),
    "pool": re.compile(r"\bpool\b", re.IGNORECASE),
    "recreation_center": re.compile(r"\b(?:recreation\s+center|rec\s+center)\b", re.IGNORECASE),
    "field": re.compile(r"\bfields?\b", re.IGNORECASE),
    "court": re.compile(r"\bcourts?\b", re.IGNORECASE),
    "visitor_center": re.compile(r"\bvisitor\s+center\b", re.IGNORECASE),
    "nature_center": re.compile(r"\bnature\s+center\b", re.IGNORECASE),
    "gymnasium": re.compile(r"\bgymnasium\b", re.IGNORECASE),
}
_RELATIONAL_PATTERNS = {
    "in_phrase": re.compile(r"\bin\b", re.IGNORECASE),
    "at_phrase": re.compile(r"\bat\b", re.IGNORECASE),
    "entrance_to": re.compile(r"\bentrance\s+to\b", re.IGNORECASE),
}
_DUPLICATE_CONTAINER_PATTERN = re.compile(r"^(.+?)\s+in\s+\1$", re.IGNORECASE)
_CONTAINER_SPLIT_PATTERN = re.compile(r"\s+(?:in|at)\s+", re.IGNORECASE)


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _canonical_borough(value: Any) -> str | None:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    matches = {
        canonical
        for candidate in values
        if (canonical := BOROUGH_ALIASES.get(re.sub(r"\s+", " ", str(candidate or "").strip().lower())))
    }
    return next(iter(matches)) if len(matches) == 1 else None


def infer_borough(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """Infer one borough conservatively; never use free-text abbreviations."""
    for field in ("borough", "event_borough", "boroughs"):
        borough = _canonical_borough(record.get(field))
        if borough:
            return borough, field

    text = " ".join(
        str(record.get(field) or "")
        for field in ("address", "location", "display_location")
    )
    matches = {
        borough
        for borough, pattern in _BOROUGH_TEXT_PATTERNS.items()
        if pattern.search(text)
    }
    return (next(iter(matches)), "location_text") if len(matches) == 1 else (None, None)


def source_identity(record: dict[str, Any]) -> tuple[str, str]:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    dataset = str(record.get("source_dataset") or source.get("dataset") or "").strip()
    source_event_id = str(record.get("source_event_id") or source.get("source_event_id") or "").strip()
    return dataset, source_event_id


def coordinate_status(record: dict[str, Any]) -> str:
    nycif = record.get("nycif") if isinstance(record.get("nycif"), dict) else {}
    return str(nycif.get("coordinate_status") or record.get("coordinate_status") or "unknown")


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def find_coordinate_pairs(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Find explicit lat/lng pairs and GeoJSON Point coordinates with key paths."""
    found: list[dict[str, Any]] = []

    def visit(value: Any, path: str, depth: int) -> None:
        if depth > 5:
            return
        if isinstance(value, dict):
            lowered = {str(key).lower(): key for key in value}
            lat_key = next((lowered[key] for key in _LAT_KEYS if key in lowered), None)
            lng_key = next((lowered[key] for key in _LNG_KEYS if key in lowered), None)
            if lat_key is not None and lng_key is not None:
                lat = _finite_number(value.get(lat_key))
                lng = _finite_number(value.get(lng_key))
                if lat is not None and lng is not None:
                    found.append(
                        {
                            "latitude": lat,
                            "longitude": lng,
                            "path": path or "$",
                            "kind": "named_fields",
                            "keys": [str(lat_key), str(lng_key)],
                        }
                    )
            if str(value.get("type") or "").lower() == "point":
                coords = value.get("coordinates")
                if isinstance(coords, list) and len(coords) >= 2:
                    lng = _finite_number(coords[0])
                    lat = _finite_number(coords[1])
                    if lat is not None and lng is not None:
                        found.append(
                            {
                                "latitude": lat,
                                "longitude": lng,
                                "path": f"{path or '$'}.coordinates",
                                "kind": "geojson_point",
                                "keys": ["coordinates[1]", "coordinates[0]"],
                            }
                        )
            for key, child in value.items():
                visit(child, f"{path}.{key}" if path else str(key), depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value[:25]):
                visit(child, f"{path}[{index}]", depth + 1)

    visit(record, "", 0)
    unique: dict[tuple[float, float, str, str], dict[str, Any]] = {}
    for item in found:
        key = (item["latitude"], item["longitude"], item["path"], item["kind"])
        unique[key] = item
    return list(unique.values())


def _raw_index(raw_records: Iterable[SnapshotRecord]) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, Any]]:
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_artifact: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total = 0
    with_pairs = 0
    key_paths: Counter[str] = Counter()

    for wrapped in raw_records:
        total += 1
        record = wrapped.record
        identity = source_identity(record)
        if all(identity):
            index[identity].append(record)
        pairs = find_coordinate_pairs(record)
        by_artifact[wrapped.artifact_path]["records"] += 1
        if pairs:
            with_pairs += 1
            by_artifact[wrapped.artifact_path]["records_with_coordinate_pairs"] += 1
            for pair in pairs:
                key_paths[f"{wrapped.artifact_path}:{pair['path']}:{pair['kind']}"] += 1
            if len(examples[wrapped.artifact_path]) < 5:
                examples[wrapped.artifact_path].append(
                    {"source_identity": identity, "coordinate_pairs": pairs[:3]}
                )

    diagnostic = {
        "total_raw_records": total,
        "records_with_coordinate_pairs": with_pairs,
        "records_without_coordinate_pairs": total - with_pairs,
        "by_artifact": {
            artifact: {**dict(counts), "examples": examples.get(artifact, [])}
            for artifact, counts in sorted(by_artifact.items())
        },
        "coordinate_key_paths": _counter_dict(key_paths),
    }
    return index, diagnostic


def _source_borough_from_raw(raw_matches: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    candidates: set[str] = set()
    sources: set[str] = set()
    for raw in raw_matches:
        for field in ("borough", "event_borough", "boroughs"):
            borough = _canonical_borough(raw.get(field))
            if borough:
                candidates.add(borough)
                sources.add(field)
    if len(candidates) != 1:
        return None, None
    return next(iter(candidates)), "+".join(sorted(sources)) or "raw_source"


def build_unresolved_diagnostics(
    review_list_only: list[dict[str, Any]],
    raw_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Diagnose classifier-produced unresolved list-only occurrences without promotion."""
    source_distribution: Counter[str] = Counter()
    evidence_reasons: Counter[str] = Counter()
    pipeline_reasons: Counter[str] = Counter()
    facility_counts: Counter[str] = Counter()
    relational_counts: Counter[str] = Counter()
    unique_identities: set[tuple[str, str]] = set()
    unique_identities_with_raw_coordinates: set[tuple[str, str]] = set()
    samples: list[dict[str, Any]] = []

    diagnostics: dict[str, Any] = {
        "total_unresolved": 0,
        "location_text": {"present": 0, "empty": 0},
        "borough_state": {"null": 0, "populated": 0},
        "facility_within_park_candidates": 0,
        "duplicate_facility_container": 0,
        "raw_to_projected_coordinate_trace": {
            "raw_identity_match_occurrences": 0,
            "raw_identity_missing_occurrences": 0,
            "unresolved_occurrences_with_raw_coordinates": 0,
            "unresolved_occurrences_with_projected_coordinates": 0,
            "coordinate_loss_candidate_occurrences": 0,
            "unique_source_identities": 0,
            "unique_source_identities_with_raw_coordinates": 0,
            "parks_unresolved_occurrences": 0,
            "parks_raw_identity_match_occurrences": 0,
            "parks_occurrences_with_raw_coordinates": 0,
            "parks_occurrences_with_projected_coordinates": 0,
            "parks_coordinate_loss_candidate_occurrences": 0,
        },
        "promotion_allowed": False,
    }

    for item in review_list_only:
        if item.get("evidence_tier") != "unresolved":
            continue

        diagnostics["total_unresolved"] += 1
        dataset = str(item.get("source_dataset") or "unknown")
        source_event_id = str(item.get("source_event_id") or "")
        identity = (dataset, source_event_id)
        if all(identity):
            unique_identities.add(identity)
        source_distribution[dataset] += 1

        location = str(item.get("location") or "").strip()
        title = str(item.get("title") or "").strip()
        text = location or title
        if location:
            diagnostics["location_text"]["present"] += 1
        else:
            diagnostics["location_text"]["empty"] += 1

        if item.get("borough"):
            diagnostics["borough_state"]["populated"] += 1
        else:
            diagnostics["borough_state"]["null"] += 1

        facility_hit = False
        for name, pattern in _FACILITY_PATTERNS.items():
            if pattern.search(text):
                facility_counts[name] += 1
                facility_hit = True
        if facility_hit:
            facility_counts["any_facility"] += 1

        relational_hit = False
        for name, pattern in _RELATIONAL_PATTERNS.items():
            if pattern.search(text):
                relational_counts[name] += 1
                relational_hit = True
        if relational_hit:
            relational_counts["any_relational"] += 1

        parts = _CONTAINER_SPLIT_PATTERN.split(text, maxsplit=1)
        if len(parts) == 2:
            sub_facility = parts[0].strip()
            container = parts[1].strip()
            if (
                sub_facility
                and container
                and sub_facility.casefold() != container.casefold()
                and (
                    _FACILITY_PATTERNS["park"].search(container)
                    or _FACILITY_PATTERNS["playground"].search(container)
                )
            ):
                diagnostics["facility_within_park_candidates"] += 1
        if _DUPLICATE_CONTAINER_PATTERN.fullmatch(text):
            diagnostics["duplicate_facility_container"] += 1

        evidence_reasons[str(item.get("evidence_reason") or "none")] += 1
        reason_fields = item.get("pipeline_reason_fields")
        if isinstance(reason_fields, dict) and reason_fields:
            for field, value in sorted(reason_fields.items()):
                pipeline_reasons[f"{field}:{value}"] += 1
        else:
            pipeline_reasons["none_recorded"] += 1

        raw_matches = raw_index.get(identity, []) if all(identity) else []
        raw_pairs = [pair for raw in raw_matches for pair in find_coordinate_pairs(raw)]
        projected_pairs = item.get("projected_coordinate_pairs")
        if not isinstance(projected_pairs, list):
            projected_pairs = []

        trace = diagnostics["raw_to_projected_coordinate_trace"]
        is_parks = "parks" in dataset.casefold() or "bigapps" in dataset.casefold()
        if is_parks:
            trace["parks_unresolved_occurrences"] += 1

        if raw_matches:
            trace["raw_identity_match_occurrences"] += 1
            if is_parks:
                trace["parks_raw_identity_match_occurrences"] += 1
        else:
            trace["raw_identity_missing_occurrences"] += 1

        if raw_pairs:
            trace["unresolved_occurrences_with_raw_coordinates"] += 1
            if all(identity):
                unique_identities_with_raw_coordinates.add(identity)
            if is_parks:
                trace["parks_occurrences_with_raw_coordinates"] += 1
        if projected_pairs:
            trace["unresolved_occurrences_with_projected_coordinates"] += 1
            if is_parks:
                trace["parks_occurrences_with_projected_coordinates"] += 1
        if raw_pairs and not projected_pairs:
            trace["coordinate_loss_candidate_occurrences"] += 1
            if is_parks:
                trace["parks_coordinate_loss_candidate_occurrences"] += 1

        if len(samples) < 20:
            samples.append(
                {
                    "id": item.get("id"),
                    "title": title[:80],
                    "location": location[:140],
                    "source_dataset": dataset,
                    "source_event_id": source_event_id,
                    "borough": item.get("borough"),
                    "evidence_reason": item.get("evidence_reason"),
                    "pipeline_reason_fields": reason_fields or {},
                    "raw_identity_matches": len(raw_matches),
                    "raw_coordinate_pair_count": len(raw_pairs),
                    "projected_coordinate_pair_count": len(projected_pairs),
                }
            )

    trace = diagnostics["raw_to_projected_coordinate_trace"]
    trace["unique_source_identities"] = len(unique_identities)
    trace["unique_source_identities_with_raw_coordinates"] = len(
        unique_identities_with_raw_coordinates
    )
    diagnostics["source_dataset_distribution"] = _counter_dict(source_distribution)
    diagnostics["evidence_reason_distribution"] = _counter_dict(evidence_reasons)
    diagnostics["resolver_pipeline_reason_distribution"] = _counter_dict(pipeline_reasons)
    diagnostics["facility_terminology"] = {
        key: facility_counts.get(key, 0)
        for key in (
            "any_facility",
            "park",
            "playground",
            "pool",
            "recreation_center",
            "field",
            "court",
            "visitor_center",
            "nature_center",
            "gymnasium",
        )
    }
    diagnostics["relational_patterns"] = {
        key: relational_counts.get(key, 0)
        for key in ("any_relational", "in_phrase", "at_phrase", "entrance_to")
    }
    diagnostics["representative_samples"] = samples
    return diagnostics


def render_unresolved_markdown(diagnostics: dict[str, Any]) -> str:
    location = diagnostics["location_text"]
    borough = diagnostics["borough_state"]
    facility = diagnostics["facility_terminology"]
    relational = diagnostics["relational_patterns"]
    trace = diagnostics["raw_to_projected_coordinate_trace"]
    lines = [
        "# SHADOW-2 Unresolved Diagnostics",
        "",
        "Read-only diagnostic. No coordinates, statuses, promotion flags, feeds, or map state were modified.",
        "",
        "## Summary",
        "",
        f"- Total unresolved list-only occurrences: **{diagnostics['total_unresolved']:,}**",
        f"- Location text present: **{location['present']:,}**",
        f"- Location text empty: **{location['empty']:,}**",
        f"- Borough null: **{borough['null']:,}**",
        f"- Borough populated: **{borough['populated']:,}**",
        f"- Facility terminology: **{facility['any_facility']:,}**",
        f"- Facility-within-park candidates: **{diagnostics['facility_within_park_candidates']:,}**",
        f"- Duplicate facility/container names: **{diagnostics['duplicate_facility_container']:,}**",
        "",
        "## Source distribution",
        "",
    ]
    for source, count in diagnostics["source_dataset_distribution"].items():
        lines.append(f"- `{source}`: **{count:,}**")
    lines.extend(["", "## Facility terminology", ""])
    for name, count in facility.items():
        lines.append(f"- `{name}`: **{count:,}**")
    lines.extend(["", "## Relational patterns", ""])
    for name, count in relational.items():
        lines.append(f"- `{name}`: **{count:,}**")
    lines.extend(["", "## Raw-to-projected coordinate trace", ""])
    for name, count in trace.items():
        lines.append(f"- `{name}`: **{count:,}**")
    lines.extend(
        [
            "",
            "## Interpretation gate",
            "",
            "A coordinate-loss candidate means a matched raw source record contains an explicit coordinate pair while the projected unresolved occurrence does not. It is a repair lead, not authorization to promote or publish the occurrence.",
            "",
        ]
    )
    return "\n".join(lines)


def build_audit(snapshot: ReadOnlySnapshot) -> dict[str, Any]:
    approved = list(snapshot.read_approved_events())
    review = list(snapshot.read_review_events())
    raw = list(snapshot.read_raw_snapshots())
    raw_index, raw_coordinate_diagnostic = _raw_index(raw)

    total_tiers: Counter[str] = Counter()
    tiers_by_collection: dict[str, Counter[str]] = defaultdict(Counter)
    status_by_collection: dict[str, Counter[str]] = defaultdict(Counter)
    malformed: list[dict[str, Any]] = []
    review_list_only: list[dict[str, Any]] = []
    repair_queue: list[dict[str, Any]] = []

    for wrapped in [*approved, *review]:
        record = wrapped.record
        try:
            evidence = classify_location_evidence(record)
            tier = evidence.tier.value
            evidence_reason = evidence.reason_code.value if evidence.reason_code else None
        except Exception as exc:
            tier = "malformed"
            evidence_reason = "CLASSIFICATION_FAILED"
            malformed.append(
                {
                    "id": record.get("id"),
                    "artifact_path": wrapped.artifact_path,
                    "record_index": wrapped.record_index,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

        total_tiers[tier] += 1
        tiers_by_collection[wrapped.collection][tier] += 1
        status = coordinate_status(record)
        status_by_collection[wrapped.collection][status] += 1

        if wrapped.collection != "review" or status != "list_only":
            continue

        dataset, source_event_id = source_identity(record)
        borough = _canonical_borough(record.get("borough"))
        inferred_borough = None
        inference_source = None
        if borough is None:
            inferred_borough, inference_source = _source_borough_from_raw(
                raw_index.get((dataset, source_event_id), [])
            )
            if inferred_borough is None:
                inferred_borough, inference_source = infer_borough(record)

        item = {
            "id": record.get("id"),
            "title": record.get("title"),
            "location": record.get("location") or record.get("display_location"),
            "borough": borough,
            "source_dataset": dataset,
            "source_event_id": source_event_id,
            "coordinate_status": status,
            "evidence_tier": tier,
            "evidence_reason": evidence_reason,
            "projected_coordinate_pairs": find_coordinate_pairs(record),
            "pipeline_reason_fields": {
                key: record.get(key)
                for key in (
                    "review_reason",
                    "approval_decision_reason",
                    "exclusion_reason",
                    "pipeline_reason",
                    "resolver_reason",
                    "match_type",
                    "location_source",
                )
                if record.get(key) not in (None, "")
            },
            "borough_inference": {
                "candidate": inferred_borough,
                "source": inference_source,
            },
            "promotion_allowed": False,
        }
        review_list_only.append(item)

        if inferred_borough:
            repair_queue.append(
                {
                    "id": item["id"],
                    "source_dataset": dataset,
                    "source_event_id": source_event_id,
                    "repair_type": "populate_missing_borough",
                    "proposed_borough": inferred_borough,
                    "evidence_source": inference_source,
                    "coordinate_change": False,
                    "coordinate_status_change": False,
                    "promotion_allowed": False,
                    "requires_rebuild_and_reaudit": True,
                }
            )

    list_only_tiers = Counter(item["evidence_tier"] for item in review_list_only)
    list_only_reasons = Counter(str(item["evidence_reason"] or "none") for item in review_list_only)
    list_only_sources = Counter(item["source_dataset"] or "unknown" for item in review_list_only)
    borough_null = sum(item["borough"] is None for item in review_list_only)
    borough_candidates = sum(bool(item["borough_inference"]["candidate"]) for item in review_list_only)
    unresolved_diagnostics = build_unresolved_diagnostics(review_list_only, raw_index)

    classified_occurrences = len(approved) + len(review)
    raw_records = len(raw)
    reconciliation = {
        "classified_occurrences": classified_occurrences,
        "approved_occurrences": len(approved),
        "review_occurrences": len(review),
        "raw_source_records": raw_records,
        "occurrence_minus_raw_delta": classified_occurrences - raw_records,
        "status": "requires_occurrence_expansion_contract",
        "note": (
            "Approved/review artifacts contain dated occurrences while raw snapshots may contain source records. "
            "The delta is not proof of loss or duplication until a source-record-to-occurrence expansion manifest is reconciled."
        ),
    }

    return {
        "schema_version": "shadow2-real-data-audit-v3",
        "safety": {
            "read_only": True,
            "production_feeds_modified": False,
            "public_map_modified": False,
            "coordinates_modified": False,
            "promotion_allowed": False,
        },
        "input_totals": {
            "approved_events": len(approved),
            "review_events": len(review),
            "classified_events": classified_occurrences,
            "raw_snapshot_files": len(snapshot.raw_snapshot_paths()),
            "raw_records": raw_records,
        },
        "evidence_distribution": {
            "total": {tier: total_tiers.get(tier, 0) for tier in TIERS},
            "by_collection": {
                collection: {tier: counts.get(tier, 0) for tier in TIERS}
                for collection, counts in sorted(tiers_by_collection.items())
            },
        },
        "coordinate_status_distribution": {
            collection: _counter_dict(counts)
            for collection, counts in sorted(status_by_collection.items())
        },
        "review_list_only": {
            "count": len(review_list_only),
            "tier_distribution": _counter_dict(list_only_tiers),
            "evidence_reason_distribution": _counter_dict(list_only_reasons),
            "source_distribution": _counter_dict(list_only_sources),
            "borough_null_count": borough_null,
            "borough_repair_candidate_count": borough_candidates,
            "records": review_list_only,
        },
        "unresolved_diagnostics": unresolved_diagnostics,
        "repair_queue": repair_queue,
        "malformed_records": malformed,
        "raw_coordinate_diagnostic": raw_coordinate_diagnostic,
        "reconciliation": reconciliation,
        "interpretation_guards": [
            "A location-evidence tier is a claim classification, not semantic certification.",
            "SEGMENT_UNCERTIFIED is an Enigma evidence reason, not necessarily the pipeline demotion reason.",
            "The total certified_street_segment count must not be reported as the review list-only segment count.",
            "Borough repair alone must not change coordinates, coordinate_status, or promotion_allowed.",
            "A raw-to-projected coordinate-loss candidate is a repair lead, not authorization to promote an event.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    totals = report["input_totals"]
    evidence = report["evidence_distribution"]["total"]
    list_only = report["review_list_only"]
    unresolved = report.get("unresolved_diagnostics", {})
    recon = report["reconciliation"]
    raw_diag = report["raw_coordinate_diagnostic"]

    lines = [
        "# SHADOW-2 Real-Data Audit — Step 2",
        "",
        "## Safety",
        "",
        "Read-only. No coordinates, production feeds, public map state, or promotion flags were modified.",
        "",
        "## Input totals",
        "",
        f"- Approved occurrences: **{totals['approved_events']:,}**",
        f"- Review occurrences: **{totals['review_events']:,}**",
        f"- Classified occurrences: **{totals['classified_events']:,}**",
        f"- Raw source records: **{totals['raw_records']:,}** across **{totals['raw_snapshot_files']}** files",
        "",
        "## Evidence distribution",
        "",
        "| Tier | Count |",
        "|---|---:|",
    ]
    for tier in TIERS:
        lines.append(f"| `{tier}` | {evidence.get(tier, 0):,} |")

    lines.extend(
        [
            "",
            "## Review list-only findings",
            "",
            f"- Total list-only review occurrences: **{list_only['count']:,}**",
            f"- Street-segment claims in list-only review: **{list_only['tier_distribution'].get('certified_street_segment', 0):,}**",
            f"- Missing borough in list-only review: **{list_only['borough_null_count']:,}**",
            f"- Deterministic borough repair candidates: **{list_only['borough_repair_candidate_count']:,}**",
            "",
            "The total `certified_street_segment` count across approved and review records is not the same as the list-only review segment count. `SEGMENT_UNCERTIFIED` describes unvalidated segment evidence; it does not mean Enigma has certified a map-safe pin.",
            "",
            "### List-only tiers",
            "",
            "| Tier | Count |",
            "|---|---:|",
        ]
    )
    for tier, count in list_only["tier_distribution"].items():
        lines.append(f"| `{tier}` | {count:,} |")

    if unresolved:
        trace = unresolved["raw_to_projected_coordinate_trace"]
        lines.extend(
            [
                "",
                "## Unresolved diagnostics",
                "",
                f"- Unresolved list-only occurrences: **{unresolved['total_unresolved']:,}**",
                f"- Location text present: **{unresolved['location_text']['present']:,}**",
                f"- Location text empty: **{unresolved['location_text']['empty']:,}**",
                f"- Facility terminology: **{unresolved['facility_terminology']['any_facility']:,}**",
                f"- Facility-within-park candidates: **{unresolved['facility_within_park_candidates']:,}**",
                f"- Raw-coordinate loss candidates: **{trace['coordinate_loss_candidate_occurrences']:,}**",
                f"- Parks raw-coordinate loss candidates: **{trace['parks_coordinate_loss_candidate_occurrences']:,}**",
            ]
        )

    lines.extend(
        [
            "",
            "## Raw coordinate diagnostic",
            "",
            f"- Raw records containing an explicit coordinate pair: **{raw_diag['records_with_coordinate_pairs']:,}**",
            f"- Raw records without an explicit coordinate pair: **{raw_diag['records_without_coordinate_pairs']:,}**",
            "",
            "## Reconciliation",
            "",
            f"- Occurrence minus raw-record delta: **{recon['occurrence_minus_raw_delta']:+,}**",
            f"- Status: `{recon['status']}`",
            "",
            recon["note"],
            "",
            "## Safe implementation gate",
            "",
            "Borough repairs and coordinate-retention diagnostics are data-shape investigations only. Rebuild and rerun SHADOW-2 before considering any coordinate-status change, promotion, approximate-marker layer, or public map change.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "complete_json": output_dir / "shadow2-real-data-audit.json",
        "markdown": output_dir / "shadow2-real-data-audit.md",
        "review_list_only": output_dir / "shadow2-audit-review-list-only.json",
        "repair_queue": output_dir / "shadow2-repair-queue.json",
        "raw_coordinate_diagnostic": output_dir / "shadow2-raw-coordinate-diagnostic.json",
    }
    unresolved = report.get("unresolved_diagnostics")
    if unresolved:
        paths["unresolved_diagnostics_json"] = output_dir / "shadow2-unresolved-diagnostics.json"
        paths["unresolved_diagnostics_markdown"] = output_dir / "shadow2-unresolved-diagnostics.md"
    paths["complete_json"].write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["markdown"].write_text(render_markdown(report), encoding="utf-8")
    paths["review_list_only"].write_text(
        json.dumps(report["review_list_only"]["records"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["repair_queue"].write_text(
        json.dumps(report["repair_queue"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["raw_coordinate_diagnostic"].write_text(
        json.dumps(report["raw_coordinate_diagnostic"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if unresolved:
        paths["unresolved_diagnostics_json"].write_text(
            json.dumps(unresolved, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        paths["unresolved_diagnostics_markdown"].write_text(
            render_unresolved_markdown(unresolved),
            encoding="utf-8",
        )
    return {key: str(path) for key, path in paths.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/shadow2-audit"))
    args = parser.parse_args(argv)

    report = build_audit(ReadOnlySnapshot())
    paths = write_reports(report, args.output_dir)
    unresolved = report["unresolved_diagnostics"]
    trace = unresolved["raw_to_projected_coordinate_trace"]
    summary = {
        "qa_pass": not report["malformed_records"],
        "review_list_only_count": report["review_list_only"]["count"],
        "review_list_only_segment_count": report["review_list_only"]["tier_distribution"].get(
            "certified_street_segment", 0
        ),
        "borough_repair_candidate_count": report["review_list_only"]["borough_repair_candidate_count"],
        "unresolved_count": unresolved["total_unresolved"],
        "unresolved_location_present": unresolved["location_text"]["present"],
        "unresolved_facility_terminology": unresolved["facility_terminology"]["any_facility"],
        "coordinate_loss_candidate_occurrences": trace["coordinate_loss_candidate_occurrences"],
        "parks_coordinate_loss_candidate_occurrences": trace[
            "parks_coordinate_loss_candidate_occurrences"
        ],
        "raw_records_with_coordinate_pairs": report["raw_coordinate_diagnostic"][
            "records_with_coordinate_pairs"
        ],
        "outputs": paths,
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
