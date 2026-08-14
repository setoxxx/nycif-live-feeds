#!/usr/bin/env python3
"""Diagnose why V9 route occurrences do or do not survive canonical projection.

This is read-only evidence tooling. It does not authorize equivalence between
source records. Exact identity remains occurrence_key_v2. Near matches are
reported only as diagnostics and can never satisfy the V10 handoff gate.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.discovery_v02 import extract_rows
    from scripts.occurrence_identity_contract import occurrence_key_v2, identity_precision, source_key
    from scripts.projector_v2_authority import build_rejection_contract, classify_occurrence_intake, rejection_scope_applied
except ModuleNotFoundError:  # pragma: no cover
    from discovery_v02 import extract_rows
    from occurrence_identity_contract import occurrence_key_v2, identity_precision, source_key
    from projector_v2_authority import build_rejection_contract, classify_occurrence_intake, rejection_scope_applied


def _rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return extract_rows(payload)


def _exact_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {
        occurrence_key_v2(row)
        for row in rows
        if identity_precision(row) != "AMBIGUOUS"
    }


def diagnose(
    *,
    v9: dict[str, Any],
    raw_rows: list[dict[str, Any]],
    staged_rows: list[dict[str, Any]],
    supplemental_rows: list[dict[str, Any]],
    disposition_rows: list[dict[str, Any]],
    canonical_rows: list[dict[str, Any]],
    season_start: str,
    season_end: str,
) -> dict[str, Any]:
    targets = {
        tuple(str(v or "").strip() for v in row.get("occurrence_key_v2", [])): row
        for row in (v9.get("registry") or []) if isinstance(row, dict)
    }
    targets = {key: row for key, row in targets.items() if len(key) == 3}

    raw_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        if identity_precision(row) != "AMBIGUOUS":
            raw_by_key[occurrence_key_v2(row)].append(row)

    # Projector V3 raw accounting begins with staged exact identities only.
    # Supplemental identity presence is reported separately because it can affect
    # later approved/dedupe handling but must not be mislabeled as pre-raw intake.
    staged_exact = _exact_keys(staged_rows)
    supplemental_exact = _exact_keys(supplemental_rows)
    contract = build_rejection_contract(disposition_rows)

    canonical_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    canonical_by_source_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    canonical_by_start: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in canonical_rows:
        if identity_precision(event) != "AMBIGUOUS":
            key = occurrence_key_v2(event)
            canonical_by_key[key].append(event)
            canonical_by_start[key[2]].append(event)
        canonical_by_source_id[source_key(event)[1]].append(event)

    buckets: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for key in sorted(targets):
        raw_matches = raw_by_key.get(key, [])
        if len(raw_matches) != 1:
            bucket = "RAW_IDENTITY_NOT_UNIQUE"
            intake_bucket = None
            rejection_scope = None
        else:
            raw = raw_matches[0]
            rejection_scope = rejection_scope_applied(raw, contract)
            intake_bucket = classify_occurrence_intake(
                raw,
                represented_occurrences=staged_exact,
                rejection_contract=contract,
                season_start=season_start,
                season_end=season_end,
            )
            exact_canonical = canonical_by_key.get(key, [])
            if len(exact_canonical) == 1:
                bucket = "EXACT_CANONICAL_MATCH"
            elif len(exact_canonical) > 1:
                bucket = "EXACT_CANONICAL_NOT_UNIQUE"
            elif rejection_scope:
                bucket = f"REJECTED_{rejection_scope}"
            elif key in staged_exact:
                bucket = "PRE_RAW_EXACT_OCCURRENCE_REPRESENTED"
            elif intake_bucket != "accepted_review_supplemental":
                bucket = f"INTAKE_{intake_bucket or 'UNSPECIFIED'}"
            elif key in supplemental_exact:
                bucket = "ACCEPTED_RAW_AND_PRESENT_IN_SUPPLEMENTAL_BUT_NO_EXACT_CANONICAL"
            else:
                bucket = "ACCEPTED_RAW_BUT_NO_EXACT_CANONICAL"

        source_candidates = canonical_by_source_id.get(key[1], [])
        same_start_candidates = canonical_by_start.get(key[2], [])
        rows.append({
            "occurrence_key_v2": list(key),
            "classification": bucket,
            "raw_match_count": len(raw_matches),
            "staged_exact_represented": key in staged_exact,
            "supplemental_exact_present": key in supplemental_exact,
            "rejection_scope": rejection_scope,
            "projector_intake_bucket": intake_bucket,
            "exact_canonical_match_count": len(canonical_by_key.get(key, [])),
            "canonical_same_source_event_id_count": len(source_candidates),
            "canonical_same_start_count": len(same_start_candidates),
            "same_source_event_id_candidates": [
                {
                    "occurrence_key_v2": list(occurrence_key_v2(event)),
                    "canonical_id": event.get("id"),
                    "event_role": event.get("event_role"),
                    "display_disposition": (event.get("nycif") or {}).get("display_disposition") if isinstance(event.get("nycif"), dict) else None,
                    "title": event.get("title"),
                }
                for event in source_candidates[:10]
            ],
        })
        buckets[bucket] += 1

    return {
        "schema_version": "NYCIF_STREET_SEGMENT_ROUTE_CANONICAL_HANDOFF_DIAGNOSTIC_V10",
        "read_only": True,
        "equivalence_authority_granted": False,
        "publication_authority_granted": False,
        "target_occurrence_count": len(targets),
        "classification_counts": dict(sorted(buckets.items())),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v9-registry", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--supplemental", type=Path, required=True)
    parser.add_argument("--dispositions", type=Path, required=True)
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--season-start", required=True)
    parser.add_argument("--season-end", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = diagnose(
        v9=json.loads(args.v9_registry.read_text(encoding="utf-8")),
        raw_rows=_rows(args.raw),
        staged_rows=_rows(args.staged),
        supplemental_rows=_rows(args.supplemental),
        disposition_rows=_rows(args.dispositions),
        canonical_rows=_rows(args.canonical),
        season_start=args.season_start,
        season_end=args.season_end,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema_version": result["schema_version"],
        "target_occurrence_count": result["target_occurrence_count"],
        "classification_counts": result["classification_counts"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
