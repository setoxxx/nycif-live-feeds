from __future__ import annotations

from scripts.run_review_locations_from_lion import (
    canonical_node_id,
    canonical_street_key,
    normalized_node_street_index,
    official_street_variants,
)


def test_node_id_padding_is_normalized():
    assert canonical_node_id("0047448") == "47448"
    assert canonical_node_id(47448) == "47448"


def test_official_street_aliases_share_canonical_keys():
    assert canonical_street_key("AV OF THE AMERICAS") == "6 AVE"
    assert canonical_street_key("AVE OF THE AMERICAS") == "6 AVE"
    assert canonical_street_key("AV OF AMERICAS") == "6 AVE"
    assert canonical_street_key("AVE OF AMERICAS") == "6 AVE"
    assert canonical_street_key("AMERICAS AVE") == "6 AVE"
    assert canonical_street_key("6 Avenue") == "6 AVE"
    assert canonical_street_key("MAC DOUGAL ST") == "MACDOUGAL ST"
    assert canonical_street_key("MacDougal Street") == "MACDOUGAL ST"


def test_query_variants_include_lion_aliases():
    variants = official_street_variants("6 Avenue")
    assert "AV OF THE AMERICAS" in variants
    assert "AVE OF THE AMERICAS" in variants
    assert "AV OF AMERICAS" in variants
    assert "AVE OF AMERICAS" in variants
    assert "AMERICAS AVE" in variants
    assert "MAC DOUGAL ST" in official_street_variants("MacDougal Street")


def test_node_index_joins_padded_line_ids_to_integer_node_ids():
    rows = [
        {
            "Street": "W 48 ST",
            "SAFStreetName": None,
            "NodeIDFrom": "0021470",
            "NodeIDTo": "0021472",
        },
        {
            "Street": "AV OF AMERICAS",
            "SAFStreetName": None,
            "NodeIDFrom": "0021470",
            "NodeIDTo": "0021500",
        },
    ]
    index = normalized_node_street_index(rows)
    assert "21470" in index
    assert index["21470"] == {"W 48 ST", "6 AVE"}
