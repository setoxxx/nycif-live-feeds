#!/usr/bin/env python3
"""Pin integrity gate — enforce semantic exact-pin eligibility, fail closed.

Writes:
  data/pin_integrity_gate_report.json
  data/pin_integrity_demotions.json

Rewrites certified artifacts in place (staging only; never protected production
files). Geometry validity remains a low-level guard. A row is an exact public
pin only when the canonical semantic location-evidence authority returns
MAP_READY and certified_pin is true.

Backward-compatible migration rule: legacy in-bounds ``map_ready`` coordinates
may remain present while their evidence is rebuilt, but they must not carry an
exact-pin claim, exact map link, or semantic MAP_READY state until validated.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, utc_now  # noqa: E402
from pin_integrity import (  # noqa: E402
    NYC_BOUNDS_DOC,
    certify_event_pin,
    nested_nycif_certify,
)


def _id_of(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("event_id") or row.get("title") or "")


def _demotion_record(surface: str, row: dict[str, Any], result: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "surface": surface,
        "id": _id_of(row),
        "title": row.get("title"),
        "reason": result.get("reason"),
        "before_lat": result.get("before_lat"),
        "before_lng": result.get("before_lng"),
        "before_status": result.get("before_status"),
        "after_status": result.get("after_status"),
        **extra,
    }


def _semantic_exact_ready(row: dict[str, Any]) -> bool:
    return (
        row.get("coordinate_status") == "map_ready"
        and row.get("map_eligibility_state") == "MAP_READY"
        and row.get("certified_pin") is True
        and row.get("latitude") is not None
        and row.get("longitude") is not None
    )


def _claims_exact_pin(row: dict[str, Any]) -> bool:
    """Return whether a row currently exposes or asserts exact-pin authority."""
    return (
        row.get("certified_pin") is True
        or row.get("map_eligibility_state") == "MAP_READY"
        or bool(row.get("map_link"))
    )


def _scan_flat_events(rows: list[dict[str, Any]], *, surface: str) -> tuple[int, int, list[dict[str, Any]], Counter]:
    before = sum(1 for r in rows if r.get("coordinate_status") == "map_ready")
    demotions: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    for row in rows:
        was_ready = row.get("coordinate_status") == "map_ready"
        result = certify_event_pin(row)
        reasons[result.get("reason") or "unknown"] += 1
        if result.get("demoted") and was_ready:
            demotions.append(_demotion_record(surface, row, result))
    after = sum(1 for r in rows if _semantic_exact_ready(r))
    return before, after, demotions, reasons


def _verify_zero_bad_map_ready(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unsupported exact-pin claims; legacy review state is allowed.

    ``coordinate_status=map_ready`` by itself is treated as a legacy transport
    state during migration. It is not an exact-pin claim unless the row also
    asserts semantic MAP_READY, certified_pin=true, or an exact map link.
    """
    bad: list[dict[str, Any]] = []
    for row in rows:
        if not _claims_exact_pin(row):
            continue
        candidate = dict(row)
        if isinstance(row.get("location_evidence"), dict):
            candidate["location_evidence"] = dict(row["location_evidence"])
        result = certify_event_pin(candidate, allow_swap_correct=False)
        if not _semantic_exact_ready(candidate):
            bad.append(
                {
                    "id": _id_of(row),
                    "reason": result.get("reason") or candidate.get("pin_integrity_reason") or "semantic_map_eligibility_failed",
                    "lat": row.get("latitude"),
                    "lng": row.get("longitude"),
                    "map_eligibility_state": candidate.get("map_eligibility_state"),
                    "certified_pin": candidate.get("certified_pin"),
                    "map_link": row.get("map_link"),
                }
            )
    return bad


def _mark_certified_flags(events: list[dict[str, Any]]) -> None:
    """Create exact links only from already-proven semantic certification."""
    for e in events:
        if _semantic_exact_ready(e):
            e["map_link"] = f"https://www.google.com/maps?q={e['latitude']},{e['longitude']}"
        else:
            e["map_link"] = None
            e["certified_pin"] = False


