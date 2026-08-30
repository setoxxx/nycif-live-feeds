from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """Raw-but-normalized observation emitted by any external event adapter.

    SourceObservation is not a canonical event and is never a public-feed row.
    It must pass through OccurrenceIdentityV2, reconciliation, location QA, and
    publication gates before it can become canonical/public data.
    """

    source_dataset: str
    source_event_id: str
    source_url: str | None
    title: str
    start_date_time: str
    end_date_time: str | None
    timezone: str
    venue_name: str | None = None
    venue_id: str | None = None
    event_location: str | None = None
    address: str | None = None
    borough: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    series_id: str | None = None
    raw_record: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
