#!/usr/bin/env python3
"""Dedupe approved discovery events after supplemental fold/merge."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from typing import Any, Mapping, Sequence

COORD_EPSILON_M = 80.0


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _event_day(event: dict[str, Any]) -> str:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return str(nycif.get("event_date") or event.get("start_date_time") or "")[:10]


def _has_coords(event: dict[str, Any]) -> bool:
    lat = event.get("latitude")
    lng = event.get("longitude")
    if lat is None or lng is None:
        return False
    try:
        float(lat)
        float(lng)
    except (TypeError, ValueError):
        return False
    return True


def _coord_distance_m(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    if not _has_coords(a) or not _has_coords(b):
        return None
    lat1 = math.radians(float(a["latitude"]))
    lng1 = math.radians(float(a["longitude"]))
    lat2 = math.radians(float(b["latitude"]))
    lng2 = math.radians(float(b["longitude"]))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _event_priority(event: dict[str, Any]) -> int:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    score = 0
    if nycif.get("coordinate_status") == "map_ready" and _has_coords(event):
        score += 200
    if str(nycif.get("manual_review_status") or "").lower() == "approved":
        score += 120
    if nycif.get("data_layer") == "approved_staged" and not str(event.get("id") or "").startswith(
        "review_supplemental:"
    ):
        score += 80
    if nycif.get("supplemental_merge_authorized"):
        score += 60
    if nycif.get("public_supplemental"):
        score += 10
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    if str(source.get("dataset") or "").startswith("nyc-open-data"):
        score += 40
    return score


def supplemental_fold_eligible(event: dict[str, Any]) -> bool:
    """Only fold human-approved or map-ready official supplemental rows into approved."""
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    status = str(nycif.get("manual_review_status") or "").lower()
    if status in {"pending", "rejected"}:
        return False
    if status == "approved":
        return True
    return nycif.get("coordinate_status") == "map_ready" and _has_coords(event)


def _duplicate_group_key(event: dict[str, Any]) -> tuple[str, ...] | None:
    title = _norm_text(event.get("title"))
    day = _event_day(event)
    if not title or not day:
        return None
    if _has_coords(event):
        return (
            "coord",
            title,
            day,
            f"{float(event['latitude']):.4f}",
            f"{float(event['longitude']):.4f}",
        )
    location = _norm_text(event.get("location") or event.get("address"))
    if location:
        return ("loc", title, day, location)
    return None


def _is_supplemental_related(event: dict[str, Any]) -> bool:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    eid = str(event.get("id") or "")
    if eid.startswith("review_supplemental:"):
        return True
    if nycif.get("public_supplemental"):
        return True
    if nycif.get("supplemental_merge_authorized"):
        return True
    if nycif.get("supplemental_from"):
        return True
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    dataset = str(source.get("dataset") or "").lower()
    return dataset in {
        "nyc-citywide-events-calendar-api",
        "nyc-parks-bigapps-events",
        "nyc_parks_bigapps_events_snapshot",
    }


def _supplemental_bucket(event: dict[str, Any]) -> tuple[str, str] | None:
    title = _norm_text(event.get("title"))
    day = _event_day(event)
    if not title or not day:
        return None
    return (title, day)


def _locations_compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    dist = _coord_distance_m(a, b)
    if dist is not None and dist <= COORD_EPSILON_M:
        return True
    loc_a = _norm_text(a.get("location") or a.get("address"))
    loc_b = _norm_text(b.get("location") or b.get("address"))
    if loc_a and loc_b and (loc_a == loc_b or loc_a in loc_b or loc_b in loc_a):
        return True
    nycif_a = a.get("nycif") if isinstance(a.get("nycif"), dict) else {}
    nycif_b = b.get("nycif") if isinstance(b.get("nycif"), dict) else {}
    statuses = {nycif_a.get("coordinate_status"), nycif_b.get("coordinate_status")}
    if statuses == {"list_only", "map_ready"}:
        return True
    return False


def dedupe_approved_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop weaker cross-source supplemental duplicates while preserving permit rows."""
    kept: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str], list[int]] = {}
    removed: list[dict[str, Any]] = []

    for event in events:
        if not _is_supplemental_related(event):
            kept.append(event)
            continue

        bucket = _supplemental_bucket(event)
        if bucket is None:
            kept.append(event)
            continue

        candidate_indexes = buckets.get(bucket, [])
        replace_idx = None
        for idx in candidate_indexes:
            current = kept[idx]
            if not _is_supplemental_related(current):
                continue
            if not _locations_compatible(current, event):
                continue
            replace_idx = idx
            break

        if replace_idx is None:
            buckets.setdefault(bucket, []).append(len(kept))
            kept.append(event)
            continue

        current = kept[replace_idx]
        if _event_priority(event) > _event_priority(current):
            removed.append(
                {
                    "dropped_id": current.get("id"),
                    "kept_id": event.get("id"),
                    "title": event.get("title"),
                    "date": bucket[1],
                    "reason": "lower_priority_supplemental_duplicate",
                }
            )
            kept[replace_idx] = event
        else:
            removed.append(
                {
                    "dropped_id": event.get("id"),
                    "kept_id": current.get("id"),
                    "title": event.get("title"),
                    "date": bucket[1],
                    "reason": "lower_priority_supplemental_duplicate",
                }
            )

    stats = {
        "input_count": len(events),
        "output_count": len(kept),
        "removed_duplicate_count": len(removed),
        "sample_removed": removed[:25],
    }
    return kept, stats

