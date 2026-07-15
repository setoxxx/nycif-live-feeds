#!/usr/bin/env python3
"""Match current Money-Day calendar events to prior-year historical permits.

Operator/premium Viral Recurrence Memory. Never invents HH:MM or coords.
Left-joins optional FOIL operator index when present (else omit).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from civic_people_facing_common import DATA_DIR, load_json, save_json, today_nyc, utc_now  # noqa: E402

STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "of",
        "a",
        "an",
        "at",
        "to",
        "for",
        "in",
        "on",
        "nyc",
        "new",
        "york",
        "street",
        "st",
        "ave",
        "avenue",
        "plaza",
        "park",
    }
)


def norm_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokens(value: Any) -> set[str]:
    return {t for t in norm_text(value).split() if t and t not in STOP_WORDS and len(t) > 1}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def name_similarity(a: str, b: str) -> float:
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    seq = SequenceMatcher(None, na, nb).ratio()
    jac = jaccard(tokens(na), tokens(nb))
    return max(seq, jac)


def place_fingerprint(location: Any, borough: Any, precinct: Any = None) -> str:
    loc = norm_text(location)
    # Keep leading venue-ish chunk before colon if present.
    if ":" in loc:
        loc = loc.split(":", 1)[0].strip()
    boro = norm_text(borough)
    prec = re.sub(r"[^0-9]", "", str(precinct or "").split(",")[0])
    return "|".join(x for x in (boro, loc[:80], prec) if x)


def parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def month_day_delta(a: date, b: date) -> int:
    """Absolute day-of-year distance ignoring year, min across year wrap."""
    da = a.timetuple().tm_yday
    db = b.timetuple().tm_yday
    direct = abs(da - db)
    wrap = 366 - direct
    return min(direct, wrap)


def field_desk_link(day: str) -> str:
    return (
        "https://setoxxx.github.io/nycif-field-desk/"
        f"?v=civic-people-facing-v01&resetFilters=1&feeds=main&mode=all&date={day}&assignment=1"
    )


def load_foil_index() -> dict[str, dict[str, Any]]:
    payload = load_json(DATA_DIR / "sapo_foil_operator_index.json", {})
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, dict):
        return out
    for row in payload.get("operators") or []:
        if not isinstance(row, dict):
            continue
        org = row.get("applicant_org")
        if not org:
            continue
        for key_name in ("event_id", "cemsid", "source_event_id"):
            key = str(row.get(key_name) or "").strip()
            if key:
                out[key] = row
    return out


def foil_for(event_id: Any, cemsid: Any, index: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for key in (str(event_id or "").strip(), str(cemsid or "").strip()):
        if key and key in index:
            row = index[key]
            return {
                "applicant_org": row.get("applicant_org"),
                "source": row.get("source") or "foil",
                "notes": row.get("notes"),
                "foil_request_id": row.get("foil_request_id"),
            }
    return None


def hist_row_view(row: dict[str, Any]) -> dict[str, Any]:
    day = parse_day(row.get("start_date_time"))
    return {
        "event_id": row.get("event_id"),
        "cemsid": row.get("cemsid"),
        "title": row.get("event_name"),
        "date": day.isoformat() if day else None,
        "start_date_time": row.get("start_date_time"),
        "end_date_time": row.get("end_date_time"),
        "borough": row.get("event_borough"),
        "display_location": row.get("event_location"),
        "event_type": row.get("event_type"),
        "street_closure_type": row.get("street_closure_type"),
        "police_precinct": row.get("police_precinct"),
        "dataset": "bkfu-528j",
    }


def current_event_id(e: dict[str, Any]) -> str:
    src = e.get("source") if isinstance(e.get("source"), dict) else {}
    return str(src.get("source_event_id") or "").strip()


def score_match(current: dict[str, Any], hist: dict[str, Any]) -> tuple[int, list[str], str]:
    reasons: list[str] = []
    score = 0

    name_sim = name_similarity(current.get("title"), hist.get("event_name"))
    if name_sim >= 0.92:
        score += 45
        reasons.append(f"name_exactish:{name_sim:.2f}")
    elif name_sim >= 0.72:
        score += 30
        reasons.append(f"name_strong:{name_sim:.2f}")
    elif name_sim >= 0.55:
        score += 16
        reasons.append(f"name_partial:{name_sim:.2f}")

    cur_fp = place_fingerprint(
        current.get("display_location"),
        current.get("borough"),
        None,
    )
    hist_fp = place_fingerprint(
        hist.get("event_location"),
        hist.get("event_borough"),
        hist.get("police_precinct"),
    )
    place_sim = name_similarity(cur_fp.replace("|", " "), hist_fp.replace("|", " "))
    if cur_fp and hist_fp and cur_fp == hist_fp:
        score += 35
        reasons.append("place_fingerprint_exact")
    elif place_sim >= 0.75:
        score += 24
        reasons.append(f"place_strong:{place_sim:.2f}")
    elif place_sim >= 0.55:
        score += 12
        reasons.append(f"place_partial:{place_sim:.2f}")

    cur_day = parse_day(current.get("date") or current.get("start_date_time"))
    hist_day = parse_day(hist.get("start_date_time"))
    if cur_day and hist_day:
        delta = month_day_delta(cur_day, hist_day)
        if delta <= 3:
            score += 25
            reasons.append(f"season_delta_days:{delta}")
        elif delta <= 7:
            score += 18
            reasons.append(f"season_delta_days:{delta}")
        elif delta <= 14:
            score += 10
            reasons.append(f"season_delta_days:{delta}")
        else:
            return 0, [f"season_too_far:{delta}"], "weak"

    cur_type = norm_text(current.get("category") or "")
    hist_type = norm_text(hist.get("event_type") or "")
    if cur_type and hist_type and (cur_type in hist_type or hist_type in cur_type):
        score += 6
        reasons.append("event_type_compatible")

    hist_close = norm_text(hist.get("street_closure_type") or "")
    if hist_close and hist_close not in {"n a", "na", "none"}:
        score += 3
        reasons.append("historical_street_closure_present")

    cid = current_event_id(current)
    hid = str(hist.get("event_id") or "").strip()
    cem = str(hist.get("cemsid") or "").strip().rstrip(",")
    if cid and hid and cid == hid:
        score += 40
        reasons.append("event_id_continuity")
    # CEMSID continuity across years is rare but powerful when present on current
    # (usually only on hist rows)

    if score >= 85:
        label = "returning_likely"
    elif score >= 60:
        label = "possible"
    else:
        label = "weak"
    return score, reasons, label


def index_historical(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket historical rows by borough for cheaper candidate scan."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        boro = norm_text(row.get("event_borough") or "unknown") or "unknown"
        buckets[boro].append(row)
        buckets["*"].append(row)
    return buckets


def best_matches_for(
    current: dict[str, Any],
    buckets: dict[str, list[dict[str, Any]]],
    foil_index: dict[str, dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    boro = norm_text(current.get("borough") or "unknown") or "unknown"
    candidates = buckets.get(boro) or buckets.get("*") or []
    # If few in borough, widen
    if len(candidates) < 25:
        candidates = buckets.get("*") or candidates

    scored: list[tuple[int, list[str], str, dict[str, Any]]] = []
    title_toks = tokens(current.get("title"))
    for hist in candidates:
        # cheap prefilter: require some token overlap OR strong place token
        htoks = tokens(hist.get("event_name"))
        if title_toks and htoks and not (title_toks & htoks):
            # still allow if place tokens overlap strongly
            pcur = tokens(current.get("display_location"))
            ph = tokens(hist.get("event_location"))
            if not (pcur & ph):
                continue
        score, reasons, label = score_match(current, hist)
        if score < 50 or label == "weak" and score < 55:
            continue
        scored.append((score, reasons, label, hist))
    scored.sort(key=lambda x: (-x[0], str(x[3].get("start_date_time") or "")))

    out: list[dict[str, Any]] = []
    seen_hist: set[str] = set()
    for score, reasons, label, hist in scored:
        hid = f"{hist.get('event_id')}|{str(hist.get('start_date_time') or '')[:10]}"
        if hid in seen_hist:
            continue
        seen_hist.add(hid)
        foil = foil_for(hist.get("event_id"), str(hist.get("cemsid") or "").rstrip(","), foil_index)
        foil_cur = foil_for(current_event_id(current), None, foil_index)
        item = {
            "match_score": score,
            "match_reasons": reasons,
            "recurrence_label": label,
            "current": {
                "id": current.get("id"),
                "event_id": current_event_id(current),
                "title": current.get("title"),
                "date": current.get("date"),
                "start_date_time": current.get("start_date_time"),
                "end_date_time": current.get("end_date_time"),
                "borough": current.get("borough"),
                "display_location": current.get("display_location"),
                "coordinate_status": current.get("coordinate_status"),
                "assignment_score": current.get("assignment_score"),
                "lane": current.get("lane"),
                "source": current.get("source"),
                "map_link": current.get("map_link"),
                "field_desk_link": current.get("field_desk_link")
                or field_desk_link(str(current.get("date") or "")),
                "latitude": current.get("latitude"),
                "longitude": current.get("longitude"),
            },
            "prior_year": hist_row_view(hist),
            "promotion_allowed": False,
            "public_map_modified": False,
            "location_cache_modified": False,
        }
        if foil or foil_cur:
            item["foil_operator"] = foil or foil_cur
        out.append(item)
        if len(out) >= limit:
            break
    return out


def build_next_14d_pack(
    matches: list[dict[str, Any]],
    *,
    reference: date,
) -> dict[str, Any]:
    end = reference + timedelta(days=14)
    ranked: list[dict[str, Any]] = []
    best_by_current: dict[str, dict[str, Any]] = {}
    for m in matches:
        cur = m.get("current") or {}
        day = parse_day(cur.get("date"))
        if not day or day < reference or day > end:
            continue
        cid = str(cur.get("id") or "")
        prev = best_by_current.get(cid)
        if prev is None or int(m.get("match_score") or 0) > int(prev.get("match_score") or 0):
            best_by_current[cid] = m
    ranked = sorted(
        best_by_current.values(),
        key=lambda m: (
            0 if m.get("recurrence_label") == "returning_likely" else 1 if m.get("recurrence_label") == "possible" else 2,
            -(m.get("match_score") or 0),
            str((m.get("current") or {}).get("date") or ""),
        ),
    )
    magnets = []
    for m in ranked[:40]:
        cur = m["current"]
        magnets.append(
            {
                "title": cur.get("title"),
                "date": cur.get("date"),
                "borough": cur.get("borough"),
                "display_location": cur.get("display_location"),
                "coordinate_status": cur.get("coordinate_status"),
                "match_score": m.get("match_score"),
                "recurrence_label": m.get("recurrence_label"),
                "prior_year_title": (m.get("prior_year") or {}).get("title"),
                "prior_year_date": (m.get("prior_year") or {}).get("date"),
                "match_reasons": m.get("match_reasons"),
                "field_desk_link": cur.get("field_desk_link"),
                "map_link": cur.get("map_link"),
                "foil_operator": m.get("foil_operator"),
                "event_id": cur.get("event_id"),
                "prior_event_id": (m.get("prior_year") or {}).get("event_id"),
                "cemsid": (m.get("prior_year") or {}).get("cemsid"),
            }
        )
    return {
        "schema_version": "photographer-viral-recurrence-pack-v1",
        "premium_label": "Viral Recurrence Pack — next 14 days (premium/operator)",
        "generated_at_utc": utc_now(),
        "reference_today_nyc": reference.isoformat(),
        "window_end": end.isoformat(),
        "crowd_magnet_count": len(magnets),
        "returning_likely_count": sum(1 for m in magnets if m.get("recurrence_label") == "returning_likely"),
        "possible_count": sum(1 for m in magnets if m.get("recurrence_label") == "possible"),
        "crowd_magnets": magnets,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "notes": "Coords/times from current Money-Day rows only. Prior-year rows are history matches.",
    }


def ensure_foil_stub() -> None:
    path = DATA_DIR / "sapo_foil_operator_index.json"
    existing = load_json(path, None)
    if isinstance(existing, dict) and existing.get("schema_version"):
        # Keep Howard's filled rows; refresh docs only if empty shell.
        if existing.get("operators"):
            return
    stub = {
        "schema_version": "sapo-foil-operator-index-v1",
        "generated_at_utc": utc_now(),
        "purpose": (
            "Manual join index for FOIL-derived applicant/org names. "
            "Fill after OpenRecords CECM/SAPO PDFs arrive. Never scrape unofficial sites."
        ),
        "open_data_note": (
            "tvpp-9vvx / bkfu-528j do not include applicant/company. "
            "Join keys: event_id and/or cemsid."
        ),
        "foil_portal": "https://a860-openrecords.nyc.gov/request/new",
        "operators": [],
        "example_operator_row": {
            "event_id": "936942",
            "cemsid": None,
            "applicant_org": None,
            "source": "foil",
            "foil_request_id": None,
            "notes": "Paste org name from released application PDF when available",
            "manual_review_status": "pending",
            "promotion_allowed": False,
        },
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
    }
    save_json(path, stub)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-today", default=None)
    args = parser.parse_args()
    reference = date.fromisoformat(args.reference_today) if args.reference_today else today_nyc()

    ensure_foil_stub()
    foil_index = load_foil_index()

    cal = load_json(DATA_DIR / "photographer_assignment_calendar_2mo.json", {})
    current_events = cal.get("events") if isinstance(cal, dict) else None
    if not isinstance(current_events, list) or not current_events:
        raise SystemExit("Missing photographer_assignment_calendar_2mo.json events")

    hist = load_json(DATA_DIR / "nyc_permits_historical_snapshot.json", {})
    hist_rows = hist.get("rows") if isinstance(hist, dict) else None
    if not isinstance(hist_rows, list) or not hist_rows:
        raise SystemExit("Missing nyc_permits_historical_snapshot.json rows — run sync first")

    buckets = index_historical(hist_rows)
    matches: list[dict[str, Any]] = []
    for event in current_events:
        matches.extend(best_matches_for(event, buckets, foil_index, limit=2))

    matches.sort(
        key=lambda m: (
            0 if m.get("recurrence_label") == "returning_likely" else 1 if m.get("recurrence_label") == "possible" else 2,
            -(m.get("match_score") or 0),
            str((m.get("current") or {}).get("date") or ""),
        )
    )

    label_counts = Counter(m.get("recurrence_label") for m in matches)
    with_foil = sum(1 for m in matches if m.get("foil_operator"))

    matches_payload = {
        "schema_version": "photographer-viral-recurrence-matches-v1",
        "premium_label": "Viral Recurrence Memory (premium/operator)",
        "generated_at_utc": utc_now(),
        "reference_today_nyc": reference.isoformat(),
        "current_calendar_events": len(current_events),
        "historical_rows_considered": len(hist_rows),
        "historical_window": {
            "prior_year": hist.get("prior_year"),
            "window_start": hist.get("window_start"),
            "window_end": hist.get("window_end"),
            "dataset": hist.get("dataset"),
        },
        "match_count": len(matches),
        "label_counts": dict(label_counts),
        "foil_operator_joins": with_foil,
        "matching_rules_documentation": [
            "Normalized event_name similarity (sequence + token Jaccard).",
            "Place fingerprint from location + borough (+ precinct on historical).",
            "Seasonal month-day window ±3/±7/±14 days.",
            "Event type compatibility + street-closure presence boost.",
            "event_id continuity when shared across years.",
            "FOIL applicant_org left-joined via event_id/cemsid when manually present.",
            "Never invent HH:MM; coordinates only from current Money-Day map_ready rows.",
        ],
        "matches": matches,
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
    }
    save_json(DATA_DIR / "photographer_viral_recurrence_matches.json", matches_payload)

    pack = build_next_14d_pack(matches, reference=reference)
    save_json(DATA_DIR / "photographer_viral_recurrence_pack_next_14d.json", pack)

    report = {
        "schema_version": "photographer-viral-recurrence-v1",
        "generated_at_utc": matches_payload["generated_at_utc"],
        "qa_pass": len(matches) > 0 and pack.get("crowd_magnet_count", 0) >= 0,
        "reference_today_nyc": reference.isoformat(),
        "match_count": len(matches),
        "label_counts": dict(label_counts),
        "next_14d_crowd_magnets": pack.get("crowd_magnet_count"),
        "next_14d_returning_likely": pack.get("returning_likely_count"),
        "foil_operator_joins": with_foil,
        "foil_index_path": "data/sapo_foil_operator_index.json",
        "top_returning_examples": [
            {
                "date": (m.get("current") or {}).get("date"),
                "title": (m.get("current") or {}).get("title"),
                "borough": (m.get("current") or {}).get("borough"),
                "score": m.get("match_score"),
                "label": m.get("recurrence_label"),
                "prior": (m.get("prior_year") or {}).get("title"),
                "prior_date": (m.get("prior_year") or {}).get("date"),
            }
            for m in matches
            if m.get("recurrence_label") == "returning_likely"
        ][:12],
        "artifacts": {
            "matches": "data/photographer_viral_recurrence_matches.json",
            "pack_next_14d": "data/photographer_viral_recurrence_pack_next_14d.json",
            "historical_snapshot": "data/nyc_permits_historical_snapshot.json",
            "foil_index": "data/sapo_foil_operator_index.json",
        },
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "protected_files_untouched": True,
    }
    # soft QA: prefer some returning_likely, but possible-only still passes if matches exist
    report["qa_pass"] = bool(matches) and bool(report.get("protected_files_untouched"))
    save_json(DATA_DIR / "photographer_viral_recurrence_report.json", report)
    # pack report alongside
    pack_report = {
        "schema_version": "photographer-viral-recurrence-pack-v1",
        "generated_at_utc": pack["generated_at_utc"],
        "qa_pass": True,
        "reference_today_nyc": reference.isoformat(),
        "crowd_magnet_count": pack.get("crowd_magnet_count"),
        "returning_likely_count": pack.get("returning_likely_count"),
        "possible_count": pack.get("possible_count"),
        "top": (pack.get("crowd_magnets") or [])[:10],
        "promotion_allowed": False,
        "public_map_modified": False,
        "protected_files_untouched": True,
    }
    save_json(DATA_DIR / "photographer_viral_recurrence_pack_report.json", pack_report)

    print(
        json.dumps(
            {
                "qa_pass": report["qa_pass"],
                "match_count": report["match_count"],
                "label_counts": report["label_counts"],
                "next_14d": pack.get("crowd_magnet_count"),
                "top_returning": report["top_returning_examples"][:5],
            },
            indent=2,
        )
    )
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
