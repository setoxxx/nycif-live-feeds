"""Holiday organizer monitors (tree lightings, menorahs, NYE, etc.)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from .community import fetch_community_sources

ROOT = Path(__file__).resolve().parents[3]
SEEDS = ROOT / "config" / "seeds" / "holiday_sources.yaml"


def fetch_holiday_sources(
    conn: sqlite3.Connection, *, window_start: date, window_end: date, **kwargs
) -> dict:
    return fetch_community_sources(
        conn,
        window_start=window_start,
        window_end=window_end,
        seeds_path=SEEDS,
        kinds={"holiday"},
    )