# ---------------------------------------------------------------------------
# V1 Batch 2A: same-source shared-CEMS occurrence projection deduplication.
# This logic is deliberately separate from the supplemental cross-source rule
# above. It preserves source observations and removes only redundant public
# projections that satisfy the complete bounded contract.
# ---------------------------------------------------------------------------

SHARED_CEMS_TARGET_DATASET = "tvpp-9vvx"
SHARED_CEMS_CONTRACT_VERSION = "shared-cems-occurrence-v1"
SHARED_CEMS_PRIVATE_REPORT_PATH = (
    "data/reports/discovery_shared_cems_occurrence_dedupe_report.json"
)
SHARED_CEMS_PUBLIC_SUMMARY_PATH = (
    "data/schema-v1-discovery/shared-cems-occurrence-dedupe-summary.json"
)
SHARED_CEMS_PUBLIC_SUMMARY_STATS = (
    ("input_count", "input_count"),
    ("output_count", "output_count"),
    ("safe_group_count", "group_count"),
    ("safe_group_member_count", "group_member_count"),
    ("representative_count", "representative_count"),
    ("suppressed_projection_count", "suppressed_projection_count"),
    ("blocked_group_count", "blocked_group_count"),
    ("blocked_record_count", "blocked_record_count"),
    ("fatal_blocked_group_count", "fatal_blocked_group_count"),
    ("qa_pass", "qa_pass"),
)
SHARED_CEMS_PROHIBITED_PUBLIC_KEYS = frozenset(
    {
        "groups",
        "blocked_groups",
        "source_references",
        "source_identity",
        "source_event_id",
        "source_cemsid",
        "cemsids",
        "public_event_payload",
        "raw_source_evidence",
        "all_committed_source_evidence",
    }
)


