from scripts.tvpp_pin_resolver import (
    TvppPinResolver,
    build_facility_index,
    cache_key,
    lion_line_midpoint,
    segment_identity,
)


def test_facility_parent_name_pins():
    resolver = TvppPinResolver(
        {"augustus st gaudens playground": {"lat": 40.737, "lng": -73.981, "label": "Augustus St. Gaudens Playground"}},
        {},
        allow_live_geosearch=False,
    )
    pin = resolver.resolve("Augustus St. Gaudens Playground: Basketball-01", "Manhattan")
    assert pin.resolved is True
    assert pin.lat == 40.737
    assert pin.source == "nyc_parks_facility_reference"
    assert pin.exact_pin_eligible is True
    assert pin.evidence()["reason_code"] == "TVPP_PARKS_FACILITY_OFFICIAL"


def test_street_between_uses_geosearch_midpoint():
    calls = []

    def fake_geosearch(query: str):
        calls.append(query)
        if "union hall" in query.lower() and "jamaica" in query.lower():
            return {"lat": 40.7020, "lng": -73.7980, "label": "a"}
        if "union hall" in query.lower() and "archer" in query.lower():
            return {"lat": 40.7030, "lng": -73.7990, "label": "b"}
        return None

    resolver = TvppPinResolver(
        {},
        {},
        allow_live_geosearch=True,
        geosearch_fn=fake_geosearch,
    )
    pin = resolver.resolve("UNION HALL STREET between JAMAICA AVENUE and ARCHER AVENUE", "Queens")
    assert pin.resolved is True
    assert pin.source == "nyc_geosearch_segment_midpoint"
    assert round(pin.lat, 4) == 40.7025
    assert pin.exact_pin_eligible is True
    assert cache_key(
        "UNION HALL STREET between JAMAICA AVENUE and ARCHER AVENUE",
        "Queens",
    ) in resolver.cache


def test_lion_centerline_midpoint_pins_street_segment():
    lion_key = segment_identity(
        "Queens",
        "UNION HALL STREET",
        "JAMAICA AVENUE",
        "ARCHER AVENUE",
    )
    resolver = TvppPinResolver(
        {},
        {},
        allow_live_geosearch=False,
        lion_index={
            lion_key: {
                "lat": 40.7028,
                "lng": -73.7982,
                "label": "UNION HALL STREET between JAMAICA AVENUE and ARCHER AVENUE",
            }
        },
    )
    pin = resolver.resolve("UNION HALL STREET between JAMAICA AVENUE and ARCHER AVENUE", "Queens")
    assert pin.resolved is True
    assert pin.source == "nyc_dcp_lion_centerline"
    assert pin.reason_code == "TVPP_LION_CENTERLINE_MIDPOINT"
    assert pin.lat == 40.7028
    assert pin.exact_pin_eligible is True


def test_street_name_geosearch_fallback_when_intersections_miss():
    def fake_geosearch(query: str):
        if " and " in query.lower():
            return None
        if "union hall" in query.lower():
            return {"lat": 40.703791, "lng": -73.797881, "label": "9204 UNION HALL STREET"}
        return None

    resolver = TvppPinResolver(
        {},
        {},
        allow_live_geosearch=True,
        geosearch_fn=fake_geosearch,
    )
    pin = resolver.resolve("UNION HALL STREET between JAMAICA AVENUE and ARCHER AVENUE", "Queens")
    assert pin.resolved is True
    assert pin.source == "nyc_geosearch_planninglabs"
    assert pin.reason_code == "TVPP_NYC_GEOSEARCH_STREET"
    assert pin.lat == 40.703791


def test_queens_hyphen_address_preferred_over_bare_street():
    calls = []

    def fake_geosearch(query: str):
        calls.append(query)
        if " and " in query.lower():
            return None
        if "77-01" in query:
            return {"lat": 40.745715, "lng": -73.887749, "label": "77-15 41 AVENUE"}
        if "41st avenue" in query.lower() or query.lower().startswith("41 avenue"):
            return {"lat": 40.749788, "lng": -73.859939, "label": "104-41 41 AVENUE"}
        return None

    resolver = TvppPinResolver(
        {},
        {},
        allow_live_geosearch=True,
        geosearch_fn=fake_geosearch,
    )
    pin = resolver.resolve("41 AVENUE between 77 STREET and 78 STREET", "Queens")
    assert pin.resolved is True
    assert pin.lat == 40.745715
    assert any("77-01" in query for query in calls)


def test_lion_line_midpoint_uses_endpoints():
    lat, lng = lion_line_midpoint(
        {
            "type": "LineString",
            "coordinates": [[-73.80, 40.70], [-73.79, 40.71]],
        }
    )
    assert round(lat, 4) == 40.705
    assert round(lng, 4) == -73.795


def test_parent_place_reuses_sibling_cache_for_park_colon_locations():
    resolver = TvppPinResolver(
        {},
        {
            cache_key("Coney Island Beach & Boardwalk: West 21st St. Performance Area", "Brooklyn"): {
                "lat": 40.57328,
                "lng": -73.97033,
                "source": "nyc_geosearch_planninglabs",
                "confidence": "medium",
                "confidence_reason": "seed",
                "reason_code": "TVPP_NYC_GEOSEARCH_PLACE",
            }
        },
        allow_live_geosearch=False,
    )
    pin = resolver.resolve("Coney Island Beach & Boardwalk: Steeplechase Pier", "Brooklyn")
    assert pin.resolved is True
    assert pin.lat == 40.57328
    assert pin.reason_code == "TVPP_PARENT_PLACE_CACHE"


def test_unresolved_without_live_or_facility():
    resolver = TvppPinResolver({}, {}, allow_live_geosearch=False)
    pin = resolver.resolve("UNKNOWN ALLEY between NOWHERE and NOWHERE", "Brooklyn")
    assert pin.resolved is False
    assert pin.lat is None


def test_facility_index_reads_reference_shape():
    index = build_facility_index()
    assert index
    assert any("playground" in key for key in list(index)[:50])


def test_facility_cannot_pin_the_wrong_borough():
    from scripts.gps_identity import normalize_text_legacy

    display = "EAST 41 STREET between PARK AVENUE and LEXINGTON AVENUE"
    resolver = TvppPinResolver(
        {
            normalize_text_legacy(display): {
                "lat": 40.533,
                "lng": -74.2021,
                "label": "Wrong SI park",
            }
        },
        {},
        allow_live_geosearch=False,
    )
    pin = resolver.resolve(display, "Manhattan")
    assert pin.resolved is False
    assert pin.lat is None
