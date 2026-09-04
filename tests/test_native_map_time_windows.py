from datetime import date

from scripts import official_event_contract as contract
from scripts import native_map_time_windows as windows


def test_next_seven_days_starts_tomorrow_friday_to_saturday_through_friday():
    today = date(2026, 9, 4)  # Friday
    days = windows.next_seven_days(today)
    assert [row["date"] for row in days] == [
        "2026-09-05",
        "2026-09-06",
        "2026-09-07",
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
    ]
    assert [row["weekday_short"] for row in days] == [
        "Sat",
        "Sun",
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
    ]
    assert days[0]["label"] == "Saturday Sep 5"
    assert today.isoformat() not in {row["date"] for row in days}


def test_tonight_keeps_only_events_starting_at_or_after_6pm():
    today = date(2026, 9, 4)
    assert windows.overlaps_tonight("2026-09-04T18:00:00-04:00", None, today) is True
    assert windows.overlaps_tonight("2026-09-04T17:59:00-04:00", "2026-09-04T23:00:00-04:00", today) is False
    assert windows.overlaps_tonight("2026-09-04T10:00:00-04:00", "2026-09-04T11:00:00-04:00", today) is False
    assert windows.overlaps_tonight("2026-09-05T20:00:00-04:00", None, today) is False


def test_seven_window_excludes_today_and_keeps_matching_day():
    today = date(2026, 9, 4)
    assert windows.overlaps_seven("2026-09-04T20:00:00-04:00", None, today) is False
    assert windows.overlaps_seven("2026-09-05T10:00:00-04:00", None, today) is True
    assert windows.overlaps_seven("2026-09-11T22:00:00-04:00", None, today) is True
    assert windows.overlaps_seven("2026-09-12T10:00:00-04:00", None, today) is False
    assert windows.overlaps_calendar_day("2026-09-07T09:00:00-04:00", None, date(2026, 9, 7)) is True
    assert windows.parse_day_param("2026-09-07", today) == date(2026, 9, 7)
    assert windows.parse_day_param("2026-09-04", today) is None
    assert windows.normalize_mode("7D") == "seven"


def test_native_map_hides_borough_only_citywide_and_multi_site():
    assert contract.native_map_row_visible("Manhattan", "Manhattan", "tvpp-9vvx") is False
    assert contract.native_map_row_visible("NYC Public Beaches Citywide", "Citywide", contract.DATASET_CALENDAR) is False
    assert (
        contract.native_map_row_visible(
            "Meadow Lake North (in Flushing Meadows Corona Park),Sand Lane,Marine Park,Bensonhurst Park",
            None,
            contract.DATASET_PARKS,
        )
        is False
    )
    assert (
        contract.native_map_row_visible(
            "WEST 97 STREET between COLUMBUS AVENUE and AMSTERDAM AVENUE",
            "Manhattan",
            contract.DATASET_CALENDAR,
        )
        is True
    )


def test_night_aux_layers_stay_locked():
    assert [layer["id"] for layer in windows.NIGHT_AUX_LAYERS] == ["5pm", "dispensary", "liquor"]
    assert windows.NIGHT_AUX_LAYERS[0]["label"] == "It's 5 PM Somewhere"