def build_shared_cems_public_summary(
    stats: Mapping[str, Any],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Build the explicitly allowlisted public Batch 2A summary."""

    summary = {
        "artifact_type": "discovery_shared_cems_occurrence_dedupe_summary",
        "generated_at_utc": generated_at_utc,
        "contract_version": stats["contract_version"],
        "target_dataset": stats["target_dataset"],
    }
    summary.update(
        {
            public_name: stats[stats_name]
            for public_name, stats_name in SHARED_CEMS_PUBLIC_SUMMARY_STATS
        }
    )
    return summary


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _source_identity(value: Mapping[str, Any]) -> tuple[str, str]:
    dataset = str(value.get("source_dataset") or "").strip()
    source_event_id = str(value.get("source_event_id") or "").strip()
    source = value.get("source")
    if isinstance(source, Mapping):
        dataset = dataset or str(source.get("dataset") or source.get("source_dataset") or "").strip()
        source_event_id = source_event_id or str(
            source.get("source_event_id") or source.get("event_id") or source.get("id") or ""
        ).strip()
    return dataset, source_event_id


def _extract_cemsids(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, (list, tuple, set)):
        for item in value:
            result.update(_extract_cemsids(item))
        return result
    if value in (None, "", 0, "0"):
        return result
    text = str(value).strip()
    if not text or text == "0":
        return result
    for part in re.split(r"[,;|]", text):
        cleaned = part.strip()
        if cleaned and cleaned != "0":
            result.add(cleaned)
    return result


def build_cems_source_lookup(
    source_rows_by_artifact: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[
    dict[tuple[str, str], frozenset[str]],
    dict[tuple[str, str], tuple[dict[str, Any], ...]],
]:
    """Build private CEMS and immutable source-evidence lookups.

    The lookup is derived only from committed raw/staged inputs supplied by the
    caller. CEMS identifiers are not copied into canonical public events.
    """

    cemsids: dict[tuple[str, str], set[str]] = defaultdict(set)
    evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for artifact in sorted(source_rows_by_artifact):
        rows = source_rows_by_artifact[artifact]
        for row_index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            key = _source_identity(row)
            if not key[0] or not key[1]:
                continue
            row_cemsids = _extract_cemsids(row.get("source_cemsid"))
            cemsids[key].update(row_cemsids)
            evidence[key].append(
                {
                    "artifact": artifact,
                    "row_index": row_index,
                    "row_sha256": _sha256_json(row),
                    "cemsids": sorted(row_cemsids),
                }
            )

    frozen_cemsids = {
        key: frozenset(values)
        for key, values in cemsids.items()
        if values
    }
    frozen_evidence = {
        key: tuple(items)
        for key, items in evidence.items()
    }
    return frozen_cemsids, frozen_evidence


def _time_block_component(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"[T ](\d{2}:\d{2}(?::\d{2})?)", text)
    if match:
        component = match.group(1)
        return component if len(component) == 8 else component + ":00"
    if re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", text):
        return text if len(text) == 8 else text + ":00"
    return ""


def _shared_cems_contract(event: Mapping[str, Any]) -> tuple[Any, ...] | None:
    dataset, source_event_id = _source_identity(event)
    if dataset != SHARED_CEMS_TARGET_DATASET or not source_event_id:
        return None
    title = _norm_text(event.get("title"))
    day = _event_day(dict(event))
    start_time = _time_block_component(event.get("start_date_time"))
    end_time = _time_block_component(event.get("end_date_time"))
    location = _norm_text(event.get("location") or event.get("address"))
    if not title or not day or not start_time or not end_time or not location or not _has_coords(dict(event)):
        return None
    return (
        dataset,
        day,
        title,
        start_time,
        end_time,
        location,
        round(float(event["latitude"]), 6),
        round(float(event["longitude"]), 6),
    )


def _display_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return the bounded user-visible payload for fail-closed comparison."""

    top_level_fields = (
        "schema_version",
        "title",
        "description",
        "category",
        "interests",
        "tags",
        "event_role",
        "significance",
        "audience",
        "start_date_time",
        "end_date_time",
        "timezone",
        "borough",
        "neighborhood",
        "location",
        "address",
        "latitude",
        "longitude",
        "parent_event_id",
    )
    nycif_fields = (
        "data_layer",
        "coordinate_status",
        "display_disposition",
        "is_major",
        "photo_pick",
        "field_default",
        "crowd_level",
        "priority_score",
        "expected_crowd_score",
        "event_date",
        "event_type",
        "event_agency",
    )
    nycif = event.get("nycif") if isinstance(event.get("nycif"), Mapping) else {}
    return {
        "event": {field: event.get(field) for field in top_level_fields},
        "nycif": {field: nycif.get(field) for field in nycif_fields},
    }


def _representative_sort_key(event: Mapping[str, Any]) -> tuple[Any, ...]:
    _, source_event_id = _source_identity(event)
    canonical_id = str(event.get("id") or "")
    if source_event_id.isdigit():
        return (0, int(source_event_id), canonical_id)
    return (1, 0, canonical_id)


def _external_member_references(
    events: Sequence[Mapping[str, Any]],
    member_set: frozenset[int],
) -> list[dict[str, str]]:
    """Find retained records that depend on a candidate member identity."""

    member_ids = {
        str(events[index].get("id") or "")
        for index in member_set
        if events[index].get("id")
    }
    references: list[dict[str, str]] = []
    for index, event in enumerate(events):
        if index in member_set:
            continue
        for field in ("parent_event_id", "event_group_id"):
            target_id = str(event.get(field) or "")
            if target_id in member_ids:
                references.append(
                    {
                        "referrer_id": str(event.get("id") or ""),
                        "field": field,
                        "target_id": target_id,
                    }
                )
    return sorted(
        references,
        key=lambda item: (
            item["target_id"],
            item["referrer_id"],
            item["field"],
        ),
    )


def _source_reference(
    event: Mapping[str, Any],
    cemsids_by_source: Mapping[tuple[str, str], frozenset[str]],
    evidence_by_source: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    dataset, source_event_id = _source_identity(event)
    evidence = [dict(item) for item in evidence_by_source.get((dataset, source_event_id), ())]
    raw_evidence = [item for item in evidence if item.get("artifact") == "data/raw_nyc_open_data_snapshot.json"]
    return {
        "canonical_id": str(event.get("id") or ""),
        "source_identity": {
            "dataset": dataset,
            "source_event_id": source_event_id,
        },
        "cemsids": sorted(cemsids_by_source.get((dataset, source_event_id), frozenset())),
        "public_record_sha256": _sha256_json(event),
        "public_event_payload": _display_payload(event),
        "raw_source_evidence": raw_evidence,
        "all_committed_source_evidence": evidence,
    }


def _flatten_display_payload(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, Mapping):
        for key in sorted(value):
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_display_payload(value[key], child))
        return flattened
    flattened[prefix] = value
    return flattened


def _display_payload_differences(events: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        (str(event.get("id") or ""), _flatten_display_payload(_display_payload(event)))
        for event in events
    ]
    fields = sorted({field for _, payload in rows for field in payload})
    differences: list[dict[str, Any]] = []
    for field in fields:
        values = [
            {"id": event_id, "value": payload.get(field)}
            for event_id, payload in rows
        ]
        if len({_sha256_json(item["value"]) for item in values}) > 1:
            differences.append({"field": field, "values": values})
    return differences


def _payload_block_classification(differences: Sequence[Mapping[str, Any]]) -> str:
    if len(differences) == 1 and differences[0].get("field") == "nycif.event_type":
        values = {
            str(item.get("value") or "").strip().lower()
            for item in differences[0].get("values", [])
            if isinstance(item, Mapping)
        }
        if values == {"sport - adult", "sport - youth"}:
            return "blocked_event_type_conflict"
    return "blocked_user_visible_payload_mismatch"


def dedupe_shared_cems_occurrences(
    events: list[dict[str, Any]],
    cemsids_by_source: Mapping[tuple[str, str], frozenset[str]],
    evidence_by_source: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Suppress redundant same-source occurrence projections, fail closed.

    Eligibility requires the exact Batch 2A contract. The function performs no
    I/O and does not mutate source events or the supplied lookups.
    """

    evidence_by_source = evidence_by_source or {}
    bucket_members: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    event_contracts: dict[int, tuple[Any, ...]] = {}
    eligible_count = 0

    for index, event in enumerate(events):
        contract = _shared_cems_contract(event)
        if contract is None:
            continue
        source_key = _source_identity(event)
        cemsids = cemsids_by_source.get(source_key, frozenset())
        if not cemsids:
            continue
        eligible_count += 1
        event_contracts[index] = contract
        for cemsid in sorted(cemsids):
            bucket_members[(cemsid, *contract)].append(index)

    # A pair may share more than one CEMS value. Collapse identical member sets
    # while preserving every shared CEMS identifier in diagnostics.
    member_sets: dict[frozenset[int], set[str]] = defaultdict(set)
    for bucket, indexes in bucket_members.items():
        unique_indexes = frozenset(indexes)
        if len(unique_indexes) >= 2:
            member_sets[unique_indexes].add(str(bucket[0]))

    memberships_by_event: dict[int, list[frozenset[int]]] = defaultdict(list)
    for member_set in member_sets:
        for index in member_set:
            memberships_by_event[index].append(member_set)
    overlapping_sets = {
        member_set
        for memberships in memberships_by_event.values()
        if len(memberships) > 1
        for member_set in memberships
    }

    suppressed_indexes: set[int] = set()
    groups: list[dict[str, Any]] = []
    blocked_groups: list[dict[str, Any]] = []

    def group_order(item: tuple[frozenset[int], set[str]]) -> tuple[Any, ...]:
        member_set, shared = item
        members = sorted((events[index] for index in member_set), key=_representative_sort_key)
        contract = event_contracts[next(iter(member_set))]
        return (*contract, tuple(str(member.get("id") or "") for member in members), tuple(sorted(shared)))

    for member_set, bucket_cemsids in sorted(member_sets.items(), key=group_order):
        members = [events[index] for index in member_set]
        contracts = {event_contracts[index] for index in member_set}
        source_keys = [_source_identity(event) for event in members]
        cems_intersection: set[str] | None = None
        for source_key in source_keys:
            current = set(cemsids_by_source.get(source_key, frozenset()))
            cems_intersection = current if cems_intersection is None else cems_intersection.intersection(current)
        shared_cemsids = sorted(cems_intersection or set())
        contract = next(iter(contracts)) if len(contracts) == 1 else None

        fatal_reasons: list[str] = []
        if member_set in overlapping_sets:
            fatal_reasons.append("overlapping_candidate_member_sets")
        if contract is None:
            fatal_reasons.append("contract_mismatch")
        if not shared_cemsids:
            fatal_reasons.append("no_single_shared_nonempty_cemsid")

        ordered_members = sorted(members, key=_representative_sort_key)
        payload_differences = _display_payload_differences(ordered_members)
        external_references = _external_member_references(events, member_set)
        if external_references:
            fatal_reasons.append("externally_referenced_candidate_member")
        references = [
            _source_reference(event, cemsids_by_source, evidence_by_source)
            for event in ordered_members
        ]
        if any(not reference["raw_source_evidence"] for reference in references):
            fatal_reasons.append("missing_preserved_raw_source_evidence")

        if fatal_reasons or payload_differences:
            classification = (
                "blocked_contract_integrity_failure"
                if fatal_reasons
                else _payload_block_classification(payload_differences)
            )
            blocked_groups.append(
                {
                    "classification": classification,
                    "reasons": sorted(
                        set(fatal_reasons)
                        | ({"user_visible_payload_mismatch"} if payload_differences else set())
                    ),
                    "shared_cemsids": shared_cemsids or sorted(bucket_cemsids),
                    "member_count": len(ordered_members),
                    "member_ids": [str(event.get("id") or "") for event in ordered_members],
                    "differing_fields": payload_differences,
                    "external_references": external_references,
                    "display_payload_sha256": [
                        {
                            "id": str(event.get("id") or ""),
                            "sha256": _sha256_json(_display_payload(event)),
                        }
                        for event in ordered_members
                    ],
                    "source_references": references,
                }
            )
            continue

        representative = ordered_members[0]
        representative_index = next(index for index in member_set if events[index] is representative)
        suppressed_group_indexes = sorted(index for index in member_set if index != representative_index)
        suppressed_indexes.update(suppressed_group_indexes)

        groups.append(
            {
                "grouping_contract": {
                    "source_dataset": contract[0],
                    "event_date": contract[1],
                    "normalized_title": contract[2],
                    "start_time": contract[3],
                    "end_time": contract[4],
                    "normalized_location": contract[5],
                    "latitude_6dp": contract[6],
                    "longitude_6dp": contract[7],
                    "shared_cemsids": shared_cemsids,
                },
                "member_count": len(ordered_members),
                "representative": _source_reference(
                    representative,
                    cemsids_by_source,
                    evidence_by_source,
                ),
                "suppressed": [
                    _source_reference(events[index], cemsids_by_source, evidence_by_source)
                    for index in suppressed_group_indexes
                ],
            }
        )

    kept = [event for index, event in enumerate(events) if index not in suppressed_indexes]
    member_count = sum(group["member_count"] for group in groups)
    blocked_record_count = sum(group["member_count"] for group in blocked_groups)
    fatal_blocked_group_count = sum(
        1 for group in blocked_groups if group["classification"] == "blocked_contract_integrity_failure"
    )
    stats = {
        "contract_version": SHARED_CEMS_CONTRACT_VERSION,
        "target_dataset": SHARED_CEMS_TARGET_DATASET,
        "representative_rule": "lowest numeric source_event_id; canonical id lexicographic tie-break",
        "input_count": len(events),
        "output_count": len(kept),
        "eligible_event_count": eligible_count,
        "group_count": len(groups),
        "group_member_count": member_count,
        "representative_count": len(groups),
        "suppressed_projection_count": len(suppressed_indexes),
        "blocked_group_count": len(blocked_groups),
        "blocked_record_count": blocked_record_count,
        "fatal_blocked_group_count": fatal_blocked_group_count,
        "qa_pass": fatal_blocked_group_count == 0,
        "groups": groups,
        "blocked_groups": blocked_groups,
    }
    return kept, stats
