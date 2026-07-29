#!/usr/bin/env python3
"""Tests for the Culture business candidate geocoder (Enigma bridge).

No network: a fake geosearch is injected. Confidence gating is delegated to the
shared Enigma ``pick_best_result`` (>= 0.5), so we exercise it through the real
helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import geocode_culture_business_candidates as geo  # noqa: E402


CANDIDATE = {
    "candidate_id": "geo-1",
    "license_id": "2100021",
    "business_id": "biz-x",
    "business_name": "Sample Unmapped Grocery",
    "address": "1502 Nostrand Ave, Brooklyn, NY, 11226",
    "borough": "Brooklyn",
    "community_district": "BK17",
}


def _fake_geosearch(hits):
    return lambda query: hits


def test_confident_hit_becomes_pending_proposal_never_promoted():
    hits = [{"label": "1502 Nostrand Ave", "lat": 40.65, "lng": -73.95, "confidence": 0.9, "query": "q"}]
    [p] = geo.geocode_culture_candidates([CANDIDATE], _fake_geosearch(hits))
    assert p["geocoding_status"] == "proposed_needs_review"
    assert p["lat"] == 40.65 and p["lng"] == -73.95
    assert p["license_id"] == "2100021"
    # Staging discipline mirrored from Enigma.
    assert p["promotion_allowed"] is False
    assert p["approved"] is False
    assert p["manual_review_status"] == "pending"


def test_low_confidence_is_unresolved():
    hits = [{"label": "weak", "lat": 40.65, "lng": -73.95, "confidence": 0.2, "query": "q"}]
    [p] = geo.geocode_culture_candidates([CANDIDATE], _fake_geosearch(hits))
    assert p["geocoding_status"] == "unresolved_no_confident_match"
    assert "lat" not in p


def test_no_hits_is_unresolved():
    [p] = geo.geocode_culture_candidates([CANDIDATE], _fake_geosearch([]))
    assert p["geocoding_status"] == "unresolved_no_confident_match"


def test_query_appends_borough_when_missing():
    cand = {**CANDIDATE, "address": "1502 Nostrand Ave"}
    assert geo.build_query(cand).endswith("Brooklyn, NY")
