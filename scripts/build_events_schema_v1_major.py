#!/usr/bin/env python3
"""Build schema-v1 major events feed from current approved data.

Carries forward explicit signals from the legacy major radar feed when IDs/source
event IDs still match current approved rows, then applies documented scoring rules
to current staged/all events. Never promotes supplemental review rows.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import (  # noqa: E402
    SCHEMA_VERSION,
    envelope,
    event_date_key,
    extract_events,
    norm_text,
    project_event,
    reset_stable_id_registry,
    today_nyc_approx,
    utc_now,
)

STAGED_PATH = ROOT / "data" / "nycif_staged_live_events.json"
ALL_PATH = ROOT / "nycif_all_radar_map_events.json"
LEGACY_MAJOR_PATH = ROOT / "nycif_major_radar_map_events.json"
STAGED_SCHEMA_PATH = ROOT / "data" / "events_schema_v1_staged.json"
OUT_MAJOR = ROOT / "data" / "events_schema_v1_major.json"
OUT_REPORT = ROOT / "data" / "events_schema_v1_major_report.json"

# Inclusive window matches Field Desk dayRange (today .. today+7).
DEFAULT_MAX_MAJOR = 900
SCORE_THRESHOLD = 180


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def seid(row: dict) -> str:
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    return str(nested.get("source_event_id") or row.get("source_event_id") or "").strip()


def legacy_seid(row: dict) -> str:
    if row.get("source_event_id"):
        return str(row["source_event_id"]).strip()
    rid = str(row.get("id") or "")
    if ":" in rid:
        return rid.split(":")[-1].strip()
    return rid.strip()


def score_event(row: dict, carried: dict | None = None) -> tuple[int, list[str], dict]:
    """Return major_score, selection_rules, major_meta overlay."""
    carried = carried or {}
    rules: list[str] = []
    score = 0

    text = norm_text(
        " ".join(
            str(v)
            for v in (
                row.get("title"),
                row.get("search_label"),
                row.get("event_type"),
                row.get("type"),
                row.get("event_agency"),
                row.get("location"),
                row.get("display_location"),
                row.get("major_reason"),
                row.get("verification_status"),
                row.get("nypd_notice"),
                row.get("lane"),
                carried.get("major_reason"),
            )
            if v
        )
    )
    event_type = norm_text(row.get("event_type") or row.get("type"))

    field_default = bool(carried.get("field_default") or row.get("field_default"))
    photo_pick = bool(carried.get("photo_pick") or row.get("photo_pick"))
    assignment = carried.get("assignment_feed") or row.get("assignment_feed")
    crowd = carried.get("crowd_level") or row.get("crowd_level")
    verification = carried.get("verification_status") or row.get("verification_status")
    priority_score = carried.get("priority_score") or row.get("priority_score")
    expected = carried.get("expected_crowd_score") or row.get("expected_crowd_score")
    major_reason = carried.get("major_reason") or row.get("major_reason")

    if field_default:
        score += 500
        rules.append("field_default")
    if assignment == "major":
        score += 400
        rules.append("assignment_feed_major")
    if verification == "nypd_field_intel" or "nypd" in text:
        score += 1000
        rules.append("nypd_field_intel")
    if photo_pick:
        score += 250
        rules.append("photo_pick")
    if crowd == "very_high":
        score += 400
        rules.append("crowd_very_high")
    elif crowd == "high":
        score += 260
        rules.append("crowd_high")
    elif crowd == "medium_high":
        score += 160
        rules.append("crowd_medium_high")
    elif crowd == "medium":
        score += 80
        rules.append("crowd_medium")

    try:
        score += min(int(expected or 0), 400)
        if expected:
            rules.append("expected_crowd_score")
    except (TypeError, ValueError):
        pass
    try:
        score += min(int(priority_score or 0), 200)
        if priority_score:
            rules.append("priority_score")
    except (TypeError, ValueError):
        pass

    # Explicit event types (not every Sport Youth/Adult).
    if event_type in {"parade"}:
        score += 220
        rules.append("event_type_parade")
    if event_type in {"farmers market", "plaza partner event", "plaza event"}:
        score += 160
        rules.append("event_type_market_plaza")
    if event_type in {"block party", "street event", "open street partner event", "open culture"}:
        score += 140
        rules.append("event_type_street_activation")
    if event_type in {"athletic race / tour"}:
        score += 200
        rules.append("event_type_athletic_race")
    if event_type in {"religious event", "production event"}:
        score += 90
        rules.append("event_type_public_activation")

    keyword_rules = [
        (220, r"world cup|fifa|fan zone", "keyword_world_cup_fan_zone"),
        (200, r"\bpride\b", "keyword_pride"),
        (200, r"\bparade\b|\bmarch\b|\brally\b|\bvigil\b|\bceremony\b", "keyword_civic_gathering"),
        (180, r"street fair|festival|merchandise fair|feast", "keyword_street_fair_festival"),
        (170, r"marathon|criterium|5k|10k|half marathon|tour|race", "keyword_spectator_race"),
        (120, r"farmers market|greenmarket|street market", "keyword_market"),
        (150, r"strong visual|waterfront|hudson yards|javits|rockefeller|dumbo|times square", "keyword_visual_location"),
        (150, r"special event", "keyword_special_event"),
    ]
    for points, pattern, rule in keyword_rules:
        if re.search(pattern, text) and rule not in rules:
            score += points
            rules.append(rule)

    # Suppress routine athletic permits unless stronger signals already present.
    if re.search(r"sport - youth|sport - adult|softball|baseball|basketball|soccer", text):
        if not any(
            r.startswith(("nypd", "photo", "crowd_", "assignment", "field_default", "keyword_world", "keyword_spectator", "event_type_athletic"))
            for r in rules
        ):
            score = min(score, 40)
            rules.append("routine_sport_suppressed")

    meta = {
        "is_major": False,
        "major_score": score,
        "major_reason": major_reason or (", ".join(rules[:4]) if rules else None),
        "photo_pick": photo_pick or bool(re.search(r"world cup|fan zone|pride|parade|street fair|festival", text)),
        "field_default": field_default,
        "crowd_level": crowd,
        "priority_score": priority_score,
        "expected_crowd_score": expected,
        "assignment_feed": "major" if score >= SCORE_THRESHOLD or assignment == "major" or field_default else assignment,
        "verification_status": verification,
        "selection_rules": rules,
    }
    return score, rules, meta


def choose_threshold(scores: list[int]) -> int:
    # Prefer configured threshold unless it would create an empty upcoming major set.
    return SCORE_THRESHOLD


def main() -> int:
    generated_at = utc_now()
    today = today_nyc_approx()
    end7 = today + timedelta(days=7)
    today_s, end7_s = today.isoformat(), end7.isoformat()

    staged_rows = extract_events(json.loads(STAGED_PATH.read_text(encoding="utf-8")))
    all_rows = extract_events(json.loads(ALL_PATH.read_text(encoding="utf-8"))) if ALL_PATH.exists() else []
    legacy_major = extract_events(json.loads(LEGACY_MAJOR_PATH.read_text(encoding="utf-8"))) if LEGACY_MAJOR_PATH.exists() else []

    # Index carry-forward signals from legacy major by source_event_id and title+date.
    carried_by_seid: dict[str, dict] = {}
    carried_by_title_date: dict[tuple[str, str], dict] = {}
    for row in legacy_major:
        payload = {
            "field_default": row.get("field_default"),
            "photo_pick": row.get("photo_pick"),
            "assignment_feed": row.get("assignment_feed"),
            "crowd_level": row.get("crowd_level"),
            "priority_score": row.get("priority_score"),
            "expected_crowd_score": row.get("expected_crowd_score"),
            "major_reason": row.get("major_reason"),
            "verification_status": row.get("verification_status"),
            "_manual_priority": row.get("_manual_priority"),
        }
        sid = legacy_seid(row)
        if sid:
            carried_by_seid[sid] = payload
        title = norm_text(row.get("title") or row.get("search_label"))
        d = str(row.get("date") or "")[:10]
        if title and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            carried_by_title_date[(title, d)] = payload

    # Prefer staged; fill gaps from all-radar by id.
    by_id = {str(r.get("id")): r for r in all_rows if r.get("id")}
    for r in staged_rows:
        by_id[str(r.get("id"))] = r
    candidates = list(by_id.values())

    scored = []
    rule_counter = Counter()
    score_hist = Counter()
    reset_stable_id_registry()
    for i, row in enumerate(candidates):
        sid = seid(row)
        d = str(row.get("date") or "")[:10]
        title = norm_text(row.get("title") or row.get("name"))
        carried = carried_by_seid.get(sid) or carried_by_title_date.get((title, d))
        score, rules, meta = score_event(row, carried)
        for rule in rules:
            rule_counter[rule] += 1
        bucket = f"{(score // 50) * 50}-{(score // 50) * 50 + 49}"
        score_hist[bucket] += 1
        scored.append((score, rules, meta, row, i))

    threshold = choose_threshold([s for s, *_ in scored])
    selected = []
    for score, rules, meta, row, i in scored:
        include = (
            score >= threshold
            or meta.get("field_default")
            or meta.get("assignment_feed") == "major"
            or meta.get("verification_status") == "nypd_field_intel"
            or "nypd_field_intel" in rules
        )
        # Always include carried field_default rows that still exist.
        if not include:
            continue
        meta = dict(meta)
        meta["is_major"] = True
        meta["assignment_feed"] = "major"
        meta["major_score"] = score
        event = project_event(
            row,
            index=i,
            data_layer="approved_staged",
            production_feed=True,
            major_meta=meta,
        )
        event["significance"] = "major"
        event["nycif"]["is_major"] = True
        selected.append(event)

    # Prefer upcoming, keep past only when needed for continuity, cap rows.
    selected.sort(
        key=lambda e: (
            0 if (event_date_key(e) or "") >= today_s else 1,
            -(e["nycif"].get("major_score") or 0),
            event_date_key(e) or "9999",
            e.get("title") or "",
        )
    )
    if len(selected) > DEFAULT_MAX_MAJOR:
        upcoming = [e for e in selected if (event_date_key(e) or "") >= today_s]
        past = [e for e in selected if (event_date_key(e) or "") < today_s]
        selected = (upcoming + past)[:DEFAULT_MAX_MAJOR]

    major_env = envelope(selected, generated_at_utc=generated_at, next_cursor=None)

    upcoming = [e for e in selected if (event_date_key(e) or "") >= today_s]
    today_rows = [e for e in selected if event_date_key(e) == today_s]
    next7_rows = [e for e in selected if today_s <= (event_date_key(e) or "") <= end7_s]
    dates = [event_date_key(e) for e in selected if event_date_key(e)]

    excluded_high = sorted(
        [
            {
                "id": str(row.get("id")),
                "title": row.get("title") or row.get("name"),
                "date": str(row.get("date") or "")[:10],
                "score": score,
                "rules": rules,
            }
            for score, rules, meta, row, i in scored
            if score >= threshold - 40 and not (
                score >= threshold
                or meta.get("field_default")
                or meta.get("assignment_feed") == "major"
                or meta.get("verification_status") == "nypd_field_intel"
                or "nypd_field_intel" in rules
            )
        ],
        key=lambda x: -x["score"],
    )[:20]

    # Freshness vs approved schema
    staged_schema = None
    if STAGED_SCHEMA_PATH.exists():
        staged_schema = json.loads(STAGED_SCHEMA_PATH.read_text(encoding="utf-8"))
    approved_generated = (staged_schema or {}).get("generated_at_utc")
    approved_upcoming = 0
    if staged_schema:
        for e in extract_events(staged_schema):
            d = event_date_key(e)
            if d and d >= today_s:
                approved_upcoming += 1

    only_past = bool(dates) and max(dates) < today_s
    freshness_fail = bool(approved_upcoming > 0 and (only_past or len(upcoming) == 0))

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "reference_today_nyc": today_s,
        "score_threshold": threshold,
        "max_rows": DEFAULT_MAX_MAJOR,
        "total_input_records": len(candidates),
        "total_major_records": len(selected),
        "major_count_today": len(today_rows),
        "major_count_next_seven_days": len(next7_rows),
        "major_count_all_upcoming": len(upcoming),
        "count_by_category": dict(Counter(e.get("category") for e in selected).most_common()),
        "count_by_borough": dict(Counter(e.get("borough") for e in selected).most_common()),
        "count_by_selection_rule": dict(rule_counter.most_common()),
        "score_distribution": dict(sorted(score_hist.items(), key=lambda kv: int(kv[0].split("-")[0]))),
        "sample_included_records": [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "date": event_date_key(e),
                "category": e.get("category"),
                "borough": e.get("borough"),
                "major_score": e["nycif"].get("major_score"),
                "major_reason": e["nycif"].get("major_reason"),
                "selection_rules": e["nycif"].get("selection_rules"),
            }
            for e in selected[:15]
        ],
        "sample_excluded_high_scoring_records": excluded_high,
        "earliest_major_date": min(dates) if dates else None,
        "latest_major_date": max(dates) if dates else None,
        "selection_rules_documentation": [
            "field_default explicit",
            "assignment_feed == major",
            "NYPD field intel / verification_status",
            "photo_pick",
            "crowd_level weights (very_high/high/medium_high/medium)",
            "expected_crowd_score / priority_score capped contributions",
            "event_type parade / market / street activation / athletic race",
            "keywords: world cup/fan zone, pride, civic gatherings, street fairs, spectator races, visual landmarks",
            "routine Sport Youth/Adult permits suppressed unless stronger signals present",
            f"score threshold >= {threshold} OR explicit field_default/assignment/NYPD",
            "carry-forward of legacy major radar signals by source_event_id or title+date",
        ],
        "freshness": {
            "approved_schema_generated_at_utc": approved_generated,
            "approved_upcoming_count": approved_upcoming,
            "major_upcoming_count": len(upcoming),
            "major_only_past_dates": only_past,
            "qa_fail_stale_major": freshness_fail,
        },
        "safety": {
            "location_cache_modified": False,
            "staged_feed_modified": False,
            "public_map_modified": False,
            "supplemental_promoted": False,
            "legacy_major_file_rewritten": False,
        },
        "qa_pass": (not freshness_fail) and len(selected) > 0 and len(upcoming) > 0,
    }

    write_json(OUT_MAJOR, major_env)
    write_json(OUT_REPORT, report)
    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "total_major": report["total_major_records"],
                "upcoming": report["major_count_all_upcoming"],
                "next7": report["major_count_next_seven_days"],
                "today": report["major_count_today"],
                "report": str(OUT_REPORT),
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
