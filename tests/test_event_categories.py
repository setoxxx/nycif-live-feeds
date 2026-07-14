"""Tests for event category classification in build_test_enriched_feed."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_test_enriched_feed import category


def test_fitness_category_yoga():
    assert category({"event_name": "Morning Yoga in the Park", "event_type": "Special Event"}) == "fitness"


def test_fitness_category_zumba():
    assert category({"event_name": "Zumba Fitness Class", "event_agency": "Parks Department"}) == "fitness"


def test_parks_without_fitness_tokens():
    assert category({"event_name": "Family Picnic Day", "event_type": "Park Event"}) == "parks"


def test_sports_still_classified():
    assert category({"event_name": "Youth Soccer League", "event_type": "Athletic"}) == "sports"
