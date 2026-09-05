"""Parse NYC block-face location strings into corridor proposals.

Parse only. Does not geocode, write location_cache.json, or mark MAP_READY.
"""

from __future__ import annotations

import re
from typing import Any

BETWEEN_RE = re.compile(
    r"^(?P<main>.+?)\s+between\s+(?P<from>.+?)\s+and\s+(?P<to>.+?)$",
    re.IGNORECASE,
)

BOROUGH_RE = re.compile(
    r"^(?P<body>.+?)(?:,\s*)?(?P<borough>Manhattan|Brooklyn|Queens|Bronx|Staten Island)(?:\s*,?\s*NY)?$",
    re.IGNORECASE,
)

STREET_TOKEN_RE = re.compile(
    r"\b(street|st|avenue|ave|boulevard|blvd|road|rd|place|pl|drive|dr|"
    r"lane|ln|parkway|pkwy|plaza|highway|hwy|expressway|expy|turnpike|"
    r"terrace|ter|court|ct|way|walk)\b",
    re.IGNORECASE,
)


def _clean_street(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" ,")
    text = re.sub(r"\s+Manhattan$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+Brooklyn$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+Queens$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+Bronx$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+Staten Island$", "", text, flags=re.IGNORECASE)
    return text.strip(" ,")


def _looks_like_street(value: str) -> bool:
    text = value.strip()
    if len(text) < 2:
        return False
    if STREET_TOKEN_RE.search(text):
        return True
    if re.search(r"\bavenue\s+[a-z]$", text, re.IGNORECASE):
        return True
    return bool(re.match(r"^(east|west|north|south)\s+\d+", text, re.IGNORECASE))


def parse_street_corridor(
    display_location: str | None,
    borough: str | None = None,
) -> dict[str, Any] | None:
    """Return a corridor proposal or None if the string is not a block face."""
    raw = re.sub(r"\s+", " ", str(display_location or "")).strip(" ,")
    if not raw:
        return None

    found_borough = (borough or "").strip() or None
    body = raw
    match_b = BOROUGH_RE.match(raw)
    if match_b:
        body = match_b.group("body").strip(" ,")
        found_borough = match_b.group("borough").title()
        if found_borough == "Staten Island":
            found_borough = "Staten Island"

    match = BETWEEN_RE.match(body)
    if not match:
        return None

    main = _clean_street(match.group("main"))
    from_street = _clean_street(match.group("from"))
    to_street = _clean_street(match.group("to"))
    if not (_looks_like_street(main) and _looks_like_street(from_street) and _looks_like_street(to_street)):
        return None
    if from_street.lower() == to_street.lower():
        return None

    return {
        "geometry_type": "CORRIDOR",
        "main_street": main,
        "from_street": from_street,
        "to_street": to_street,
        "borough": found_borough,
        "point_a": None,
        "point_b": None,
        "line": None,
        "resolver": None,
        "reason_code": "SEGMENT_UNCERTIFIED",
        "map_eligibility_state": "LIST_ONLY",
        "query_a": f"{main} and {from_street}, {found_borough or 'New York'}, NY",
        "query_b": f"{main} and {to_street}, {found_borough or 'New York'}, NY",
    }


def corridor_reader_stub(parsed: dict[str, Any]) -> dict[str, Any]:
    """Reader blob after parse, before endpoint resolution."""
    return {
        "certified_pin": False,
        "map_eligibility_state": "LIST_ONLY",
        "display_disposition": "LIST_ONLY",
        "geometry_type": "CORRIDOR",
        "corridor": parsed,
    }
