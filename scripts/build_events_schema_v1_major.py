#!/usr/bin/env python3
"""Build schema-v1 major events feed from current approved data."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from schema_v1_common import (  # noqa: E402
    SCHEMA_VERSION,
    ISO_DATE_RE,
    envelope,
    event_date_key,
    extract_events,
    norm_text,
    project_event,
    reset_stable_id_registry,
    write_repo_json,
    today_nyc_approx,
    utc_now,
)

STAGED_PATH = ROOT / "data" / "nycif_staged_live_events.json"
ALL_PATH = ROOT / "nycif_all_radar_map_events.json"
LEGACY_MAJOR_PATH = ROOT / "nycif_major_radar_map_events.json"
STAGED_SCHEMA_PATH = ROOT / "data" / "events_schema_v1_staged.json"
OUT_MAJOR = ROOT / "data" / "events_schema_v1_major.json"
OUT_REPORT = ROOT / "data" / "events_schema_v1_major_report.json"

DEFAULT_MAX_MAJOR = 900
SCORE_THRESHOLD = 180

CARRIED_ONLY_BOOSTERS = {
    "field_default",
    "assignment_feed_major",
    "nypd_field_intel",
    "photo_pick",
    "crowd_very_high",
    "crowd_high",
    "crowd_medium_high",
    "crowd_medium",
    "expected_crowd_score",
    "priority_score",
}


def seid(row: dict) -> str:
    nested = row.get("source") if isinstance(row.get("source"), dict) else {}
    return str(nested.get("source_event_id") or row.get("source_event_id") or "").strip()


def legacy_seid(row: dict) -> str:
    if row.get("source_event_id"):
        return str(row["source_event_id"]).strip()
    rid = str(row.get("id") or "")
    return rid.split(":")[-1].strip() if ":" in rid else rid.strip()


def carried_payload(row: dict) -> dict:
    return {
        "field_default": row.get("field_default"),
        "photo_pick": row.get("photo_pick"),
        "assignment_feed": row.get("assignment_feed"),
        "crowd_level": row.get("crowd_level"),
        "priority_score": row.get("priority_score"),
        "expected_crowd_score": row.get("expected_crowd_score"),
        "major_reason": row.get("major_reason"),
        "verification_status": row.get("verification_status"),
        "_manual_priority": row.get("_manual_priority"),
        "legacy_title": row.get("title") or row.get("search_label"),
        "legacy_date": str(row.get("date") or "")[:10],
        "legacy_borough": row.get("borough"),
        "legacy_location": row.get("display_location") or row.get("location"),
    }


def index_legacy(legacy_major: list[dict]) -> tuple[dict[str, dict], dict[tuple[str, str, str], dict]]:
    by_seid: dict[str, dict] = {}
    by_title_date_loc: dict[tuple[str, str, str], dict] = {}
    for row in legacy_major:
        payload = carried_payload(row)
        sid = legacy_seid(row)
        if sid:
            by_seid[sid] = payload
        title = norm_text(row.get("title") or row.get("search_label"))
        day = str(row.get("date") or "")[:10]
        loc = norm_text(row.get("display_location") or row.get("location") or row.get("borough"))
        if title and ISO_DATE_RE.fullmatch(day):
            by_title_date_loc[(title, day, loc)] = payload
    return by_seid, by_title_date_loc


def match_legacy(
    row: dict,
    by_seid: dict[str, dict],
    by_title_date_loc: dict[tuple[str, str, str], dict],
) -> tuple[dict | None, str | None]:
    sid = seid(row)
    if sid and sid in by_seid:
        return by_seid[sid], "legacy_source_event_id"
    title = norm_text(row.get("title") or row.get("name"))
    day = str(row.get("date") or "")[:10]
    loc = norm_text(row.get("display_location") or row.get("location") or row.get("borough"))
    key = (title, day, loc)
    if title and ISO_DATE_RE.fullmatch(day) and key in by_title_date_loc:
        return by_title_date_loc[key], "legacy_title_date_location"
    # Require location/borough when using title+date — do not match title+date alone.
    return None, None


def add_score(score: int, rules: list[str], points: int, rule: str) -> int:
    if rule not in rules:
        rules.append(rule)
    return score + points


def scoring_text(row: dict, carried: dict | None) -> str:
    carried = carried or {}
    return norm_text(
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
                carried.get("major_reason"),
            )
            if v
        )
    )


def carried_field_values(row: dict, carried: dict | None) -> dict:
    carried = carried or {}
    return {
        "field_default": bool(carried.get("field_default") or row.get("field_default")),
        "photo_pick": bool(carried.get("photo_pick") or row.get("photo_pick")),
        "assignment": carried.get("assignment_feed") or row.get("assignment_feed"),
        "crowd": carried.get("crowd_level") or row.get("crowd_level"),
        "verification": carried.get("verification_status") or row.get("verification_status"),
        "priority_score": carried.get("priority_score") or row.get("priority_score"),
        "expected": carried.get("expected_crowd_score") or row.get("expected_crowd_score"),
        "major_reason": carried.get("major_reason") or row.get("major_reason"),
    }


def score_explicit_fields(score: int, rules: list[str], fields: dict, text: str) -> int:
    if fields["field_default"]:
        score = add_score(score, rules, 500, "field_default")
    if fields["assignment"] == "major":
        score = add_score(score, rules, 400, "assignment_feed_major")
    if fields["verification"] == "nypd_field_intel" or "nypd" in text:
        score = add_score(score, rules, 1000, "nypd_field_intel")
    if fields["photo_pick"]:
        score = add_score(score, rules, 250, "photo_pick")
    return score


def score_crowd(score: int, rules: list[str], crowd: str | None, expected: Any, priority_score: Any) -> int:
    crowd_points = {
        "very_high": (400, "crowd_very_high"),
        "high": (260, "crowd_high"),
        "medium_high": (160, "crowd_medium_high"),
        "medium": (80, "crowd_medium"),
    }
    if crowd in crowd_points:
        points, rule = crowd_points[crowd]
        score = add_score(score, rules, points, rule)
    try:
        if expected:
            score = add_score(score, rules, min(int(expected), 400), "expected_crowd_score")
    except (TypeError, ValueError):
        pass
    try:
        if priority_score:
            score = add_score(score, rules, min(int(priority_score), 200), "priority_score")
    except (TypeError, ValueError):
        pass
    return score


def score_event_type(score: int, rules: list[str], event_type: str) -> int:
    type_points = {
        "parade": (220, "event_type_parade"),
        "farmers market": (160, "event_type_market_plaza"),
        "plaza partner event": (160, "event_type_market_plaza"),
        "plaza event": (160, "event_type_market_plaza"),
        "block party": (140, "event_type_street_activation"),
        "street event": (140, "event_type_street_activation"),
        "open street partner event": (140, "event_type_street_activation"),
        "open culture": (140, "event_type_street_activation"),
        "athletic race / tour": (200, "event_type_athletic_race"),
        "religious event": (90, "event_type_public_activation"),
        "production event": (90, "event_type_public_activation"),
    }
    if event_type in type_points:
        points, rule = type_points[event_type]
        score = add_score(score, rules, points, rule)
    return score


def score_keywords(score: int, rules: list[str], text: str) -> int:
    for points, pattern, rule in [
        (220, r"world cup|fifa|fan zone", "keyword_world_cup_fan_zone"),
        (200, r"\bpride\b", "keyword_pride"),
        (200, r"\bparade\b|\bmarch\b|\brally\b|\bvigil\b|\bceremony\b", "keyword_civic_gathering"),
        (180, r"street fair|festival|merchandise fair|feast", "keyword_street_fair_festival"),
        (170, r"marathon|criterium|5k|10k|half marathon|tour|race", "keyword_spectator_race"),
        (120, r"farmers market|greenmarket|street market", "keyword_market"),
        (150, r"strong visual|waterfront|hudson yards|javits|rockefeller|dumbo|times square", "keyword_visual_location"),
    ]:
        if re.search(pattern, text):
            score = add_score(score, rules, points, rule)
    return score


def apply_sport_suppression(score: int, rules: list[str], text: str) -> int:
    if not re.search(r"sport - youth|sport - adult|softball|baseball|basketball|soccer", text):
        return score
    strong = any(
        r.startswith(
            (
                "nypd",
                "photo",
                "crowd_",
                "assignment",
                "field_default",
                "keyword_world",
                "keyword_spectator",
                "event_type_athletic",
            )
        )
        for r in rules
    )
    if strong:
        return score
    rules.append("routine_sport_suppressed")
    return min(score, 40)


def build_score_meta(fields: dict, score: int, rules: list[str], text: str) -> dict:
    return {
        "is_major": False,
        "major_score": score,
        "major_reason": fields["major_reason"] or (", ".join(rules[:4]) if rules else None),
        "photo_pick": fields["photo_pick"]
        or bool(re.search(r"world cup|fan zone|pride|parade|street fair|festival", text)),
        "field_default": fields["field_default"],
        "crowd_level": fields["crowd"],
        "priority_score": fields["priority_score"],
        "expected_crowd_score": fields["expected"],
        "assignment_feed": fields["assignment"],
        "verification_status": fields["verification"],
        "selection_rules": rules,
    }


def score_event(row: dict, carried: dict | None = None) -> tuple[int, list[str], dict]:
    fields = carried_field_values(row, carried)
    rules: list[str] = []
    text = scoring_text(row, carried)
    event_type = norm_text(row.get("event_type") or row.get("type"))
    score = 0
    score = score_explicit_fields(score, rules, fields, text)
    score = score_crowd(score, rules, fields["crowd"], fields["expected"], fields["priority_score"])
    score = score_event_type(score, rules, event_type)
    score = score_keywords(score, rules, text)
    score = apply_sport_suppression(score, rules, text)
    meta = build_score_meta(fields, score, rules, text)
    return score, rules, meta


def major_source_label(rules: list[str], legacy_match: str | None, included: bool) -> str:
    if not included:
        return "excluded"
    if "field_default" in rules or "assignment_feed_major" in rules:
        return "current_explicit_fields"
    if "nypd_field_intel" in rules:
        return "nypd_or_field_intel"
    has_current_doc = any(
        r.startswith(("event_type_", "keyword_", "crowd_", "expected_", "priority_", "photo_"))
        for r in rules
    )
    if has_current_doc and not legacy_match:
        if any(r.startswith(("event_type_", "keyword_")) for r in rules):
            return "documented_event_rules"
        return "current_score"
    if legacy_match and not has_current_doc:
        return "legacy_carryover_only"
    if legacy_match and has_current_doc:
        return "current_score_with_legacy_signal"
    return "current_score"


def is_carried_only_rules(rules: list[str]) -> bool:
    if any(r.startswith(("event_type_", "keyword_")) for r in rules):
        return False
    return all(r in CARRIED_ONLY_BOOSTERS for r in rules)


def legacy_only_sample(row: dict, legacy_match: str | None, score: int, score_no_legacy: int, meta: dict) -> dict:
    return {
        "id": str(row.get("id")),
        "title": row.get("title") or row.get("name"),
        "date": str(row.get("date") or "")[:10],
        "borough": row.get("borough"),
        "legacy_match": legacy_match,
        "score_with_legacy": score,
        "score_without_legacy": score_no_legacy,
        "major_reason": meta.get("major_reason"),
    }


def classify_major_source(
    row: dict,
    *,
    rules: list[str],
    legacy_match: str | None,
    include: bool,
    score: int,
    meta: dict,
    legacy_only_samples: list[dict],
) -> str:
    source = major_source_label(rules, legacy_match, include)
    if not legacy_match or not include:
        return source
    if not is_carried_only_rules(rules):
        return source
    score_no_legacy, rules_no_legacy, meta_no_legacy = score_event(row, None)
    if not should_include(score_no_legacy, meta_no_legacy, rules_no_legacy):
        if len(legacy_only_samples) < 40:
            legacy_only_samples.append(
                legacy_only_sample(row, legacy_match, score, score_no_legacy, meta)
            )
        return "legacy_carryover_only"
    return source


def should_include(score: int, meta: dict, rules: list[str]) -> bool:
    return (
        score >= SCORE_THRESHOLD
        or bool(meta.get("field_default"))
        or meta.get("assignment_feed") == "major"
        or meta.get("verification_status") == "nypd_field_intel"
        or "nypd_field_intel" in rules
    )


def build_candidate_index(staged_rows: list[dict], all_rows: list[dict]) -> list[dict]:
    by_id = {str(r.get("id")): r for r in all_rows if r.get("id")}
    for row in staged_rows:
        by_id[str(row.get("id"))] = row
    return list(by_id.values())


def load_pipeline_inputs() -> tuple[list[dict], list[dict], list[dict], dict[str, dict], dict]:
    staged_rows = extract_events(json.loads(STAGED_PATH.read_text(encoding="utf-8")))
    all_rows = extract_events(json.loads(ALL_PATH.read_text(encoding="utf-8"))) if ALL_PATH.exists() else []
    legacy_major = (
        extract_events(json.loads(LEGACY_MAJOR_PATH.read_text(encoding="utf-8")))
        if LEGACY_MAJOR_PATH.exists()
        else []
    )
    by_seid, by_tdl = index_legacy(legacy_major)
    candidates = build_candidate_index(staged_rows, all_rows)
    return staged_rows, legacy_major, candidates, by_seid, by_tdl


def score_and_select(
    candidates: list[dict],
    by_seid: dict[str, dict],
    by_tdl: dict,
) -> tuple[list[dict], list, Counter, Counter, Counter, Counter, list]:
    reset_stable_id_registry()
    selected = []
    rule_counter = Counter()
    score_hist = Counter()
    source_counter = Counter()
    legacy_only_samples = []
    scored_rows = []

    for index, row in enumerate(candidates):
        carried, legacy_match = match_legacy(row, by_seid, by_tdl)
        score, rules, meta = score_event(row, carried)
        for rule in rules:
            rule_counter[rule] += 1
        bucket = f"{(score // 50) * 50}-{(score // 50) * 50 + 49}"
        score_hist[bucket] += 1
        include = should_include(score, meta, rules)
        source = classify_major_source(
            row,
            rules=rules,
            legacy_match=legacy_match,
            include=include,
            score=score,
            meta=meta,
            legacy_only_samples=legacy_only_samples,
        )

        scored_rows.append((score, rules, meta, row, index, source, legacy_match))
        if not include:
            continue
        source_counter[source] += 1
        meta = dict(meta)
        meta["is_major"] = True
        meta["assignment_feed"] = "major"
        meta["major_score"] = score
        meta["major_source"] = source
        meta["selection_rules"] = rules + ([f"legacy_match:{legacy_match}"] if legacy_match else [])
        event = project_event(
            row,
            index=index,
            data_layer="approved_staged",
            major_meta=meta,
        )
        event["significance"] = "major"
        event["nycif"]["is_major"] = True
        selected.append(event)

    return selected, scored_rows, rule_counter, score_hist, source_counter, legacy_only_samples


def sort_and_cap_major(selected: list[dict], today_s: str) -> list[dict]:
    selected.sort(
        key=lambda e: (
            0 if (event_date_key(e) or "") >= today_s else 1,
            -(e["nycif"].get("major_score") or 0),
            event_date_key(e) or "9999",
            e.get("title") or "",
        )
    )
    if len(selected) <= DEFAULT_MAX_MAJOR:
        return selected
    upcoming = [e for e in selected if (event_date_key(e) or "") >= today_s]
    past = [e for e in selected if (event_date_key(e) or "") < today_s]
    return (upcoming + past)[:DEFAULT_MAX_MAJOR]


def legacy_drop_ids(scored_rows: list) -> list[str]:
    without_legacy = []
    for score, rules, meta, row, _index, _source, _legacy_match in scored_rows:
        score2, rules2, meta2 = score_event(row, None)
        if should_include(score, meta, rules) and not should_include(score2, meta2, rules2):
            without_legacy.append(str(row.get("id")))
    return without_legacy


def load_staged_schema() -> dict | None:
    if not STAGED_SCHEMA_PATH.exists():
        return None
    return json.loads(STAGED_SCHEMA_PATH.read_text(encoding="utf-8"))


def count_approved_upcoming(staged_schema: dict | None, today_s: str) -> int:
    if not staged_schema:
        return 0
    approved_upcoming = 0
    for event in extract_events(staged_schema):
        day = event_date_key(event)
        if day and day >= today_s:
            approved_upcoming += 1
    return approved_upcoming


def build_major_report(
    *,
    generated_at: str,
    today_s: str,
    end7_s: str,
    candidates: list[dict],
    selected: list[dict],
    rule_counter: Counter,
    score_hist: Counter,
    source_counter: Counter,
    legacy_only_samples: list,
    without_legacy: list[str],
    staged_schema: dict | None,
    approved_upcoming: int,
) -> dict:
    upcoming = [e for e in selected if (event_date_key(e) or "") >= today_s]
    today_rows = [e for e in selected if event_date_key(e) == today_s]
    next7_rows = [e for e in selected if today_s <= (event_date_key(e) or "") <= end7_s]
    dates = [event_date_key(e) for e in selected if event_date_key(e)]
    only_past = bool(dates) and max(dates) < today_s
    freshness_fail = bool(approved_upcoming > 0 and (only_past or len(upcoming) == 0))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "reference_today_nyc": today_s,
        "score_threshold": SCORE_THRESHOLD,
        "max_rows": DEFAULT_MAX_MAJOR,
        "total_input_records": len(candidates),
        "total_major_records": len(selected),
        "major_count_today": len(today_rows),
        "major_count_next_seven_days": len(next7_rows),
        "major_count_all_upcoming": len(upcoming),
        "count_by_category": dict(Counter(e.get("category") for e in selected).most_common()),
        "count_by_borough": dict(Counter(e.get("borough") for e in selected).most_common()),
        "count_by_selection_rule": dict(rule_counter.most_common()),
        "count_by_major_source": dict(source_counter.most_common()),
        "legacy_carryover_only_count": source_counter.get("legacy_carryover_only", 0),
        "would_stop_being_major_without_legacy_count": len(without_legacy),
        "legacy_carryover_only_samples": legacy_only_samples[:25],
        "score_distribution": dict(sorted(score_hist.items(), key=lambda kv: int(kv[0].split("-")[0]))),
        "sample_included_records": [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "date": event_date_key(e),
                "category": e.get("category"),
                "borough": e.get("borough"),
                "major_score": e["nycif"].get("major_score"),
                "major_source": e["nycif"].get("major_source"),
                "major_reason": e["nycif"].get("major_reason"),
                "selection_rules": e["nycif"].get("selection_rules"),
            }
            for e in selected[:15]
        ],
        "earliest_major_date": min(dates) if dates else None,
        "latest_major_date": max(dates) if dates else None,
        "legacy_match_requirements": [
            "same source_event_id",
            "OR same normalized title + same event date + same location/borough",
            "title+date alone is not enough",
        ],
        "selection_rules_documentation": [
            "field_default explicit",
            "assignment_feed == major",
            "NYPD field intel / verification_status",
            "photo_pick",
            "crowd_level weights",
            "expected_crowd_score / priority_score capped contributions",
            "event_type parade / market / street activation / athletic race",
            "keywords: world cup/fan zone, pride, civic gatherings, street fairs, spectator races",
            "routine Sport Youth/Adult permits suppressed unless stronger signals present",
            f"score threshold >= {SCORE_THRESHOLD} OR explicit field_default/assignment/NYPD",
            "legacy major signals only via source_event_id or title+date+location/borough",
        ],
        "freshness": {
            "approved_schema_generated_at_utc": (staged_schema or {}).get("generated_at_utc"),
            "approved_upcoming_count": approved_upcoming,
            "major_upcoming_count": len(upcoming),
            "major_only_past_dates": only_past,
            "qa_fail_stale_major": freshness_fail,
            "legacy_major_file_is_production_feed": False,
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


def main() -> int:
    generated_at = utc_now()
    today = today_nyc_approx()
    end7 = today + timedelta(days=7)
    today_s, end7_s = today.isoformat(), end7.isoformat()

    _staged_rows, _legacy_major, candidates, by_seid, by_tdl = load_pipeline_inputs()
    selected, scored_rows, rule_counter, score_hist, source_counter, legacy_only_samples = score_and_select(
        candidates, by_seid, by_tdl
    )
    selected = sort_and_cap_major(selected, today_s)
    without_legacy = legacy_drop_ids(scored_rows)
    staged_schema = load_staged_schema()
    approved_upcoming = count_approved_upcoming(staged_schema, today_s)

    major_env = envelope(selected, generated_at_utc=generated_at, next_cursor=None)
    report = build_major_report(
        generated_at=generated_at,
        today_s=today_s,
        end7_s=end7_s,
        candidates=candidates,
        selected=selected,
        rule_counter=rule_counter,
        score_hist=score_hist,
        source_counter=source_counter,
        legacy_only_samples=legacy_only_samples,
        without_legacy=without_legacy,
        staged_schema=staged_schema,
        approved_upcoming=approved_upcoming,
    )

    write_repo_json("data/events_schema_v1_major.json", major_env)
    write_repo_json("data/events_schema_v1_major_report.json", report)
    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "total_major": report["total_major_records"],
                "upcoming": report["major_count_all_upcoming"],
                "next7": report["major_count_next_seven_days"],
                "today": report["major_count_today"],
                "legacy_only": report["legacy_carryover_only_count"],
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
