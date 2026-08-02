"""Resolve an otherwise ambiguous DPR alias only when borough makes it unique."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from nycif.normalize.facility_lookup import canonical_borough, valid_nyc_point
from nycif.normalize.facility_resolver import evidence_tier, location_text
from nycif.normalize.park_geometry import extract_park_names, normalize_park_name

LOOKUP = Path(__file__).resolve().parents[3] / "data" / "park_ambiguous_candidates.json"

def resolve_borough_qualified_park(record: dict[str, Any], *, lookup_path: Path = LOOKUP):
    if evidence_tier(record) != "unresolved":
        return None
    borough = canonical_borough(record.get("borough") or record.get("event_borough"))
    if not borough:
        return None
    try:
        payload = json.loads(lookup_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    matched: dict[str, dict[str, Any]] = {}
    for candidate in extract_park_names(location_text(record)):
        values = (payload.get("aliases") or {}).get(normalize_park_name(candidate)) or []
        borough_values = [value for value in values if canonical_borough(value.get("borough")) == borough and valid_nyc_point(value.get("lat"), value.get("lng"))]
        for value in borough_values:
            matched[str(value.get("park_id"))] = value
    if len(matched) != 1:
        return None
    entry = next(iter(matched.values()))
    return {"latitude": entry["lat"], "longitude": entry["lng"], "coordinate_precision": "park_level_anchor", "coordinate_source": "dpr_parks_properties_centroid", "coordinate_status": "approximate", "display_disposition": "approximate_marker", "promotion_allowed": False, "production_feed": False, "public_map_modified": False, "park_id": entry.get("park_id"), "park_name": entry.get("park_name"), "park_borough": borough, "park_match_type": "borough_qualified_ambiguous_alias"}
