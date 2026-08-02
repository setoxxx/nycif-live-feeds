"""DCP Facilities is a verification-only cross-check, never a primary matcher."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from nycif.normalize.facility_lookup import canonical_borough, load_lookup, normalize_name, valid_nyc_point

LOOKUP = Path(__file__).resolve().parents[3] / "data" / "dcp_facility_centroids.json"

def cross_check_dcp_facility(record: dict[str, Any], proposed: dict[str, Any] | None, *, lookup_path: Path = LOOKUP) -> dict[str, Any] | None:
    if not proposed:
        return None
    payload = load_lookup(lookup_path)
    entry = (payload.get("aliases") or {}).get(normalize_name(proposed.get("facility_name")))
    if not isinstance(entry, dict):
        return proposed
    event_borough = canonical_borough(record.get("borough") or record.get("event_borough"))
    if event_borough != canonical_borough(entry.get("borough")):
        return None
    if not valid_nyc_point(entry.get("lat"), entry.get("lng")):
        return None
    checked = dict(proposed)
    checked["dcp_cross_check"] = True
    checked["dcp_authority_id"] = entry.get("authority_id")
    return checked

def resolve_dcp_facility(record: dict[str, Any], *, lookup_path: Path = LOOKUP):
    return None
