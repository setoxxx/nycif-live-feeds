from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_review_location_coverage import (
    SpatialEntry,
    build_spatial_index,
    load_review_events,
    resolve_null_borough_event,
)
from scripts.nyc_location_gazetteer import NYCLocationGazetteer


def event(**overrides):
    payload = {
        "id": "review:test:1@2026-07-28",
        "title": "Test event",
        "borough": None,
        "location": "Test Place",
        "latitude": None,
        "longitude": None,
        "source": {"dataset": "test", "source_event_id": "1", "source