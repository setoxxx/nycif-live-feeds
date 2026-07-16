from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote_plus

from ..normalize import clean_text, empty_record, maps_url
from ..schema import VALID_BOROUGHS

BOROUGH_HINTS = [
    ("staten island", "Staten Island"),
    ("the bronx", "The Bronx"),
    ("bronx", "The Bronx"),
    ("brooklyn", "Brooklyn"),
    ("queens", "Queens"),
    ("manhattan", "Manhattan"),
    ("citywide", "Citywide"),
]


def guess_borough(*texts: str) -> str:
    blob = " ".join(clean_text(t).lower() for t in texts if t)
    for needle, label in BOROUGH_HINTS:
        if needle in blob:
            return label
    # Outer borough street-fair heuristics from producer schedules
    if any(x in blob for x in ("astoria", "forest hills", "jamaica", "woodside", "rego park", "steinway")):
        return "Queens"
    if any(x in blob for x in ("brighton", "williamsburg", "sunset park", "greenpoint", "smith street", "bedford")):
        return "Brooklyn"
    if any(x in blob for x in ("ronkonkoma", "islip", "long island", "hawkins ave")):
        return "NYC-adjacent"
    if any(x in blob for x in ("bleecker", "lexington", "columbus", "times sq", "chelsea", "washington sq")):
        return "Manhattan"
    return "Unknown"


def parse_mdy(value: str) -> str | None:
    value = clean_text(value)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if not m:
        return None
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_iso_date(value: Any) -> str:
    if value in (None, "", "Unknown", "TBA"):
        return "Unknown" if value != "TBA" else "TBA"
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    mdy = parse_mdy(text)
    return mdy or "Unknown"


def parse_clock(value: Any) -> str:
    text = clean_text(value)
    if text in ("", "Unknown"):
        return "Unknown"
    m = re.search(r"(\d{1,2}):(\d{2})\s*([ap]m)?", text, re.I)
    if not m:
        return "Unknown"
    hour = int(m.group(1))
    minute = int(m.group(2))
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def borough_from_coords(lat: str, lng: str) -> str:
    try:
        la = float(lat)
        lo = float(lng)
    except (TypeError, ValueError):
        return "Unknown"
    # Coarse borough boxes — only used when official Parks coordinates exist.
    if 40.70 <= la <= 40.88 and -74.05 <= lo <= -73.90:
        return "Manhattan"
    if 40.57 <= la <= 40.74 and -74.05 <= lo <= -73.83:
        return "Brooklyn"
    if 40.54 <= la <= 40.81 and -73.96 <= lo <= -73.70:
        return "Queens"
    if 40.79 <= la <= 40.92 and -73.93 <= lo <= -73.76:
        return "The Bronx"
    if 40.49 <= la <= 40.65 and -74.26 <= lo <= -74.05:
        return "Staten Island"
    return "Unknown"


def valid_nyc_pair(lat: Any, lng: Any) -> tuple[str, str]:
    try:
        la = float(lat)
        lo = float(lng)
    except (TypeError, ValueError):
        return "Unknown", "Unknown"
    if not (40.4 <= la <= 41.0 and -74.3 <= lo <= -73.6):
        return "Unknown", "Unknown"
    return f"{la:.6f}", f"{lo:.6f}"


def base_record(
    *,
    name: str,
    start_date: str,
    end_date: str = "Unknown",
    start_time: str = "Unknown",
    end_time: str = "Unknown",
    borough: str = "Unknown",
    venue: str = "Unknown",
    street_from: str = "Unknown",
    street_to: str = "Unknown",
    organizer: str = "Unknown",
    category: str = "Community Festival",
    subcategory: str = "Unknown",
    status: str = "Announced",
    confidence: str = "High",
    primary_source: str,
    secondary_source: str = "Unknown",
    website: str = "Unknown",
    permit_id: str = "Unknown",
    notes: str = "Unknown",
    lat: str = "Unknown",
    lng: str = "Unknown",
    verified_on: str | None = None,
) -> dict:
    rec = empty_record()
    if borough not in VALID_BOROUGHS and borough != "Unknown":
        borough = guess_borough(borough, venue, name)
    if borough == "Unknown":
        borough = guess_borough(name, venue, notes)
    # If still unknown, leave as Unknown — review will reject_invalid unless TBA path.
    # For street fairs we usually resolve borough via heuristics; if not, mark Citywide only when explicit.
    lat_s, lng_s = valid_nyc_pair(lat, lng) if lat != "Unknown" else ("Unknown", "Unknown")
    location_query = venue if venue != "Unknown" else name
    rec.update(
        {
            "EVENT_NAME": clean_text(name),
            "EVENT_STATUS": status,
            "CATEGORY": category,
            "SUBCATEGORY": subcategory,
            "START_DATE": start_date,
            "END_DATE": end_date if end_date != "Unknown" else start_date,
            "START_TIME": start_time,
            "END_TIME": end_time,
            "BOROUGH": "Unknown",
            "VENUE": clean_text(venue),
            "FULL_ADDRESS": clean_text(venue),
            "STREET_NAME": clean_text(venue) if venue != "Unknown" else "Unknown",
            "STREET_FROM": clean_text(street_from),
            "STREET_TO": clean_text(street_to),
            "LATITUDE": lat_s,
            "LONGITUDE": lng_s,
            "GOOGLE_MAPS_URL": maps_url(location_query),
            "APPLE_MAPS_URL": maps_url(location_query, True),
            "ORGANIZER": clean_text(organizer),
            "OFFICIAL_WEBSITE": website if website != "Unknown" else primary_source,
            "PERMIT_ID": clean_text(permit_id),
            "PRIMARY_SOURCE": primary_source,
            "SECONDARY_SOURCE": secondary_source,
            "SOURCE_CONFIDENCE": confidence,
            "LAST_VERIFIED": verified_on or date.today().isoformat(),
            "RESEARCH_NOTES": clean_text(notes),
        }
    )
    if borough in VALID_BOROUGHS:
        rec["BOROUGH"] = borough
    else:
        guessed = guess_borough(name, venue, notes, organizer, borough)
        rec["BOROUGH"] = guessed if guessed in VALID_BOROUGHS else "Unknown"
    return rec
