from datetime import date

from nyc_event_atlas.adapters.clearview import parse_clearview_html
from nyc_event_atlas.adapters.common import guess_borough, parse_mdy
from nyc_event_atlas.adapters.nyc_street_fairs import parse_schedule_text
from nyc_event_atlas.adapters.public_calendar import map_calendar_row
from nyc_event_atlas.dedupe import occurrence_key


def test_parse_mdy():
    assert parse_mdy("07/18/2026 Bleecker Fair") == "2026-07-18"


def test_guess_borough_astoria():
    assert guess_borough("30th Ave Astoria", "30th Avenue") == "Queens"


def test_clearview_parser_extracts_rows():
    html = """
    <table>
      <tr><td>Saturday, July 18</td><td></td>
          <td>07/18/2026 Bleecker Pompei Fair ALMOST SOLD OUT</td>
          <td>Bleecker Street</td><td>7th Avenue - 6th Avenue</td>
          <td>Download Event Application Form</td></tr>
      <tr><td>Sunday, July 26</td><td></td>
          <td>07/26/2026 30th Ave Astoria</td>
          <td>30th Avenue</td><td>Steinway - 31st Street</td>
          <td>Download</td></tr>
    </table>
    """
    rows = parse_clearview_html(
        html,
        window_start=date(2026, 7, 16),
        window_end=date(2026, 12, 31),
        verified_on="2026-07-16",
    )
    assert len(rows) == 2
    assert rows[0]["START_DATE"] == "2026-07-18"
    assert rows[0]["BOROUGH"] == "Manhattan"
    assert rows[1]["BOROUGH"] == "Queens"
    assert rows[0]["LATITUDE"] == "Unknown"
    assert occurrence_key(rows[0])


def test_clearview_jammed_cell_fallback():
    html = """
    <html><body><table><tr><td>
    Saturday, July 18 07/18/2026 Bleecker Pompei Fair ALMOST SOLD OUT Bleecker Street
    7th Avenue - 6th Avenue Download Event Application Form
    Sunday, July 26 07/26/2026 30th Ave Astoria 30th Avenue Steinway - 31st Street
    Download Event Application Form
    </td></tr></table></body></html>
    """
    rows = parse_clearview_html(
        html,
        window_start=date(2026, 7, 16),
        window_end=date(2026, 12, 31),
        verified_on="2026-07-16",
    )
    assert len(rows) >= 2
    dates = {r["START_DATE"] for r in rows}
    assert "2026-07-18" in dates
    assert "2026-07-26" in dates


def test_public_calendar_maps_snapshot_shape():
    row = {
        "title": "Astoria Harvest Festival",
        "start_date_time": "2026-09-20T12:00:00",
        "end_date_time": "2026-09-20T18:00:00",
        "boroughs": ["Qn"],
        "address": "Astoria Park",
        "permalink": "https://www.nyc.gov/events/example",
        "agency_name": "NYC Parks",
        "categories": ["Festivals"],
        "canceled": False,
        "source_event_id": "abc123",
    }
    mapped = map_calendar_row(
        row,
        window_start=date(2026, 7, 16),
        window_end=date(2026, 12, 31),
        verified_on="2026-07-16",
    )
    assert mapped is not None
    assert mapped["START_DATE"] == "2026-09-20"
    assert mapped["BOROUGH"] == "Queens"
    assert mapped["LATITUDE"] == "Unknown"


def test_public_calendar_skips_lap_swim():
    row = {
        "title": "Astoria Pool: Lap Swim",
        "start_date_time": "2026-07-20T11:00:00",
        "boroughs": ["Qn"],
        "address": "Astoria Pool",
        "canceled": False,
    }
    assert (
        map_calendar_row(
            row,
            window_start=date(2026, 7, 16),
            window_end=date(2026, 12, 31),
            verified_on="2026-07-16",
        )
        is None
    )


def test_street_fairs_ordinal_dates():
    text = """
    JULY 18ᵗʰ    Bleecker Street Fair    Bleecker Street
    AUG. 1st     Jamaica Jams Festival   Jamaica Avenue
    09/07/2026   30th Ave Astoria Labor Day   30th Avenue
    """
    rows = parse_schedule_text(
        text,
        window_start=date(2026, 7, 16),
        window_end=date(2026, 12, 31),
        source_url="https://example.test/schedule.pdf",
        verified_on="2026-07-16",
        default_year=2026,
    )
    dates = {r["START_DATE"] for r in rows}
    assert "2026-07-18" in dates
    assert "2026-08-01" in dates
    assert "2026-09-07" in dates
    assert all(r["LATITUDE"] == "Unknown" for r in rows)
