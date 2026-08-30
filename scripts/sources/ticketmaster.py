from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.sources.base import SourceObservation

API_BASE = "https://app.ticketmaster.com/discovery/v2/events.json"
DATASET = "ticketmaster-discovery-v2"
DEFAULT_TIMEZONE = "America/New_York"


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _address(venue: dict[str, Any]) -> str | None:
    address = venue.get("address") if isinstance(venue.get("address"), dict) else {}
    city = venue.get("city") if isinstance(venue.get("city"), dict) else {}
    state = venue.get("state") if isinstance(venue.get("state"), dict) else {}
    parts = [
        _text(address.get("line1")),
        _text(city.get("name")),
        _text(state.get("stateCode") or state.get("name")),
        _text(venue.get("postalCode")),
    ]
    return ", ".join(part for part in parts if part) or None


def _start(event: dict[str, Any]) -> tuple[str, str]:
    dates = event.get("dates") if isinstance(event.get("dates"), dict) else {}
    start = dates.get("start") if isinstance(dates.get("start"), dict) else {}
    date_time = _text(start.get("dateTime"))
    timezone = _text(dates.get("timezone")) or DEFAULT_TIMEZONE
    if date_time:
        return date_time, timezone
    local_date = _text(start.get("localDate"))
    local_time = _text(start.get("localTime")) or "00:00:00"
    if not local_date:
        raise ValueError("Ticketmaster event is missing a usable start date")
    return f"{local_date}T{local_time}", timezone


def normalize_event(event: dict[str, Any]) -> SourceObservation:
    event_id = _text(event.get("id"))
    title = _text(event.get("name"))
    if not event_id or not title:
        raise ValueError("Ticketmaster event requires id and name")

    start_date_time, timezone = _start(event)
    embedded = event.get("_embedded") if isinstance(event.get("_embedded"), dict) else {}
    venues = embedded.get("venues") if isinstance(embedded.get("venues"), list) else []
    venue = venues[0] if venues and isinstance(venues[0], dict) else {}
    location = venue.get("location") if isinstance(venue.get("location"), dict) else {}

    venue_name = _text(venue.get("name"))
    address = _address(venue)
    city = venue.get("city") if isinstance(venue.get("city"), dict) else {}
    state = venue.get("state") if isinstance(venue.get("state"), dict) else {}
    display_location = venue_name or address

    end_date_time = None
    dates = event.get("dates") if isinstance(event.get("dates"), dict) else {}
    end = dates.get("end") if isinstance(dates.get("end"), dict) else {}
    if end:
        end_date_time = _text(end.get("dateTime"))

    return SourceObservation(
        source_dataset=DATASET,
        source_event_id=event_id,
        source_url=_text(event.get("url")),
        title=title,
        start_date_time=start_date_time,
        end_date_time=end_date_time,
        timezone=timezone,
        venue_name=venue_name,
        venue_id=_text(venue.get("id")),
        event_location=display_location,
        address=address,
        borough=None,
        latitude=_float(location.get("latitude")),
        longitude=_float(location.get("longitude")),
        series_id=None,
        raw_record=event,
    )


class TicketmasterAdapter:
    """Minimal Discovery API v2 fetcher that emits SourceObservation rows only."""

    def __init__(self, api_key: str, *, city: str = "New York", state_code: str = "NY", page_size: int = 200):
        if not api_key.strip():
            raise ValueError("Ticketmaster API key is required for network fetches")
        self.api_key = api_key.strip()
        self.city = city
        self.state_code = state_code
        self.page_size = max(1, min(200, int(page_size)))

    def build_url(self, page: int) -> str:
        params = {
            "apikey": self.api_key,
            "city": self.city,
            "stateCode": self.state_code,
            "size": self.page_size,
            "page": max(0, int(page)),
            "sort": "date,asc",
        }
        return f"{API_BASE}?{urlencode(params)}"

    def fetch_page(self, page: int) -> dict[str, Any]:
        request = Request(self.build_url(page), headers={"Accept": "application/json", "User-Agent": "NYC-In-Focus-events/1.0"})
        with urlopen(request, timeout=30) as response:  # nosec B310 - fixed HTTPS Ticketmaster endpoint
            return json.load(response)

    def iter_observations(self, *, max_pages: int | None = None) -> Iterator[SourceObservation]:
        page = 0
        while max_pages is None or page < max_pages:
            payload = self.fetch_page(page)
            embedded = payload.get("_embedded") if isinstance(payload.get("_embedded"), dict) else {}
            events = embedded.get("events") if isinstance(embedded.get("events"), list) else []
            for event in events:
                if isinstance(event, dict):
                    yield normalize_event(event)
            page_meta = payload.get("page") if isinstance(payload.get("page"), dict) else {}
            total_pages = int(page_meta.get("totalPages") or 0)
            page += 1
            if not events or (total_pages and page >= total_pages):
                break


def normalize_events(events: Iterable[dict[str, Any]]) -> list[SourceObservation]:
    return [normalize_event(event) for event in events]
