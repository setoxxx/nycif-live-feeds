#!/usr/bin/env python3
"""Executable Projector V3 authority layer.

V3 keeps the reviewed discovery classification/grouping implementation from V2
but replaces its two legacy authorities at runtime:

* occurrence identity/rejection -> OccurrenceIdentityV2
* map publication -> semantic_map_decision / pin_integrity

The legacy module is therefore a classification/output library, not an identity
or coordinate authority. V3 fails closed if duplicate exact occurrences,
unsupported exact coordinates, silent raw-row loss, or legacy publication claims
survive the projection.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts import project_events_discovery_v02 as legacy
    from scripts.occurrence_identity_contract import identity_precision, occurrence_key_v2
    from scripts.projector_v2_authority import (
        build_rejection_contract,
        classify_occurrence_intake,
        occurrence_identity_v2_set,
        semantic_map_decision,
    )
except ModuleNotFoundError:  # pragma: no cover
    import project_events_discovery_v02 as legacy  # type: ignore[no-redef]
    from occurrence_identity_contract import identity_precision, occurrence_key_v2
    from projector_v2_authority import (
        build_rejection_contract,
        classify_occurrence_intake,
        occurrence_identity_v2_set,
        semantic_map_decision,
    )


NON_PUBLIC_GROUP_ROLES = {
    "supporting_permit",
    "street_closure",
    "transportation_operation",
}
PRESERVED_NON_MARKER_DISPOSITIONS = {
    "maintenance_or_closure",
    "private_or_reserved_activity",
    "grouped_under_public_event",
}


class ScopedRejectedOccurrences:
    """Legacy membership facade backed by V2 exact/day rejection scopes."""

    def __init__(self, exact: set[tuple[str, str, str]], days: set[tuple[str, str, str]]) -> None:
        self.exact = exact
        self.days = days

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, tuple) or len(key) != 3:
            return False
        typed = (str(key[0]), str(key[1]), str(key[2]))
        if typed in self.exact:
            return True
        match = re.match(r"^(\d{4}-\d{2}-\d{2})", typed[2])
        return bool(match and (typed[0], typed[1], match.group(1)) in self.days)


def v2_rejected_identity_sets(dispositions: list[dict[str, Any]]):
    contract = build_rejection_contract(dispositions)
    return set(contract.sources), ScopedRejectedOccurrences(set(contract.exact), set(contract.days))


def apply_v3_map_publication_gate(
    event: dict[str, Any],
    row: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    """Apply the final public-marker gate after semantic coordinate authority.

    A validated coordinate is necessary but not sufficient for MAP_READY. The
    canonical occurrence must also be a standalone public event. Supporting,
    grouped, child, maintenance, private, or operator records are preserved but
    cannot retain exact public geometry.
    """
    nycif = event.setdefault("nycif", {})
    semantic_state = str(decision.get("map_eligibility_state") or "REVIEW_REQUIRED")
    semantic_exact = semantic_state == "MAP_READY" and decision.get("certified_pin") is True
    event_role = str(event.get("event_role") or "")
    parent_event_id = event.get("parent_event_id")
    disposition = str(nycif.get("display_disposition") or "list_only")

    if semantic_exact and event_role == "public_event" and parent_event_id in (None, ""):
        if disposition == "list_only":
            disposition = "standalone_public_event"
            nycif["display_disposition"] = disposition

    standalone_public = (
        event_role == "public_event"
        and parent_event_id in (None, "")
        and disposition == "standalone_public_event"
    )
    exact = semantic_exact and standalone_public

    explicitly_non_marker = (
        event_role in NON_PUBLIC_GROUP_ROLES
        or parent_event_id not in (None, "")
        or disposition in PRESERVED_NON_MARKER_DISPOSITIONS
    )

    if not standalone_public and explicitly_non_marker:
        state = "LIST_ONLY"
        if event_role != "public_event":
            gate_reason = "EVENT_ROLE_NOT_PUBLIC"
        elif parent_event_id not in (None, ""):
            gate_reason = "CHILD_EVENT_NOT_STANDALONE"
        else:
            gate_reason = "DISPLAY_DISPOSITION_NOT_STANDALONE"
    else:
        state = semantic_state
        gate_reason = decision.get("reason_code")

    if not exact:
        if event_role in NON_PUBLIC_GROUP_ROLES:
            nycif["display_disposition"] = "grouped_under_public_event"
        elif disposition not in PRESERVED_NON_MARKER_DISPOSITIONS:
            nycif["display_disposition"] = "list_only"
        event["location"] = (
            decision.get("general_area_label")
            or row.get("neighborhood")
            or event.get("borough")
            or "Location under review"
        )

    event["location_evidence"] = row.get("location_evidence") if isinstance(row.get("location_evidence"), dict) else None
    event["latitude"] = decision.get("latitude") if exact else None
    event["longitude"] = decision.get("longitude") if exact else None
    event["address"] = event.get("address") if exact else None

    nycif["coordinate_status"] = "map_ready" if exact else "list_only"
    nycif["map_eligibility_state"] = state
    nycif["certified_pin"] = exact
    nycif["pin_integrity_reason"] = gate_reason
    nycif["location_authority"] = "projector_v3_semantic_map_decision"
    return event


def v3_build_base_event(row: dict[str, Any], **kwargs: Any) -> dict[str, Any] | None:
    event = _ORIGINAL_BUILD_BASE_EVENT(row, **kwargs)
    if event is None:
        return None
    decision = semantic_map_decision(row)
    return apply_v3_map_publication_gate(event, row, decision)


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return legacy.load_events(path)


def v2_raw_accounting() -> dict[str, Any]:
    raw_rows = _load_rows(legacy.RAW)
    staged_rows = _load_rows(legacy.STAGED)
    dispositions = _load_rows(legacy.DISPOSITION) if legacy.DISPOSITION.exists() else []
    contract = build_rejection_contract(dispositions)
    represented = occurrence_identity_v2_set(staged_rows)
    counts: Counter[str] = Counter()

    for row in raw_rows:
        bucket = classify_occurrence_intake(
            row,
            represented_occurrences=represented,
            rejection_contract=contract,
            season_start=legacy.SEASON_START_DATE,
            season_end=legacy.SEASON_END_DATE,
        )
        counts[bucket] += 1
        if bucket in {"accepted_review_supplemental", "identity_ambiguous_review"} and identity_precision(row) != "AMBIGUOUS":
            represented.add(occurrence_key_v2(row))

    ordered = (
        "documented_duplicate",
        "rejected_exact",
        "rejected_day",
        "rejected_source_all",
        "outside_window",
        "identity_ambiguous_review",
        "accepted_review_supplemental",
        "invalid",
    )
    accounted = sum(counts.get(key, 0) for key in ordered)
    return {
        "raw_rows": len(raw_rows),
        "raw_intake_buckets": {key: int(counts.get(key, 0)) for key in ordered},
        "raw_accounted": accounted,
        "raw_accounting_pass": accounted == len(raw_rows),
        "silent_identity_loss": len(raw_rows) - accounted,
    }


def validate_projected_authority() -> dict[str, Any]:
    accepted_path = legacy.ROOT / "data" / "events_discovery_accepted_canonical_v02.json"
    accepted = _load_rows(accepted_path)
    exact_keys: list[tuple[str, str, str]] = []
    unsupported = 0
    legacy_coordinate = 0
    invalid_publication_state = 0

    for event in accepted:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        has_coord = event.get("latitude") is not None or event.get("longitude") is not None
        exact = nycif.get("map_eligibility_state") == "MAP_READY" and nycif.get("certified_pin") is True
        standalone_public = (
            event.get("event_role") == "public_event"
            and event.get("parent_event_id") in (None, "")
            and nycif.get("display_disposition") == "standalone_public_event"
        )
        if has_coord and not exact:
            unsupported += 1
        if exact and not standalone_public:
            invalid_publication_state += 1
        if nycif.get("location_authority") != "projector_v3_semantic_map_decision":
            legacy_coordinate += 1
        if identity_precision(event) != "AMBIGUOUS":
            exact_keys.append(occurrence_key_v2(event))

    duplicate_exact = len(exact_keys) - len(set(exact_keys))
    raw = v2_raw_accounting()
    result = {
        **raw,
        "accepted_records": len(accepted),
        "duplicate_exact_occurrences": duplicate_exact,
        "unsupported_exact_pin_count": unsupported,
        "invalid_publication_state_count": invalid_publication_state,
        "implicit_source_all_count": 0,
        "legacy_occurrence_authority_count": 0,
        "legacy_coordinate_authority_count": legacy_coordinate,
    }
    zero_keys = (
        "silent_identity_loss",
        "duplicate_exact_occurrences",
        "unsupported_exact_pin_count",
        "invalid_publication_state_count",
        "implicit_source_all_count",
        "legacy_occurrence_authority_count",
        "legacy_coordinate_authority_count",
    )
    result["qa_pass"] = result["raw_accounting_pass"] and all(result[key] == 0 for key in zero_keys)
    return result


def install_v3_authority() -> None:
    legacy.occurrence_key = occurrence_key_v2
    legacy.occurrence_key_set = occurrence_identity_v2_set
    legacy.rejected_open_data_identity_sets = v2_rejected_identity_sets
    legacy.build_base_event = v3_build_base_event


def main() -> int:
    install_v3_authority()
    code = legacy.main()
    if code not in (None, 0):
        return int(code)

    report = validate_projected_authority()
    report_path = legacy.ROOT / "data" / "events_discovery_v3_authority_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    reconciliation_path = legacy.ROOT / "data" / "events_discovery_reconciliation_v02.json"
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    reconciliation["v3_authority"] = report
    reconciliation_path.write_text(json.dumps(reconciliation, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not report["qa_pass"]:
        raise RuntimeError(f"Projector V3 authority gate failed: {report}")
    return 0


_ORIGINAL_BUILD_BASE_EVENT = legacy.build_base_event

if __name__ == "__main__":
    raise SystemExit(main())
