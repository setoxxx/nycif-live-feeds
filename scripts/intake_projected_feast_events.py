#!/usr/bin/env python3
"""Geocode operator-curated projected feast/fair rows for discovery map intake.

These are real recurring NYC events that may not yet appear in the committed SAPO
raw snapshot. Outputs a staging artifact only — does not edit protected feeds.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import utc_now  # noqa: E402

SEED_PATH = ROOT / "data" / "staging" / "nyc_feast_festival_reference_seed.json"
REFERENCE_PATH = ROOT / "data" / "nyc_sapo_feast_festival_reference.json"
INTAKE_PATH = ROOT / "data" / "staging" / "projected_feast_events_map_intake.json"
REPORT_PATH = ROOT / "data" / "reports" / "projected_feast_events_map_intake_report.json"
DATASET = "nyc-projected-feast-reference"

EVENT_TYPE_BY_KIND = {
    "religious_feast": "Street Festival",
    "street_fair": "Street Festival",
    "food_festival": "Street Festival",
    "cultural_festival": "Street Festival",
    "holiday_market": "Street Festival",
    "parade": "Parade",
}


def norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def borough_label(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    mapping = {
        "manhattan": "Manhattan",
        "mn": "Manhattan",
        "brooklyn": "Brooklyn",
        "bk": "Brooklyn",
        "queens": "Queens",
        "qn": "Queens",
        "bronx": "Bronx",
        "bx": "Bronx",
        "staten island": "Staten Island",
        "si": "Staten Island",
    }
    return mapping.get(text.lower(), text)


def display_location_for(seed: dict[str, Any]) -> str:
    direct = str(seed.get("display_location") or "").strip()
    if direct:
        return direct
    hint = str(seed.get("location_hint") or "").strip()
    borough = borough_label(seed.get("borough")) or ""
    if hint and borough:
        return f"{hint}, {borough}, NY"
    return hint


def load_confirmed_raw_keys(reference_path: Path) -> set[tuple[str, str]]:
    if not reference_path.exists():
        return set()
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, dict) else []
    keys: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("match_status") != "confirmed_permit_id":
            continue
        raw = entry.get("raw_match") if isinstance(entry.get("raw_match"), dict) else {}
        dataset = str(raw.get("source_dataset") or "").strip()
        source_event_id = str(raw.get("source_event_id") or "").strip()
        if dataset and source_event_id:
            keys.add((dataset, source_event_id))
    return keys


def geocode_row(row: dict[str, Any], *, allow_live_geosearch: bool) -> dict[str, Any] | None:
    from coverage_gap_utils import resolve_supplemental_coordinates
    from nyc_location_gazetteer import GAZETTEER_PATH, GEOSEARCH_CACHE_PATH, NYCLocationGazetteer
    from nyc_location_resolver import NYCLocationResolver

    ref_lat = row.get("reference_lat")
    ref_lng = row.get("reference_lng")
    if ref_lat is not None and ref_lng is not None:
        return {
            "proposed_lat": float(ref_lat),
            "proposed_lng": float(ref_lng),
            "geocoder_source": "operator_reference_pin",
            "geocoder_confidence": "medium",
            "confidence_reason": "Operator reference coordinate for recurring feast corridor.",
            "fill_method": "operator_reference_pin",
        }

    if not GAZETTEER_PATH.exists():
        return None
    gazetteer = NYCLocationGazetteer.from_file(GAZETTEER_PATH)
    cache_payload = json.loads(GEOSEARCH_CACHE_PATH.read_text(encoding="utf-8"))
    entries = cache_payload.get("entries") if isinstance(cache_payload, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    resolver = NYCLocationResolver(gazetteer, entries, allow_live_geosearch=allow_live_geosearch)
    fill = resolve_supplemental_coordinates(
        {
            "title": row.get("title"),
            "display_location": row.get("display_location"),
            "address": row.get("display_location"),
            "borough": row.get("borough"),
        },
        gazetteer,
        parks_overlap={},
        resolver=resolver,
        geoclient=None,
        parks_properties_index={},
    )
    if fill and allow_live_geosearch and len(resolver.geosearch_cache) > len(entries):
        GEOSEARCH_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        GEOSEARCH_CACHE_PATH.write_text(
            json.dumps(
                {
                    "version": cache_payload.get("version", 1),
                    "generated_at_utc": utc_now(),
                    "entries": resolver.geosearch_cache,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return fill


def seed_to_intake_row(seed: dict[str, Any]) -> dict[str, Any]:
    title = str(seed.get("canonical_name") or "").strip()
    start = str(seed.get("projected_start") or "").strip()
    end = str(seed.get("projected_end") or start).strip()
    borough = borough_label(seed.get("borough"))
    event_kind = str(seed.get("event_kind") or "street_fair")
    return {
        "title": title,
        "event_name": title,
        "event_type": EVENT_TYPE_BY_KIND.get(event_kind, "Street Festival"),
        "start_date_time": f"{start}T12:00:00",
        "end_date_time": f"{end}T22:00:00",
        "date": start,
        "borough": borough,
        "event_borough": borough,
        "display_location": display_location_for(seed),
        "location": display_location_for(seed),
        "source_dataset": DATASET,
        "source_event_id": str(seed.get("key") or norm_text(title)).strip(),
        "intake_type": "projected_feast_reference",
        "reference_lat": seed.get("reference_lat"),
        "reference_lng": seed.get("reference_lng"),
        "projected_feast_key": seed.get("key"),
        "projected_event_kind": event_kind,
        "map_emoji": seed.get("map_emoji"),
        "promotion_allowed": False,
        "public_map_modified": False,
        "location_cache_modified": False,
        "staged_feed_modified": False,
        "confidence_reason": (
            "Operator-curated recurring feast/fair schedule for map intake until SAPO permit lands in raw data."
        ),
    }


def load_skip_seed_keys(reference_path: Path) -> set[str]:
    if not reference_path.exists():
        return set()
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, dict) else []
    skip: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("match_status") == "confirmed_permit_id":
            skip.add(str(entry.get("key") or ""))
    return skip


def build_intake(*, allow_live_geosearch: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    seed_payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    seed_rows = seed_payload.get("entries") if isinstance(seed_payload, dict) else seed_payload
    if not isinstance(seed_rows, list):
        raise SystemExit("Seed file must contain entries array.")

    confirmed_raw_keys = load_confirmed_raw_keys(REFERENCE_PATH)
    skip_seed_keys = load_skip_seed_keys(REFERENCE_PATH)
    intake_rows: list[dict[str, Any]] = []
    skipped_confirmed = 0
    map_ready = 0
    list_only = 0
    samples: list[dict[str, Any]] = []

    for seed in seed_rows:
        if not isinstance(seed, dict):
            continue
        if str(seed.get("key") or "") in skip_seed_keys:
            skipped_confirmed += 1
            continue
        row = seed_to_intake_row(seed)
        fill = geocode_row(row, allow_live_geosearch=allow_live_geosearch)
        if fill:
            row["latitude"] = fill.get("proposed_lat")
            row["longitude"] = fill.get("proposed_lng")
            row["lat"] = fill.get("proposed_lat")
            row["lng"] = fill.get("proposed_lng")
            row["proposed_lat"] = fill.get("proposed_lat")
            row["proposed_lng"] = fill.get("proposed_lng")
            row["geocoder_source"] = fill.get("geocoder_source")
            row["geocoder_confidence"] = fill.get("geocoder_confidence")
            row["confidence_reason"] = fill.get("confidence_reason") or row["confidence_reason"]
            map_ready += 1
        else:
            list_only += 1
        intake_rows.append(row)
        if len(samples) < 12 and fill:
            samples.append(
                {
                    "key": seed.get("key"),
                    "title": row.get("title"),
                    "start": row.get("date"),
                    "end": str(row.get("end_date_time") or "")[:10],
                    "latitude": row.get("latitude"),
                    "longitude": row.get("longitude"),
                }
            )

    report = {
        "artifact_type": "projected_feast_events_map_intake_report",
        "generated_at_utc": utc_now(),
        "qa_pass": map_ready > 0,
        "seed_count": len(seed_rows),
        "skipped_already_confirmed_in_raw": skipped_confirmed,
        "intake_count": len(intake_rows),
        "map_ready_count": map_ready,
        "list_only_count": list_only,
        "allow_live_geosearch": allow_live_geosearch,
        "confirmed_raw_keys_ignored": sorted(confirmed_raw_keys),
        "samples": samples,
        "notes": [
            "Projected feast rows are real recurring events staged for map visibility before SAPO raw intake.",
            "Rows without coordinates remain in intake for list visibility and later geocoding.",
        ],
    }
    return intake_rows, report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build projected feast map intake staging artifact.")
    parser.add_argument(
        "--allow-live-geosearch",
        action="store_true",
        help="Allow live NYC GeoSearch lookups and cache writes.",
    )
    args = parser.parse_args()
    allow_live = args.allow_live_geosearch or os.environ.get("NYCIF_ALLOW_LIVE_GEOSEARCH", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    intake_rows, report = build_intake(allow_live_geosearch=allow_live)
    INTAKE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    INTAKE_PATH.write_text(
        json.dumps({"events": intake_rows, "generated_at_utc": utc_now()}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
