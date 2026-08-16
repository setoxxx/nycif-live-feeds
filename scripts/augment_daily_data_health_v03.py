#!/usr/bin/env python3
"""Attach live-source, semantic pin, and News Desk V3 telemetry to daily health.

This is intentionally a post-processor around the existing daily health builder so
all current health rules remain authoritative while the V3 migration adds the
fields needed to prove source freshness, semantic location authority, and reader-
safe News Desk status.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def repository_path(*parts: str) -> Path:
    """Return an allowlisted repository path after resolving symlinks."""
    repository_root = ROOT.resolve()
    candidate = repository_root.joinpath(*parts).resolve(strict=False)
    try:
        candidate.relative_to(repository_root)
    except ValueError as exc:
        raise ValueError(f"artifact path must stay within {repository_root}") from exc
    return candidate


HEALTH = repository_path("status", "nycif-daily-data-health.json")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("events", "items", "features"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_hours(value: Any, now: datetime) -> float | None:
    parsed = parse_utc(value)
    if parsed is None:
        return None
    return round(max(0.0, (now - parsed).total_seconds() / 3600.0), 3)


def source_status(report: dict[str, Any], *, count: int, now: datetime) -> dict[str, Any]:
    generated = report.get("generated_at_utc")
    return {
        "count": int(count),
        "generated_at_utc": generated,
        "age_hours": age_hours(generated, now),
        "fetch_mode": report.get("fetch_mode", "live" if report.get("qa_pass") is not False else "unknown"),
        "qa_pass": bool(report.get("qa_pass", count > 0)),
        "non_empty": count > 0,
    }


def availability_gate(addendum: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "canonical_inventory_non_empty": int(addendum.get("canonical_event_count") or 0) > 0,
        "map_ready_non_empty": int(addendum.get("map_ready_count") or 0) > 0,
        "reader_safe_non_empty": int(addendum.get("reader_safe_event_count") or 0) > 0,
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "qa_pass": not failures,
        "checks": checks,
        "failures": failures,
        "operating_rule": (
            "A public-map release must contain canonical events, at least one "
            "certified MAP_READY marker, and at least one reader-safe event."
        ),
    }


def build_addendum(root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    permitted_report = load(root / "data" / "live_sync_report.json")
    permitted_rows = rows(load(root / "data" / "raw_nyc_open_data_snapshot.json"))
    calendar_report = load(root / "data" / "nyc_citywide_events_calendar_sync_report.json")
    calendar_rows = rows(load(root / "data" / "nyc_citywide_events_calendar_snapshot.json"))
    parks_report = load(root / "data" / "nyc_parks_bigapps_events_sync_report.json")
    parks_rows = rows(load(root / "data" / "nyc_parks_bigapps_events_snapshot.json"))
    staged_manifest = load(root / "data" / "staged_live_manifest.json")
    canonical_rows = rows(load(root / "data" / "events_discovery_accepted_canonical_v02.json"))
    v3 = load(root / "data" / "events_discovery_v3_authority_report.json")
    news = load(root / "data" / "reader-safe" / "news-desk-status-v02.json")
    map_status = load(root / "data" / "reader-safe" / "national-map-events-v03-status.json")

    map_states = {"MAP_READY": 0, "GENERAL_AREA": 0, "REVIEW_REQUIRED": 0, "LIST_ONLY": 0}
    semantic_rows = 0
    for event in canonical_rows:
        nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
        state = str(nycif.get("map_eligibility_state") or "REVIEW_REQUIRED")
        if state not in map_states:
            state = "REVIEW_REQUIRED"
        map_states[state] += 1
        if nycif.get("location_authority") == "projector_v3_semantic_map_decision":
            semantic_rows += 1

    review_count = map_states["GENERAL_AREA"] + map_states["REVIEW_REQUIRED"] + map_states["LIST_ONLY"]
    permits = source_status(permitted_report, count=len(permitted_rows), now=now)
    calendar = source_status(calendar_report, count=len(calendar_rows), now=now)
    parks = source_status(parks_report, count=len(parks_rows), now=now)

    zero_gates = {
        "silent_identity_loss": int(v3.get("silent_identity_loss") or 0),
        "duplicate_exact_occurrences": int(v3.get("duplicate_exact_occurrences") or 0),
        "unsupported_exact_pin_count": int(v3.get("unsupported_exact_pin_count") or 0),
        "implicit_source_all_count": int(v3.get("implicit_source_all_count") or 0),
        "legacy_occurrence_authority_count": int(v3.get("legacy_occurrence_authority_count") or 0),
        "legacy_coordinate_authority_count": int(v3.get("legacy_coordinate_authority_count") or 0),
    }

    addendum = {
        "generated_at_utc": now.isoformat(),
        "authority": "projector_v3_semantic_map_decision",
        "sources": {
            "permitted_events": permits,
            "citywide_calendar": calendar,
            "parks_bigapps": parks,
        },
        "semantic_staged_count": int(staged_manifest.get("staged_feed_events") or 0),
        "canonical_event_count": len(canonical_rows),
        "semantic_authority_row_count": semantic_rows,
        "map_state_counts": map_states,
        "map_ready_count": map_states["MAP_READY"],
        "reader_safe_event_count": int(map_status.get("reader_safe_event_count") or 0),
        "review_count": review_count,
        "zero_gates": zero_gates,
        "news_desk": {
            "money_count": int(news.get("money_emitted_rows") or 0),
            "viral_count": int(news.get("viral_emitted_rows") or 0),
            "unsupported_exact_pin_count": int(news.get("unsupported_exact_pin_count") or 0),
            "browser_raw_repository_required": bool(news.get("browser_raw_repository_required", True)),
            "generated_at_utc": news.get("generated_at_utc"),
            "age_hours": age_hours(news.get("generated_at_utc"), now),
        },
        "projector_v3_qa_pass": bool(v3.get("qa_pass")),
        "raw_accounting_pass": bool(v3.get("raw_accounting_pass")),
        "all_sources_live_non_empty": all(
            item["non_empty"] and item["qa_pass"] and item["fetch_mode"] == "live"
            for item in (permits, calendar, parks)
        ),
        "zero_gate_pass": all(value == 0 for value in zero_gates.values()),
    }
    addendum["availability"] = availability_gate(addendum)
    return addendum


def main() -> int:
    health = load(HEALTH)
    if not isinstance(health, dict):
        raise RuntimeError("daily health payload must be an object")
    addendum = build_addendum()
    health["v3_runtime"] = addendum
    availability = addendum["availability"]
    pipeline = health.setdefault("pipeline", {})
    pipeline["map_available"] = bool(availability["qa_pass"])
    if not availability["qa_pass"]:
        health["status"] = "BLOCKED"
        health["release_ready"] = False
        health.setdefault("blockers", []).append(
            {
                "code": "public_map_unavailable",
                "severity": "critical",
                "message": (
                    "Public-map availability failed: "
                    + ", ".join(availability["failures"])
                ),
                "artifact": "data/reader-safe/national-map-events-v03-status.json",
            }
        )
    HEALTH.write_text(json.dumps(health, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(addendum, indent=2, sort_keys=True))

    if not addendum["projector_v3_qa_pass"]:
        raise RuntimeError("Projector V3 QA is not PASS")
    if not addendum["raw_accounting_pass"]:
        raise RuntimeError("Projector V3 raw accounting is not PASS")
    if not addendum["all_sources_live_non_empty"]:
        raise RuntimeError("one or more official live source families is not live/non-empty/QA PASS")
    if not addendum["zero_gate_pass"]:
        raise RuntimeError(f"V3 zero gate failed: {addendum['zero_gates']}")
    if not addendum["availability"]["qa_pass"]:
        raise RuntimeError(
            "public-map availability gate failed: "
            + ", ".join(addendum["availability"]["failures"])
        )
    if addendum["news_desk"]["browser_raw_repository_required"]:
        raise RuntimeError("News Desk reader-safe status still requires raw repository data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
