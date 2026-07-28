from __future__ import annotations

from scripts.run_review_location_resolution_audit import (
    labels_semantically_agree,
    normalized_semantic_tokens,
)


def test_st_james_abbreviation_matches_saint_james_label():
    assert labels_semantically_agree(
        "Multi-Use Room in St. James Recreation Center, Bronx, NY",
        "SAINT JAMES PARK RECREATION CTR, Bronx, NY, USA",
    )


def test_little_bay_does_not_match_fairview_parking_lot():
    assert not labels_semantically_agree(
        "Little Bay Park - Parking lot, lot under the bridge.",
        "FAIRVIEW PARK PARKING LOT, Staten Island, NY, USA",
    )


def test_borough_name_alone_cannot_create_a_match():
    assert not labels_semantically_agree(
        "Unknown facility, Queens, NY",
        "Unrelated building, Queens, NY, USA",
    )


def test_ordinal_street_number_normalizes_for_address_match():
    assert "125" in normalized_semantic_tokens("East 125th Street, Manhattan")
    assert labels_semantically_agree(
        "East 125th Street, Manhattan, NY",
        "125 E 125 STREET, New York, NY, USA",
    )
