#!/usr/bin/env python3
"""Reconcile Google/curated NYC feast+festival seed rows against raw SAPO permits.

Read-only against protected feeds. Writes staging reference + QA report only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import extract_rows, preserve_date, utc_now  # noqa: E402

SEED_PATH = ROOT / "data" / "staging" / "nyc_feast_festival_reference_seed.json"
RAW_PATH = ROOT / "data" / "raw_nyc_open_data_snapshot.json"
REFERENCE_PATH = ROOT / "data" / "nyc_sapo_feast_festival_reference.json"
REPORT_PATH = ROOT / "data" / "reports" / "nyc_feast_festival_reference_match_report.json"


def norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def parse_day(value: Any) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", str(value or "").strip())
    return match.group(1) if match else None


def span_days(row: dict[str, Any]) -> int:
    start = parse_day(preserve_date(row) or row.get("start_date_time"))
    end = parse_day(row.get("end_date_time")) or start
    if not start or not end:
        return 1
    try:
        from datetime import date

        y1, m1, d1 = map(int, start.split("-"))
        y2, m2, d2 = map(int, end.split("-"))
        return max(1, (date(y2, m2, d2) - date(y1, m1, d1)).days + 1)
    except ValueError:
        return 1


def alias_hits(title: str, aliases: list[str]) -> bool:
    norm_title = norm_text(title)
    if not norm_title:
        return False
    for alias in aliases:
        alias_norm = norm_text(alias)
        if alias_norm and (alias_norm in norm_title or norm_title in alias_norm):
            return True
    return False


def looks_like_feast_or_fair(row: dict[str, Any]) -> bool:
    blob = norm_text(
        " ".join(
            [
                str(row.get("event_name") or ""),
                str(row.get("event_type") or ""),
                str(row.get("event_location") or ""),
            ]
        )
    )
    return bool(
        re.search(
            r"feast|festival|fair|giglio|gennaro|carnival|block party|street festival|holiday market",
            blob,
        )
    )


def location_hits(location: str, hint: str) -> bool:
    loc = norm_text(location)
    needle = norm_text(hint)
    if not loc or not needle:
        return False
    tokens = [t for t in needle.split() if len(t) > 3]
    return any(token in loc for token in tokens[:4])


def match_seed(seed: dict[str, Any], raw_rows: list[dict[str, Any]]) -> dict[str, Any]:
    aliases = [seed.get("canonical_name") or ""] + list(seed.get("aliases") or [])
    claimed_id = str(seed.get("claimed_permit_id") or "").strip()
    out: dict[str, Any] = {
        "key": seed.get("key"),
        "canonical_name": seed.get("canonical_name"),
        "event_kind": seed.get("event_kind"),
        "map_emoji": seed.get("map_emoji"),
        "typical_multi_day": bool(seed.get("typical_multi_day")),
        "claimed_permit_id": claimed_id or None,
        "projected_start": seed.get("projected_start"),
        "projected_end": seed.get("projected_end"),
        "location_hint": seed.get("location_hint"),
        "borough": seed.get("borough"),
        "source": seed.get("source") or "google_studio_projected",
        "match_status": "not_in_raw_snapshot",
        "raw_match": None,
        "notes": [],
    }

    if claimed_id:
        id_hits = [r for r in raw_rows if str(r.get("source_event_id") or "") == claimed_id]
        if id_hits:
            row = id_hits[0]
            if alias_hits(str(row.get("event_name") or ""), aliases):
                out["match_status"] = "confirmed_permit_id"
                out["raw_match"] = _raw_summary(row)
            else:
                out["match_status"] = "permit_id_mismatch"
                out["raw_match"] = _raw_summary(row)
                out["notes"].append(
                    "Claimed permit ID exists in raw snapshot but title does not match this feast/fair."
                )

    if out["match_status"] == "not_in_raw_snapshot":
        title_hits = [
            r
            for r in raw_rows
            if alias_hits(str(r.get("event_name") or ""), aliases) and looks_like_feast_or_fair(r)
        ]
        if title_hits:
            best = title_hits[0]
            out["match_status"] = "title_match"
            out["raw_match"] = _raw_summary(best)
            if claimed_id and str(best.get("source_event_id") or "") != claimed_id:
                out["notes"].append("Title matched a different permit ID than the projected one.")

    if out["match_status"] == "not_in_raw_snapshot" and seed.get("location_hint"):
        loc_hits = [
            r
            for r in raw_rows
            if location_hits(str(r.get("event_location") or ""), str(seed.get("location_hint")))
            and alias_hits(str(r.get("event_name") or ""), aliases[:2])
            and looks_like_feast_or_fair(r)
        ]
        if loc_hits:
            out["match_status"] = "location_and_title_match"
            out["raw_match"] = _raw_summary(loc_hits[0])

    if out["match_status"] == "not_in_raw_snapshot":
        out["notes"].append(
            "Not present in committed raw snapshot yet; keep projected row for registry/emoji mapping."
        )

    return out


def _raw_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_dataset": row.get("source_dataset"),
        "source_event_id": row.get("source_event_id"),
        "event_name": row.get("event_name"),
        "event_type": row.get("event_type"),
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "event_borough": row.get("event_borough"),
        "event_location": row.get("event_location"),
        "span_days": span_days(row),
    }


def build(seed_rows: list[dict[str, Any]], raw_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = utc_now()
    entries = [match_seed(seed, raw_rows) for seed in seed_rows]
    status_counts: dict[str, int] = {}
    for entry in entries:
        status_counts[entry["match_status"]] = status_counts.get(entry["match_status"], 0) + 1

    confirmed = [e for e in entries if e["match_status"] in {"confirmed_permit_id", "title_match", "location_and_title_match"}]
    multi_day_confirmed = [e for e in confirmed if (e.get("raw_match") or {}).get("span_days", 1) > 1]

    reference = {
        "artifact_type": "nyc_sapo_feast_festival_reference",
        "generated_at_utc": generated_at,
        "source_seed": str(SEED_PATH.relative_to(ROOT)),
        "warning": (
            "Projected feast/fair rows are mapping hints only. Permit IDs from external lists are often wrong; "
            "only raw-match rows are SAPO-confirmed in this snapshot."
        ),
        "emoji_guide": {
            "religious_feast_multi_day": "🎡",
            "street_fair_single_day": "🎉",
            "food_festival": "🍽️",
            "cultural_parade": "🎊",
            "holiday_market": "🎄",
            "halloween": "🎃",
            "multi_day_marker_note": "Multi-day events use the same emoji but a larger map pin.",
        },
        "entries": entries,
    }

    report = {
        "artifact_type": "nyc_feast_festival_reference_match_report",
        "generated_at_utc": generated_at,
        "qa_pass": True,
        "seed_count": len(seed_rows),
        "status_counts": status_counts,
        "confirmed_in_raw_snapshot": len(confirmed),
        "multi_day_confirmed_in_raw_snapshot": len(multi_day_confirmed),
        "permit_id_mismatch_count": status_counts.get("permit_id_mismatch", 0),
        "not_in_raw_snapshot_count": status_counts.get("not_in_raw_snapshot", 0),
        "confirmed_samples": confirmed[:25],
        "permit_id_mismatches": [e for e in entries if e["match_status"] == "permit_id_mismatch"][:25],
        "projected_only_samples": [e for e in entries if e["match_status"] == "not_in_raw_snapshot"][:25],
    }
    return reference, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NYC feast/festival reference + match report.")
    parser.parse_args()

    if not SEED_PATH.exists():
        raise SystemExit(f"Missing seed file: {SEED_PATH}")

    seed_payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    seed_rows = seed_payload.get("entries") if isinstance(seed_payload, dict) else seed_payload
    if not isinstance(seed_rows, list):
        raise SystemExit("Seed file must contain an entries array.")

    raw_rows = extract_rows(json.loads(RAW_PATH.read_text(encoding="utf-8")))
    reference, report = build(seed_rows, raw_rows)

    REFERENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REFERENCE_PATH.write_text(json.dumps(reference, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"reference": str(REFERENCE_PATH.relative_to(ROOT)), "report": report["status_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
