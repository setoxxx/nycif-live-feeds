"""Shared fail-closed exact-name resolver primitives."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from nycif.normalize.facility_lookup import canonical_borough, clean_text, load_lookup, normalize_name, valid_nyc_point
from nycif.normalize.facility_resolver import evidence_tier, location_text


def candidate_phrases(text: str, *, suffixes: Iterable[str], prefixes: Iterable[str] = ()) -> list[str]:
    value = clean_text(text)
    if not value:
        return []
    candidates = {value}
    for prefix in prefixes:
        candidates.add(re.sub(prefix, "", value, flags=re.IGNORECASE).strip(" -,:;()"))
    suffix_pattern = "|".join(suffixes)
    for match in re.finditer(rf"(?:^|\b(?:in|at|inside|outside|outdoors at|on)\s+)([^,;]+?\b(?:{suffix_pattern})\b)", value, re.IGNORECASE):
        candidates.add(match.group(1).strip(" -,:;()"))
    parts = [part.strip(" -,:;()") for part in re.split(r"\s+(?:in|at)\s+|,", value, flags=re.IGNORECASE)]
    candidates.update(part for part in parts if part)
    return sorted(candidates, key=lambda item: (-len(item), item.casefold()))


def resolve_exact(record: dict[str, Any], *, lookup_path: Path, candidates: Iterable[str], coordinate_source: str, accepted_types: set[str] | None = None) -> dict[str, Any] | None:
    if not isinstance(record, dict) or evidence_tier(record) != "unresolved":
        return None
    text = location_text(record)
    if not text:
        return None
    payload = load_lookup(lookup_path)
    aliases = payload.get("aliases") or {}
    ambiguous = set(payload.get("ambiguous_aliases") or [])
    borough = canonical_borough(record.get("borough") or record.get("event_borough"))
    matches: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = normalize_name(candidate)
        if not key or key in ambiguous:
            continue
        entry = aliases.get(key)
        if not isinstance(entry, dict):
            continue
        if accepted_types and str(entry.get("facility_type")) not in accepted_types:
            continue
        entry_borough = canonical_borough(entry.get("borough"))
        if not borough or not entry_borough or borough != entry_borough:
            continue
        if not valid_nyc_point(entry.get("lat"), entry.get("lng")):
            continue
        matched = dict(entry)
        matched["facility_query_name"] = candidate
        matched["facility_matched_alias"] = key
        matches[str(entry.get("authority_id"))] = matched
    if len(matches) != 1:
        return None
    entry = next(iter(matches.values()))
    return {
        "latitude": entry["lat"],
        "longitude": entry["lng"],
        "coordinate_precision": "certified_facility",
        "coordinate_source": coordinate_source,
        "coordinate_status": "approximate",
        "display_disposition": "approximate_marker",
        "promotion_allowed": False,
        "production_feed": False,
        "public_map_modified": False,
        "facility_name": entry.get("facility_name"),
        "facility_type": entry.get("facility_type"),
        "authority_id": entry.get("authority_id"),
        "facility_borough": canonical_borough(entry.get("borough")),
        "facility_match_type": "unique_normalized_name_and_borough",
        "facility_query_name": entry.get("facility_query_name"),
        "facility_matched_alias": entry.get("facility_matched_alias"),
    }
