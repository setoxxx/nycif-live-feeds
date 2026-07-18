#!/usr/bin/env python3
"""Dedupe approved discovery events after supplemental fold/merge."""

from __future__ import annotations

import math
import re
from typing import Any

COORD_EPSILON_M = 80.0


def _norm_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _event_day(event: dict[str, Any]) -> str:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    return str(nycif.get("event_date") or event.get("start_date_time") or "")[:10]


def _has_coords(event: dict[str, Any]) -> bool:
    lat = event.get("latitude")
    lng = event.get("longitude")
    if lat is None or lng is None:
        return False
    try:
        float(lat)
        float(lng)
    except (TypeError, ValueError):
        return False
    return True


def _coord_distance_m(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    if not _has_coords(a) or not _has_coords(b):
        return None
    lat1 = math.radians(float(a["latitude"]))
    lng1 = math.radians(float(a["longitude"]))
    lat2 = math.radians(float(b["latitude"]))
    lng2 = math.radians(float(b["longitude"]))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000.0 * 2 * math.asin(min(1.0, math.sqrt(h)))


def _event_priority(event: dict[str, Any]) -> int:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    score = 0
    if nycif.get("coordinate_status") == "map_ready" and _has_coords(event):
        score += 200
    if str(nycif.get("manual_review_status") or "").lower() == "approved":
        score += 120
    if nycif.get("data_layer") == "approved_staged" and not str(event.get("id") or "").startswith(
        "review_supplemental:"
    ):
        score += 80
    if nycif.get("supplemental_merge_authorized"):
        score += 60
    if nycif.get("public_supplemental"):
        score += 10
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    if str(source.get("dataset") or "").startswith("nyc-open-data"):
        score += 40
    return score


def supplemental_fold_eligible(event: dict[str, Any]) -> bool:
    """Only fold human-approved or map-ready official supplemental rows into approved."""
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    status = str(nycif.get("manual_review_status") or "").lower()
    if status in {"pending", "rejected"}:
        return False
    if status == "approved":
        return True
    return nycif.get("coordinate_status") == "map_ready" and _has_coords(event)


def _duplicate_group_key(event: dict[str, Any]) -> tuple[str, ...] | None:
    title = _norm_text(event.get("title"))
    day = _event_day(event)
    if not title or not day:
        return None
    if _has_coords(event):
        return (
            "coord",
            title,
            day,
            f"{float(event['latitude']):.4f}",
            f"{float(event['longitude']):.4f}",
        )
    location = _norm_text(event.get("location") or event.get("address"))
    if location:
        return ("loc", title, day, location)
    return None


def _is_supplemental_related(event: dict[str, Any]) -> bool:
    nycif = event.get("nycif") if isinstance(event.get("nycif"), dict) else {}
    eid = str(event.get("id") or "")
    if eid.startswith("review_supplemental:"):
        return True
    if nycif.get("public_supplemental"):
        return True
    if nycif.get("supplemental_merge_authorized"):
        return True
    if nycif.get("supplemental_from"):
        return True
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    dataset = str(source.get("dataset") or "").lower()
    return dataset in {
        "nyc-citywide-events-calendar-api",
        "nyc-parks-bigapps-events",
        "nyc_parks_bigapps_events_snapshot",
    }


def _supplemental_bucket(event: dict[str, Any]) -> tuple[str, str] | None:
    title = _norm_text(event.get("title"))
    day = _event_day(event)
    if not title or not day:
        return None
    return (title, day)


def _locations_compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    dist = _coord_distance_m(a, b)
    if dist is not None and dist <= COORD_EPSILON_M:
        return True
    loc_a = _norm_text(a.get("location") or a.get("address"))
    loc_b = _norm_text(b.get("location") or b.get("address"))
    if loc_a and loc_b and (loc_a == loc_b or loc_a in loc_b or loc_b in loc_a):
        return True
    nycif_a = a.get("nycif") if isinstance(a.get("nycif"), dict) else {}
    nycif_b = b.get("nycif") if isinstance(b.get("nycif"), dict) else {}
    statuses = {nycif_a.get("coordinate_status"), nycif_b.get("coordinate_status")}
    if statuses == {"list_only", "map_ready"}:
        return True
    return False


def dedupe_approved_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Drop weaker cross-source supplemental duplicates while preserving permit rows."""
    kept: list[dict[str, Any]] = []
    buckets: dict[tuple[str, str], list[int]] = {}
    removed: list[dict[str, Any]] = []

    for event in events:
        if not _is_supplemental_related(event):
            kept.append(event)
            continue

        bucket = _supplemental_bucket(event)
        if bucket is None:
            kept.append(event)
            continue

        candidate_indexes = buckets.get(bucket, [])
        replace_idx = None
        for idx in candidate_indexes:
            current = kept[idx]
            if not _is_supplemental_related(current):
                continue
            if not _locations_compatible(current, event):
                continue
            replace_idx = idx
            break

        if replace_idx is None:
            buckets.setdefault(bucket, []).append(len(kept))
            kept.append(event)
            continue

        current = kept[replace_idx]
        if _event_priority(event) > _event_priority(current):
            removed.append(
                {
                    "dropped_id": current.get("id"),
                    "kept_id": event.get("id"),
                    "title": event.get("title"),
                    "date": bucket[1],
                    "reason": "lower_priority_supplemental_duplicate",
                }
            )
            kept[replace_idx] = event
        else:
            removed.append(
                {
                    "dropped_id": event.get("id"),
                    "kept_id": current.get("id"),
                    "title": event.get("title"),
                    "date": bucket[1],
                    "reason": "lower_priority_supplemental_duplicate",
                }
            )

    stats = {
        "input_count": len(events),
        "output_count": len(kept),
        "removed_duplicate_count": len(removed),
        "sample_removed": removed[:25],
    }
    return kept, stats
