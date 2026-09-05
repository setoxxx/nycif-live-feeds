from scripts.street_corridor_parse import parse_street_corridor


def test_feast_block_face_brooklyn() -> None:
    parsed = parse_street_corridor(
        "18 AVENUE between 73 STREET and 75 STREET, Brooklyn, NY",
        borough="Brooklyn",
    )
    assert parsed is not None
    assert parsed["main_street"].upper() == "18 AVENUE"
    assert parsed["from_street"].upper() == "73 STREET"
    assert parsed["to_street"].upper() == "75 STREET"
    assert parsed["borough"] == "Brooklyn"
    assert parsed["map_eligibility_state"] == "LIST_ONLY"
    assert parsed["point_a"] is None


def test_greenmarket_west_23() -> None:
    parsed = parse_street_corridor(
        "WEST 23 STREET between 8 AVENUE and 9 AVENUE  Manhattan"
    )
    assert parsed is not None
    assert parsed["borough"] == "Manhattan"
    assert "23" in parsed["main_street"]


def test_location_evidence_regression_east_74_brooklyn() -> None:
    parsed = parse_street_corridor(
        "East 74 Street between Avenue U and Avenue T",
        borough="Brooklyn",
    )
    assert parsed is not None
    assert parsed["borough"] == "Brooklyn"
    assert parsed["from_street"].lower().startswith("avenue u")
    assert parsed["to_street"].lower().startswith("avenue t")


def test_borough_only_is_not_a_corridor() -> None:
    assert parse_street_corridor("Manhattan") is None


def test_and_without_between_is_not_a_corridor() -> None:
    assert parse_street_corridor("Park Avenue and 42 Street, Manhattan") is None