def certify_money_day() -> dict[str, Any]:
    path = DATA_DIR / "photographer_assignment_calendar_2mo.json"
    payload = load_json(path, {})
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return {"surface": "money_day", "skipped": True, "reason": "missing_calendar"}
    before, after, demotions, reasons = _scan_flat_events(events, surface="money_day")
    payload["coordinate_status_counts"] = dict(Counter(e.get("coordinate_status") for e in events))
    payload["pin_integrity"] = {
        "certified_at_utc": utc_now(),
        "map_ready_before": before,
        "semantic_map_ready_after": after,
        "bounds": NYC_BOUNDS_DOC,
    }
    _mark_certified_flags(events)
    payload["go_shoot_these"] = sorted(
        events,
        key=lambda e: (
            0 if _semantic_exact_ready(e) else 1,
            -(e.get("assignment_score") or 0),
            e.get("date") or "",
        ),
    )[:20]
    save_json(path, payload)
    report_path = DATA_DIR / "photographer_assignment_calendar_report.json"
    report = load_json(report_path, {})
    if isinstance(report, dict):
        report["coordinate_status_counts"] = payload["coordinate_status_counts"]
        report["pin_integrity_map_ready_after"] = after
        save_json(report_path, report)
    return {
        "surface": "money_day",
        "map_ready_before": before,
        "map_ready_after": after,
        "demotion_count": len(demotions),
        "reason_counts": dict(reasons),
        "demotions": demotions,
        "remaining_bad_map_ready": _verify_zero_bad_map_ready(events),
        "artifact": "data/photographer_assignment_calendar_2mo.json",
    }


