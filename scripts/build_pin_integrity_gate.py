#!/usr/bin/env python3
"""Pin integrity gate — certify desk pin surfaces, demote bad map_ready, fail closed.

Writes:
  data/pin_integrity_gate_report.json
  data/pin_integrity_demotions.json

Rewrites certified artifacts in place (staging only; never protected production files).
qa_pass is TRUE only when ZERO remaining map_ready rows fail NYC certification.
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
    REASON_OK,
    REASON_OK_SWAP,
    certify_event_pin,
    certify_nyc_pin,
    nested_nycif_certify,
)

PROTECTED = {
    "location_cache.json",
    "nycif_staged_live_events.json",
    "staged_live_manifest.json",
    "previous_staged_live_events_snapshot.json",
}


def _id_of(row: dict[str, Any]) -> str:
    return str(row.get("id") or row.get("event_id") or row.get("title") or "")


def _scan_flat_events(rows: list[dict[str, Any]], *, surface: str) -> tuple[int, int, list[dict[str, Any]], Counter]:
    before = sum(1 for r in rows if r.get("coordinate_status") == "map_ready")
    demotions: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    for row in rows:
        was_ready = row.get("coordinate_status") == "map_ready"
        result = certify_event_pin(row)
        reasons[result.get("reason") or "unknown"] += 1
        if result.get("demoted") and was_ready:
            demotions.append(
                {
                    "surface": surface,
                    "id": _id_of(row),
                    "title": row.get("title"),
                    "reason": result.get("reason"),
                    "before_lat": result.get("before_lat"),
                    "before_lng": result.get("before_lng"),
                    "before_status": result.get("before_status"),
                    "after_status": result.get("after_status"),
                }
            )
    after = sum(1 for r in rows if r.get("coordinate_status") == "map_ready")
    return before, after, demotions, reasons


def _verify_zero_bad_map_ready(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bad = []
    for row in rows:
        if row.get("coordinate_status") != "map_ready":
            continue
        lat_f, lng_f, ok, reason = certify_nyc_pin(row.get("latitude"), row.get("longitude"), allow_swap_correct=False)
        if not ok:
            bad.append({"id": _id_of(row), "reason": reason, "lat": row.get("latitude"), "lng": row.get("longitude")})
    return bad


def certify_money_day() -> dict[str, Any]:
    path = DATA_DIR / "photographer_assignment_calendar_2mo.json"
    payload = load_json(path, {})
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return {"surface": "money_day", "skipped": True, "reason": "missing_calendar"}
    before, after, demotions, reasons = _scan_flat_events(events, surface="money_day")
    # refresh go_shoot / months map_ready counts coarsely
    payload["coordinate_status_counts"] = dict(Counter(e.get("coordinate_status") for e in events))
    payload["pin_integrity"] = {
        "certified_at_utc": utc_now(),
        "map_ready_before": before,
        "map_ready_after": after,
        "bounds": NYC_BOUNDS_DOC,
    }
    for e in events:
        if e.get("coordinate_status") == "map_ready" and e.get("latitude") is not None:
            e["map_link"] = f"https://www.google.com/maps?q={e['latitude']},{e['longitude']}"
            e["certified_pin"] = True
        else:
            e["map_link"] = None
            e["certified_pin"] = False
    # rebuild go_shoot from certified order
    payload["go_shoot_these"] = sorted(
        events,
        key=lambda e: (
            0 if e.get("coordinate_status") == "map_ready" else 1,
            -(e.get("assignment_score") or 0),
            e.get("date") or "",
        ),
    )[:20]
    save_json(path, payload)
    # sync report counts
    report_path = DATA_DIR / "photographer_assignment_calendar_report.json"
    report = load_json(report_path, {})
    if isinstance(report, dict):
        report["coordinate_status_counts"] = payload["coordinate_status_counts"]
        report["pin_integrity_map_ready_after"] = after
        save_json(report_path, report)
    bad = _verify_zero_bad_map_ready(events)
    return {
        "surface": "money_day",
        "map_ready_before": before,
        "map_ready_after": after,
        "demotion_count": len(demotions),
        "reason_counts": dict(reasons),
        "demotions": demotions,
        "remaining_bad_map_ready": bad,
        "artifact": "data/photographer_assignment_calendar_2mo.json",
    }


def certify_money_packs() -> dict[str, Any]:
    out = {"surface": "money_day_packs", "packs": []}
    all_demotions: list[dict[str, Any]] = []
    for name in ("photographer_money_day_pack_today.json", "photographer_money_day_pack_tomorrow.json"):
        path = DATA_DIR / name
        pack = load_json(path, {})
        if not isinstance(pack, dict):
            continue
        rows = []
        for cluster in pack.get("borough_clusters") or []:
            rows.extend(cluster.get("events") or [])
        rows.extend(pack.get("go_shoot") or [])
        # dedupe by id for counting
        seen = set()
        unique = []
        for r in rows:
            rid = _id_of(r)
            if rid in seen:
                continue
            seen.add(rid)
            unique.append(r)
        before = sum(1 for r in unique if r.get("coordinate_status") == "map_ready")
        demotions = []
        for r in rows:
            was = r.get("coordinate_status") == "map_ready"
            result = certify_event_pin(r)
            if result.get("demoted") and was:
                demotions.append(
                    {
                        "surface": "money_day_packs",
                        "pack": name,
                        "id": _id_of(r),
                        "title": r.get("title"),
                        "reason": result.get("reason"),
                        "before_lat": result.get("before_lat"),
                        "before_lng": result.get("before_lng"),
                    }
                )
        # filter clusters to certified map_ready only for pin exposure
        new_clusters = []
        for cluster in pack.get("borough_clusters") or []:
            events = [e for e in (cluster.get("events") or []) if e.get("coordinate_status") == "map_ready" and e.get("certified_pin")]
            if events:
                cluster = {**cluster, "events": events, "count": len(events)}
                new_clusters.append(cluster)
        pack["borough_clusters"] = new_clusters
        pack["go_shoot"] = [
            e for e in (pack.get("go_shoot") or []) if e.get("coordinate_status") == "map_ready" and e.get("certified_pin")
        ]
        pack["map_ready_count"] = sum(1 for c in new_clusters for _ in c.get("events") or [])
        pack["list_only_count"] = max(0, int(pack.get("total_events") or 0) - pack["map_ready_count"])
        pack["pin_integrity"] = {"certified_at_utc": utc_now(), "bounds": NYC_BOUNDS_DOC}
        save_json(path, pack)
        after = pack["map_ready_count"]
        all_demotions.extend(demotions)
        out["packs"].append({"file": name, "map_ready_before": before, "map_ready_after": after, "demotions": len(demotions)})
    out["demotions"] = all_demotions
    out["demotion_count"] = len(all_demotions)
    out["map_ready_before"] = sum(p["map_ready_before"] for p in out["packs"])
    out["map_ready_after"] = sum(p["map_ready_after"] for p in out["packs"])
    return out


def certify_viral_pack() -> dict[str, Any]:
    path = DATA_DIR / "photographer_viral_recurrence_pack_next_14d.json"
    pack = load_json(path, {})
    if not isinstance(pack, dict):
        return {"surface": "viral", "skipped": True}
    magnets = pack.get("crowd_magnets") or []
    before = sum(1 for m in magnets if m.get("coordinate_status") == "map_ready")
    demotions = []
    kept = []
    for m in magnets:
        # magnets are flat current rows
        was = m.get("coordinate_status") == "map_ready"
        result = certify_event_pin(m)
        if result.get("demoted") and was:
            demotions.append(
                {
                    "surface": "viral",
                    "id": m.get("event_id") or m.get("title"),
                    "title": m.get("title"),
                    "reason": result.get("reason"),
                    "before_lat": result.get("before_lat"),
                    "before_lng": result.get("before_lng"),
                }
            )
        if m.get("coordinate_status") == "map_ready" and m.get("certified_pin"):
            kept.append(m)
    pack["crowd_magnets"] = kept
    pack["crowd_magnet_count"] = len(kept)
    pack["returning_likely_count"] = sum(1 for m in kept if m.get("recurrence_label") == "returning_likely")
    pack["possible_count"] = sum(1 for m in kept if m.get("recurrence_label") == "possible")
    pack["pin_integrity"] = {"certified_at_utc": utc_now(), "bounds": NYC_BOUNDS_DOC}
    save_json(path, pack)
    # also certify match current sides (optional, don't strip matches)
    matches_path = DATA_DIR / "photographer_viral_recurrence_matches.json"
    matches_payload = load_json(matches_path, {})
    match_demotions = []
    if isinstance(matches_payload, dict):
        for m in matches_payload.get("matches") or []:
            cur = m.get("current") if isinstance(m.get("current"), dict) else None
            if not cur:
                continue
            was = cur.get("coordinate_status") == "map_ready"
            result = certify_event_pin(cur)
            if result.get("demoted") and was:
                match_demotions.append(
                    {
                        "surface": "viral_matches",
                        "id": cur.get("id"),
                        "title": cur.get("title"),
                        "reason": result.get("reason"),
                        "before_lat": result.get("before_lat"),
                        "before_lng": result.get("before_lng"),
                    }
                )
        save_json(matches_path, matches_payload)
    demotions.extend(match_demotions)
    return {
        "surface": "viral",
        "map_ready_before": before,
        "map_ready_after": len(kept),
        "demotion_count": len(demotions),
        "demotions": demotions,
        "artifact": "data/photographer_viral_recurrence_pack_next_14d.json",
    }


def certify_civic_staging() -> dict[str, Any]:
    path = DATA_DIR / "civic_people_facing_staging_feed.json"
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {"surface": "civic", "skipped": True}
    events = payload.get("events")
    if not isinstance(events, list):
        # some feeds nest differently
        events = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    # Also schema civic review pages are large — focus staging feed events/opportunities/help
    bags = []
    for key in ("events", "opportunities", "help_places", "rows"):
        val = payload.get(key)
        if isinstance(val, list):
            bags.append((key, val))
    if not bags and isinstance(events, list) and events:
        bags = [("events", events)]

    before = 0
    after = 0
    demotions: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    for key, rows in bags:
        for row in rows:
            if not isinstance(row, dict):
                continue
            # schema rows often nest nycif
            status = None
            if isinstance(row.get("nycif"), dict):
                status = row["nycif"].get("coordinate_status")
            status = status or row.get("coordinate_status")
            if status == "map_ready":
                before += 1
            if isinstance(row.get("nycif"), dict):
                result = nested_nycif_certify(row)
            else:
                result = certify_event_pin(row)
            reasons[result.get("reason") or "unknown"] += 1
            new_status = None
            if isinstance(row.get("nycif"), dict):
                new_status = row["nycif"].get("coordinate_status")
            new_status = new_status or row.get("coordinate_status")
            if new_status == "map_ready":
                after += 1
            if result.get("demoted") and status == "map_ready":
                demotions.append(
                    {
                        "surface": "civic",
                        "bag": key,
                        "id": _id_of(row),
                        "title": row.get("title"),
                        "reason": result.get("reason"),
                        "before_lat": result.get("before_lat"),
                        "before_lng": result.get("before_lng"),
                    }
                )
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


def field_desk_feed_scan() -> dict[str, Any]:
    """Scan discovery major events feed used by Field Desk (report-only demotion tally)."""
    for path in (
        DATA_DIR / "schema-v1-discovery" / "major" / "events.json",
        DATA_DIR / "events_discovery_v02_major.json",
        DATA_DIR / "events_schema_v1_major.json",
    ):
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
            status = (row.get("nycif") or {}).get("coordinate_status") if isinstance(row.get("nycif"), dict) else row.get("coordinate_status")
            if status != "map_ready":
                continue
            before += 1
            lat_f, lng_f, ok, reason = certify_nyc_pin(row.get("latitude"), row.get("longitude"), allow_swap_correct=True)
            if not ok:
                would_demote.append({"id": _id_of(row), "title": row.get("title"), "reason": reason})
        return {
            "surface": "field_desk_feed",
            "artifact": str(path.relative_to(ROOT)),
            "map_ready_scanned": before,
            "would_demote_count": len(would_demote),
            "would_demote_examples": would_demote[:20],
            "note": "Major feed scan is report-only here; Field Desk JS also refuses non-NYC pins at render.",
        }
    return {"surface": "field_desk_feed", "skipped": True}


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

    # Re-verify money day + viral + civic staging for hard qa
    cal = load_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", {})
    cal_events = cal.get("events") if isinstance(cal, dict) else []
    remaining_bad = _verify_zero_bad_map_ready(cal_events if isinstance(cal_events, list) else [])

    viral = load_json(DATA_DIR / "photographer_viral_recurrence_pack_next_14d.json", {})
    viral_bad = _verify_zero_bad_map_ready(viral.get("crowd_magnets") or [] if isinstance(viral, dict) else [])
    remaining_bad.extend(viral_bad)

    civic = load_json(DATA_DIR / "civic_people_facing_staging_feed.json", {})
    civic_bags: list[dict[str, Any]] = []
    if isinstance(civic, dict):
        for key in ("events", "opportunities", "help_places", "rows"):
            val = civic.get(key)
            if isinstance(val, list):
                for row in val:
                    if not isinstance(row, dict):
                        continue
                    # flatten nested nycif for verify
                    flat = {
                        "id": row.get("id"),
                        "title": row.get("title"),
                        "coordinate_status": (
                            (row.get("nycif") or {}).get("coordinate_status")
                            if isinstance(row.get("nycif"), dict)
                            else row.get("coordinate_status")
                        ),
                        "latitude": row.get("latitude"),
                        "longitude": row.get("longitude"),
                    }
                    civic_bags.append(flat)
    remaining_bad.extend(_verify_zero_bad_map_ready(civic_bags))

    reason_totals: Counter = Counter()
    for d in all_demotions:
        reason_totals[str(d.get("reason") or "unknown")] += 1

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
        "schema_version": "pin-integrity-gate-v1",
        "generated_at_utc": utc_now(),
        "qa_pass": qa_pass,
        "bounds": NYC_BOUNDS_DOC,
        "rule": "ZERO map_ready rows may fail NYC certification after gate",
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
            "Demotes invalid map_ready to list_only and clears lat/lng on pin path. "
            "Swap auto-correct only when as-is OOB and swapped pair is inside NYC box."
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
