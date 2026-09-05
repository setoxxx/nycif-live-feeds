from scripts.street_corridor_resolve import resolve_corridor

# 18 Ave & 73 St / 18 Ave & 75 St, Brooklyn Bensonhurst
FEAST_A = (40.6149, -73.9941)
FEAST_B = (40.6138, -73.9952)


def lookup_feast(query: str, borough: str | None):
    text = query.lower()
    if "73" in text:
        return FEAST_A
    if "75" in text:
        return FEAST_B
    return None


def test_feast_block_becomes_corridor_ready() -> None:
    result = resolve_corridor(
        "18 AVENUE between 73 STREET and 75 STREET, Brooklyn, NY",
        "Brooklyn",
        lookup_feast,
    )
    assert result["ok"] is True
    assert result["map_eligibility_state"] == "CORRIDOR_READY"
    assert result["certified_pin"] is False
    assert result["map_ready"] is False
    assert result["lat"] is None and result["lng"] is None
    line = result["corridor"]["line"]
    assert line[0] == [FEAST_A[1], FEAST_A[0]] or line[0][1] == FEAST_A[0]


def test_missing_endpoint_stays_list_only() -> None:
    result = resolve_corridor(
        "18 AVENUE between 73 STREET and 75 STREET, Brooklyn",
        "Brooklyn",
        lambda query, borough: FEAST_A if "73" in query else None,
    )
    assert result["ok"] is False
    assert result["map_eligibility_state"] == "LIST_ONLY"
    assert result["reason_code"] == "SEGMENT_ENDPOINT_UNRESOLVED"


def test_not_a_block_face_stays_list_only() -> None:
    result = resolve_corridor("Manhattan", "Manhattan", lookup_feast)
    assert result["ok"] is False
    assert result["reason_code"] == "NOT_STREET_BETWEEN_CLAIM"


def test_too_far_apart_stays_list_only() -> None:
    def lookup(query: str, borough: str | None):
        if "73" in query:
            return (40.62, -74.00)
        return (40.75, -73.98)  # ~9 miles

    result = resolve_corridor(
        "18 AVENUE between 73 STREET and 75 STREET, Brooklyn",
        "Brooklyn",
        lookup,
    )
    assert result["ok"] is False
    assert result["reason_code"] == "SEGMENT_DISTANCE_OUT_OF_RANGE"
