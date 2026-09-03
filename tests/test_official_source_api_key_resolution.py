"""Env-key resolution for official NYC source collectors. No live secrets."""

from __future__ import annotations

import os
from unittest.mock import patch

from scripts.sync_nyc_citywide_events_calendar import resolve_api_key
from scripts.sync_nyc_open_data import soda_request_headers


def test_calendar_key_prefers_nyc_event_cal_api_key() -> None:
    with patch.dict(
        os.environ,
        {
            "NYC_EVENT_CAL_API_KEY": "fixture-primary-subscription",
            "NYC_EVENT_CALENDAR_API_KEY": "fixture-alias-subscription",
        },
        clear=False,
    ):
        key, source = resolve_api_key()
    assert key == "fixture-primary-subscription"
    assert source == "environment:NYC_EVENT_CAL_API_KEY"


def test_calendar_key_accepts_pipeline_alias_when_primary_empty() -> None:
    with patch.dict(
        os.environ,
        {
            "NYC_EVENT_CAL_API_KEY": "",
            "NYC_EVENT_CALENDAR_API_KEY": "fixture-alias-subscription",
        },
        clear=False,
    ):
        key, source = resolve_api_key()
    assert key == "fixture-alias-subscription"
    assert source == "environment:NYC_EVENT_CALENDAR_API_KEY"


def test_empty_calendar_secrets_fall_back_to_public_config() -> None:
    with patch.dict(
        os.environ,
        {
            "NYC_EVENT_CAL_API_KEY": "",
            "NYC_EVENT_CALENDAR_API_KEY": "  ",
        },
        clear=False,
    ), patch(
        "scripts.sync_nyc_citywide_events_calendar.fetch_public_key",
        return_value="fixture-public-config-key",
    ) as mocked_public:
        key, source = resolve_api_key()
    assert key == "fixture-public-config-key"
    assert source.startswith("public_config:")
    mocked_public.assert_called()


def test_soda_headers_omit_app_token_when_unset() -> None:
    with patch.dict(
        os.environ,
        {"SOCRATA_APP_TOKEN": "", "NYC_SODA_APP_TOKEN": ""},
        clear=False,
    ):
        headers = soda_request_headers()
    assert "X-App-Token" not in headers


def test_soda_headers_prefer_socrata_then_nyc_alias() -> None:
    with patch.dict(
        os.environ,
        {
            "SOCRATA_APP_TOKEN": "fixture-socrata-token",
            "NYC_SODA_APP_TOKEN": "fixture-nyc-soda-token",
        },
        clear=False,
    ):
        headers = soda_request_headers()
    assert headers["X-App-Token"] == "fixture-socrata-token"

    with patch.dict(
        os.environ,
        {
            "SOCRATA_APP_TOKEN": "",
            "NYC_SODA_APP_TOKEN": "fixture-nyc-soda-token",
        },
        clear=False,
    ):
        headers = soda_request_headers()
    assert headers["X-App-Token"] == "fixture-nyc-soda-token"