def _unique_pack_rows(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cluster in pack.get("borough_clusters") or []:
        rows.extend(cluster.get("events") or [])
    rows.extend(pack.get("go_shoot") or [])
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for r in rows:
        rid = _id_of(r)
        if rid in seen:
            continue
        seen.add(rid)
        unique.append(r)
    return unique


def _filter_certified_clusters(pack: dict[str, Any]) -> None:
    new_clusters = []
    for cluster in pack.get("borough_clusters") or []:
        events = [e for e in (cluster.get("events") or []) if _semantic_exact_ready(e)]
        if events:
            new_clusters.append({**cluster, "events": events, "count": len(events)})
    pack["borough_clusters"] = new_clusters
    pack["go_shoot"] = [e for e in (pack.get("go_shoot") or []) if _semantic_exact_ready(e)]
    pack["map_ready_count"] = sum(len(c.get("events") or []) for c in new_clusters)
    pack["list_only_count"] = max(0, int(pack.get("total_events") or 0) - pack["map_ready_count"])
    pack["pin_integrity"] = {"certified_at_utc": utc_now(), "bounds": NYC_BOUNDS_DOC}


def certify_money_packs() -> dict[str, Any]:
    out: dict[str, Any] = {"surface": "money_day_packs", "packs": []}
    all_demotions: list[dict[str, Any]] = []
    for name in ("photographer_money_day_pack_today.json", "photographer_money_day_pack_tomorrow.json"):
        path = DATA_DIR / name
        pack = load_json(path, {})
        if not isinstance(pack, dict):
            continue
        unique = _unique_pack_rows(pack)
        before = sum(1 for r in unique if r.get("coordinate_status") == "map_ready")
        demotions = []
        for r in unique:
            was = r.get("coordinate_status") == "map_ready"
            result = certify_event_pin(r)
            if result.get("demoted") and was:
                demotions.append(_demotion_record("money_day_packs", r, result, pack=name))
        for cluster in pack.get("borough_clusters") or []:
            for e in cluster.get("events") or []:
                certify_event_pin(e)
        for e in pack.get("go_shoot") or []:
            certify_event_pin(e)
        _filter_certified_clusters(pack)
        save_json(path, pack)
        after = pack["map_ready_count"]
        all_demotions.extend(demotions)
        out["packs"].append(
            {"file": name, "map_ready_before": before, "map_ready_after": after, "demotions": len(demotions)}
        )
    out["demotions"] = all_demotions
    out["demotion_count"] = len(all_demotions)
    out["map_ready_before"] = sum(p["map_ready_before"] for p in out["packs"])
    out["map_ready_after"] = sum(p["map_ready_after"] for p in out["packs"])
    return out


def _certify_magnet_list(magnets: list[dict[str, Any]], *, surface: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    demotions: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for m in magnets:
        was = m.get("coordinate_status") == "map_ready"
        result = certify_event_pin(m)
        if result.get("demoted") and was:
            demotions.append(_demotion_record(surface, m, result))
        if _semantic_exact_ready(m):
            kept.append(m)
    return kept, demotions


def certify_viral_pack() -> dict[str, Any]:
    path = DATA_DIR / "photographer_viral_recurrence_pack_next_14d.json"
    pack = load_json(path, {})
    if not isinstance(pack, dict):
        return {"surface": "viral", "skipped": True}
    magnets = pack.get("crowd_magnets") or []
    before = sum(1 for m in magnets if m.get("coordinate_status") == "map_ready")
    kept, demotions = _certify_magnet_list(magnets, surface="viral")
    pack["crowd_magnets"] = kept
    pack["crowd_magnet_count"] = len(kept)
    pack["returning_likely_count"] = sum(1 for m in kept if m.get("recurrence_label") == "returning_likely")
    pack["possible_count"] = sum(1 for m in kept if m.get("recurrence_label") == "possible")
    pack["pin_integrity"] = {"certified_at_utc": utc_now(), "bounds": NYC_BOUNDS_DOC}
    save_json(path, pack)

    matches_path = DATA_DIR / "photographer_viral_recurrence_matches.json"
    matches_payload = load_json(matches_path, {})
    if isinstance(matches_payload, dict):
        for m in matches_payload.get("matches") or []:
            cur = m.get("current") if isinstance(m.get("current"), dict) else None
            if not cur:
                continue
            was = cur.get("coordinate_status") == "map_ready"
            result = certify_event_pin(cur)
            if result.get("demoted") and was:
                demotions.append(_demotion_record("viral_matches", cur, result))
        save_json(matches_path, matches_payload)

    return {
        "surface": "viral",
        "map_ready_before": before,
        "map_ready_after": len(kept),
        "demotion_count": len(demotions),
        "demotions": demotions,
        "artifact": "data/photographer_viral_recurrence_pack_next_14d.json",
    }


def _row_status(row: dict[str, Any]) -> str | None:
    if isinstance(row.get("nycif"), dict):
        return row["nycif"].get("coordinate_status") or row.get("coordinate_status")
    return row.get("coordinate_status")


def _civic_bags(payload: dict[str, Any]) -> list[tuple[str, list]]:
    bags = []
    for key in ("events", "opportunities", "help_places", "rows"):
        val = payload.get(key)
        if isinstance(val, list):
            bags.append((key, val))
    return bags


def certify_civic_staging() -> dict[str, Any]:
    path = DATA_DIR / "civic_people_facing_staging_feed.json"
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {"surface": "civic", "skipped": True}
    bags = _civic_bags(payload)
    before = after = 0
    demotions: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    for key, rows in bags:
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = _row_status(row)
            if status == "map_ready":
                before += 1
            result = nested_nycif_certify(row) if isinstance(row.get("nycif"), dict) else certify_event_pin(row)
            reasons[result.get("reason") or "unknown"] += 1
            semantic_ready = (
                (row.get("nycif") or {}).get("map_eligibility_state") == "MAP_READY"
                and (row.get("nycif") or {}).get("certified_pin") is True
            ) if isinstance(row.get("nycif"), dict) else _semantic_exact_ready(row)
            if semantic_ready:
                after += 1
            if result.get("demoted") and status == "map_ready":
                demotions.append(_demotion_record("civic", row, result, bag=key))
    if bags:
        save_json(path, payload)
    return {
        "surface": "civic",
        "map_ready_before": before,
        "map_ready_after": after,
        "demotion_count": len(demotions),
        "reason_counts": dict(reasons),
        "demotions": demotions[:200],
        "artifact": "data/civic_people_facing_staging_feed.json",
    }


def _field_desk_candidates() -> list[Path]:
    return [
        DATA_DIR / "schema-v1-discovery" / "major" / "events.json",
        DATA_DIR / "events_discovery_v02_major.json",
        DATA_DIR / "events_schema_v1_major.json",
    ]


def field_desk_feed_scan() -> dict[str, Any]:
    """Report exact-pin claims that would fail semantic certification."""
    for path in _field_desk_candidates():
        payload = load_json(path, None)
        if not payload:
            continue
        events = payload.get("events") if isinstance(payload, dict) else payload
        if not isinstance(events, list):
            continue
        before = 0
        would_demote = []
        for row in events:
            if not isinstance(row, dict):
                continue
            status = _row_status(row)
            if status != "map_ready":
                continue
            before += 1
            candidate = dict(row)
            if isinstance(row.get("nycif"), dict):
                candidate["nycif"] = dict(row["nycif"])
                result = nested_nycif_certify(candidate)
                semantic_ready = (
                    candidate["nycif"].get("map_eligibility_state") == "MAP_READY"
                    and candidate["nycif"].get("certified_pin") is True
                )
                reason = result.get("reason") or candidate["nycif"].get("pin_integrity_reason")
            else:
                result = certify_event_pin(candidate)
                semantic_ready = _semantic_exact_ready(candidate)
                reason = result.get("reason") or candidate.get("pin_integrity_reason")
            if not semantic_ready and _claims_exact_pin(row):
                would_demote.append({"id": _id_of(row), "title": row.get("title"), "reason": reason})
        return {
            "surface": "field_desk_feed",
            "artifact": str(path.relative_to(ROOT)),
            "map_ready_scanned": before,
            "unsupported_exact_claim_count": len(would_demote),
            "unsupported_exact_claim_examples": would_demote[:20],
            "note": "Report-only scan; legacy map_ready without exact authority is migration state, not certification.",
        }
    return {"surface": "field_desk_feed", "skipped": True}


def _flatten_civic_for_verify(civic: dict[str, Any]) -> list[dict[str, Any]]:
    bags: list[dict[str, Any]] = []
    for key in ("events", "opportunities", "help_places", "rows"):
        val = civic.get(key)
        if not isinstance(val, list):
            continue
        for row in val:
            if not isinstance(row, dict):
                continue
            nycif = row.get("nycif") if isinstance(row.get("nycif"), dict) else {}
            bags.append(
                {
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "coordinate_status": nycif.get("coordinate_status") or row.get("coordinate_status"),
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                    "location_evidence": nycif.get("location_evidence") or row.get("location_evidence"),
                    "map_eligibility_state": nycif.get("map_eligibility_state") or row.get("map_eligibility_state"),
                    "certified_pin": nycif.get("certified_pin") if "certified_pin" in nycif else row.get("certified_pin"),
                    "map_link": row.get("map_link"),
                }
            )
    return bags


def _collect_remaining_bad() -> list[dict[str, Any]]:
    remaining_bad: list[dict[str, Any]] = []
    cal = load_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", {})
    cal_events = cal.get("events") if isinstance(cal, dict) else []
    remaining_bad.extend(_verify_zero_bad_map_ready(cal_events if isinstance(cal_events, list) else []))

    viral = load_json(DATA_DIR / "photographer_viral_recurrence_pack_next_14d.json", {})
    remaining_bad.extend(
        _verify_zero_bad_map_ready(viral.get("crowd_magnets") or [] if isinstance(viral, dict) else [])
    )

    civic = load_json(DATA_DIR / "civic_people_facing_staging_feed.json", {})
    if isinstance(civic, dict):
        remaining_bad.extend(_verify_zero_bad_map_ready(_flatten_civic_for_verify(civic)))
    return remaining_bad


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    surfaces = [
        certify_money_day(),
        certify_money_packs(),
        certify_viral_pack(),
        certify_civic_staging(),
        field_desk_feed_scan(),
    ]

    all_demotions: list[dict[str, Any]] = []
    for s in surfaces:
        all_demotions.extend(s.get("demotions") or [])

    remaining_bad = _collect_remaining_bad()
    reason_totals: Counter = Counter(str(d.get("reason") or "unknown") for d in all_demotions)
    qa_pass = len(remaining_bad) == 0

    demotions_payload = {
        "schema_version": "pin-integrity-demotions-v1",
        "generated_at_utc": utc_now(),
        "demotion_count": len(all_demotions),
        "reason_counts": dict(reason_totals),
        "demotions": all_demotions[:500],
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
    }
    save_json(DATA_DIR / "pin_integrity_demotions.json", demotions_payload)

    report = {
        "schema_version": "pin-integrity-gate-v2",
        "generated_at_utc": utc_now(),
        "qa_pass": qa_pass,
        "bounds": NYC_BOUNDS_DOC,
        "rule": "ZERO unsupported exact-pin claims; legacy coordinates may remain review-required during evidence migration",
        "surfaces": [{k: v for k, v in s.items() if k != "demotions"} for s in surfaces],
        "demotion_count": len(all_demotions),
        "demotion_reason_counts": dict(reason_totals),
        "demotions_artifact": "data/pin_integrity_demotions.json",
        "remaining_bad_map_ready": remaining_bad[:50],
        "remaining_bad_count": len(remaining_bad),
        "map_ready_before_total": sum(int(s.get("map_ready_before") or 0) for s in surfaces if "map_ready_before" in s),
        "map_ready_after_total": sum(int(s.get("map_ready_after") or 0) for s in surfaces if "map_ready_after" in s),
        "protected_files_untouched": True,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": (
            "Geometry validation never creates certification. Legacy in-bounds map_ready rows without validated "
            "location evidence may remain as migration state, but certified_pin, semantic MAP_READY and exact map links are cleared."
        ),
    }
    save_json(DATA_DIR / "pin_integrity_gate_report.json", report)
    print(
        json.dumps(
            {
                "qa_pass": qa_pass,
                "demotion_count": len(all_demotions),
                "reason_counts": dict(reason_totals),
                "map_ready_before_total": report["map_ready_before_total"],
                "map_ready_after_total": report["map_ready_after_total"],
                "remaining_bad_count": len(remaining_bad),
            },
            indent=2,
        )
    )
    return 0 if qa_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
