#!/usr/bin/env python3
"""Build Discovery God View digest: newly pulled + review/rejected queues."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discovery_v02 import utc_now, write_json  # noqa: E402


def _load(rel: str) -> dict | list | None:
    path = ROOT / rel
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _items(payload: dict | list | None, key: str = "items") -> list:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        val = payload.get(key)
        if isinstance(val, list):
            return val
        for alt in ("groups", "events", "records", "added_events", "removed_events"):
            alt_val = payload.get(alt)
            if isinstance(alt_val, list):
                return alt_val
    return []


def _slim_queue_row(row: dict) -> dict:
    src = row.get("source_identity") if isinstance(row.get("source_identity"), dict) else {}
    return {
        "canonical_id": row.get("canonical_id") or row.get("id"),
        "title": row.get("title") or row.get("name"),
        "date": row.get("date"),
        "location": row.get("location"),
        "borough": row.get("borough"),
        "current_classification": row.get("current_classification") or row.get("category"),
        "reason_for_review": row.get("reason_for_review") or row.get("reason") or row.get("quarantine_reason"),
        "recommended_action": row.get("recommended_action"),
        "source_dataset": src.get("dataset") or row.get("source_dataset"),
        "source_event_id": src.get("source_event_id") or row.get("source_event_id"),
    }


def _pattern_bucket(title: str) -> str:
    t = (title or "").lower()
    if "learn to swim" in t or "parent and tots" in t or "swim team" in t:
        return "swim_lessons"
    if "circuit training" in t or "midtown fit" in t or "cardio dance" in t or "dance fusion" in t:
        return "fitness_class_unnamed"
    if "flea market" in t or "sidewalk sale" in t or "farm stand" in t or "outdoor market" in t:
        return "market_or_sale"
    if "walk" in t and ("end" in t or "awareness" in t or "lupus" in t or "epilepsy" in t or "ribbon" in t):
        return "charity_walk"
    if "summer on the hudson" in t or "movies under the stars" in t or "ballet" in t:
        return "arts_performance"
    if "book club" in t or "workshop" in t or "training" in t:
        return "education_or_workshop"
    if "general election" in t or "register to vote" in t:
        return "government_election"
    if "restaurant week" in t:
        return "services_or_citywide_campaign"
    if "garden" in t or "lanternfly" in t or "earthing" in t or "rain garden" in t:
        return "parks_garden_environment"
    return "needs_howard_label"


# Suggested classifications Howard can confirm/edit.
SUGGESTED_RULES = {
    "swim_lessons": {
        "category": "fitness",
        "interests": ["fitness", "family", "education"],
        "tags": ["swim", "learn-to-swim", "kids", "class"],
        "note": "NYC Parks learn-to-swim / parent-tots / swim team training",
    },
    "fitness_class_unnamed": {
        "category": "fitness",
        "interests": ["fitness", "education"],
        "tags": ["fitness-class", "circuit-training"],
        "note": "Named fitness series without Shape Up branding",
    },
    "market_or_sale": {
        "category": "market",
        "interests": ["market"],
        "tags": ["flea-market", "sidewalk-sale"],
        "note": "Flea markets / BID sidewalk sales / farm stands",
    },
    "charity_walk": {
        "category": "civic",
        "interests": ["civic", "fitness"],
        "tags": ["charity-walk", "fundraiser"],
        "note": "Awareness / charity walks — civic primary, fitness interest",
    },
    "arts_performance": {
        "category": "arts",
        "interests": ["arts", "parks"],
        "tags": ["performance", "outdoor"],
        "note": "Summer on the Hudson / outdoor movies / ballet programs",
    },
    "education_or_workshop": {
        "category": "education",
        "interests": ["education"],
        "tags": ["workshop", "class"],
        "note": "Workshops / book clubs / trainings — refine subject when known",
    },
    "government_election": {
        "category": "government",
        "interests": ["government"],
        "tags": ["election", "voting"],
        "note": "Board of Elections civic deadlines / election day",
    },
    "services_or_citywide_campaign": {
        "category": "services",
        "interests": ["services"],
        "tags": ["citywide-campaign"],
        "note": "Citywide campaigns with no single venue",
    },
    "parks_garden_environment": {
        "category": "parks",
        "interests": ["parks", "environment"],
        "tags": ["community-garden", "outdoors"],
        "note": "Garden programs / nature / environment activities",
    },
    "needs_howard_label": {
        "category": None,
        "interests": [],
        "tags": [],
        "note": "Howard: reply with category + interests for these titles",
    },
}


def main() -> int:
    inventory = _load("data/events_source_inventory_v02.json") or {}
    recon = _load("data/events_discovery_reconciliation_v02.json") or {}
    audit = _load("data/events_discovery_taxonomy_v02_audit.json") or {}
    delta = _load("data/live_delta_report.json") or {}
    disposition = _load("data/row_disposition_report.json") or {}
    disposition_events = _load("data/row_disposition_events.json") or {}

    low = _items(_load("data/events_discovery_low_confidence_v02.json"))
    missing = _items(_load("data/events_discovery_missing_coordinates_v02.json"))
    invalid = _items(_load("data/events_discovery_invalid_records_v02.json"))
    legacy = _items(_load("data/events_discovery_legacy_major_quarantine_v02.json"))
    dupes = _items(_load("data/events_discovery_possible_duplicates_v02.json"), key="groups")

    disp_rows = _items(disposition_events, key="events")
    gps_review = [
        r
        for r in disp_rows
        if isinstance(r, dict) and str(r.get("disposition") or "") == "gps_review_queue"
    ]

    # Pattern assist for low-confidence titles
    pattern_counts: Counter[str] = Counter()
    assist_rows = []
    for row in low:
        if not isinstance(row, dict):
            continue
        bucket = _pattern_bucket(str(row.get("title") or ""))
        pattern_counts[bucket] += 1
        suggestion = SUGGESTED_RULES[bucket]
        assist_rows.append(
            {
                **_slim_queue_row(row),
                "pattern_bucket": bucket,
                "suggested_category": suggestion["category"],
                "suggested_interests": suggestion["interests"],
                "suggested_tags": suggestion["tags"],
                "suggestion_note": suggestion["note"],
                "howard_status": "confirm_or_override",
            }
        )

    needs_label = [r for r in assist_rows if r["pattern_bucket"] == "needs_howard_label"]

    added = _items(delta, key="added_events")
    removed = _items(delta, key="removed_events")

    digest = {
        "generated_at_utc": utc_now(),
        "classification_version": "discovery-taxonomy-v02",
        "purpose": "Press/operator God View digest: newly pulled vs review/rejected queues. Read-only.",
        "public_map_policy": "These queues are operator-visible and are not automatic public-map publishes.",
        "pipeline_snapshot": {
            "raw_intake_source_rows": inventory.get("raw_intake_source_row_total"),
            "accepted_canonical_records": recon.get("accepted_canonical_records"),
            "invalid_rejected_source_records": recon.get("invalid_rejected_source_records"),
            "reconciles": recon.get("reconciles"),
            "disposition_counts_phase1": disposition.get("disposition_counts"),
            "phase1_unclassified_rows": disposition.get("unclassified_rows"),
        },
        "daily_delta": {
            "generated_at_utc": delta.get("generated_at_utc"),
            "previous_snapshot_generated_at_utc": delta.get("previous_snapshot_generated_at_utc"),
            "added_count": delta.get("added_count") or len(added),
            "removed_count": delta.get("removed_count") or len(removed),
            "changed_count": delta.get("changed_count") or 0,
            "added_sample": [
                {
                    "title": e.get("title") or e.get("event_name"),
                    "date": e.get("date") or str(e.get("start_date_time") or "")[:10],
                    "borough": e.get("borough") or e.get("event_borough"),
                    "location": e.get("location") or e.get("display_location"),
                    "source_event_id": e.get("source_event_id") or e.get("event_id"),
                }
                for e in added[:50]
                if isinstance(e, dict)
            ],
            "removed_sample": [
                {
                    "title": e.get("title") or e.get("event_name"),
                    "date": e.get("date") or str(e.get("start_date_time") or "")[:10],
                    "borough": e.get("borough") or e.get("event_borough"),
                    "source_event_id": e.get("source_event_id") or e.get("event_id"),
                }
                for e in removed[:50]
                if isinstance(e, dict)
            ],
        },
        "queue_totals": {
            "hard_invalid_rejected": len(invalid),
            "low_confidence_general_fallback": len(low),
            "missing_or_invalid_coordinates_list_only": len(missing),
            "possible_duplicate_groups": len(dupes),
            "legacy_major_quarantined": len(legacy),
            "phase1_gps_review_queue": len(gps_review),
        },
        "howard_assist": {
            "instruction": (
                "Reply with confirmed category/interests per pattern_bucket, or per title for needs_howard_label. "
                "Confirmed rules will become permanent overrides for daily pulls."
            ),
            "pattern_counts": dict(pattern_counts),
            "suggested_rules": SUGGESTED_RULES,
            "needs_howard_label_count": len(needs_label),
            "needs_howard_label_titles": sorted(
                {str(r.get("title") or "") for r in needs_label if r.get("title")}
            ),
            "low_confidence_rows": assist_rows,
        },
        "review_queues_preview": {
            "low_confidence_sample": [_slim_queue_row(r) for r in low[:40] if isinstance(r, dict)],
            "missing_coordinates_sample": [_slim_queue_row(r) for r in missing[:40] if isinstance(r, dict)],
            "invalid_rejected_sample": [_slim_queue_row(r) for r in invalid[:40] if isinstance(r, dict)],
            "legacy_major_quarantine_sample": [
                _slim_queue_row(r) for r in legacy[:40] if isinstance(r, dict)
            ],
            "gps_review_sample": [
                {
                    "title": r.get("title") or r.get("event_name"),
                    "date": r.get("date") or r.get("event_date"),
                    "borough": r.get("borough") or r.get("event_borough"),
                    "location": r.get("location") or r.get("event_location"),
                    "reason": r.get("reason") or r.get("disposition_reason"),
                    "source_event_id": r.get("source_event_id") or r.get("event_id"),
                }
                for r in gps_review[:40]
                if isinstance(r, dict)
            ],
        },
        "category_interest_snapshot": {
            "primary_category_counts": audit.get("primary_category_counts"),
            "interest_counts": audit.get("interest_counts"),
            "kids_family_interest_count": audit.get("kids_family_interest_count"),
            "classes_workshops_interest_count": audit.get("classes_workshops_interest_count"),
            "volunteer_category_count": audit.get("volunteer_category_count"),
            "tours_category_count": audit.get("tours_category_count"),
        },
        "artifact_links": {
            "low_confidence": "data/events_discovery_low_confidence_v02.json",
            "missing_coordinates": "data/events_discovery_missing_coordinates_v02.json",
            "invalid_records": "data/events_discovery_invalid_records_v02.json",
            "possible_duplicates": "data/events_discovery_possible_duplicates_v02.json",
            "legacy_major_quarantine": "data/events_discovery_legacy_major_quarantine_v02.json",
            "reconciliation": "data/events_discovery_reconciliation_v02.json",
            "live_delta": "data/live_delta_report.json",
            "howard_assist_sheet": "data/howard_classification_assist_v02.json",
        },
    }

    assist_sheet = {
        "generated_at_utc": digest["generated_at_utc"],
        "instruction": digest["howard_assist"]["instruction"],
        "suggested_rules": SUGGESTED_RULES,
        "pattern_counts": dict(pattern_counts),
        "needs_howard_label_titles": digest["howard_assist"]["needs_howard_label_titles"],
        "rows": assist_rows,
    }

    write_json("data/events_discovery_godview_digest_v02.json", digest)
    write_json("data/howard_classification_assist_v02.json", assist_sheet)
    print(
        json.dumps(
            {
                "godview_digest": "data/events_discovery_godview_digest_v02.json",
                "assist_sheet": "data/howard_classification_assist_v02.json",
                "queue_totals": digest["queue_totals"],
                "needs_howard_label": len(needs_label),
                "delta_added": digest["daily_delta"]["added_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
