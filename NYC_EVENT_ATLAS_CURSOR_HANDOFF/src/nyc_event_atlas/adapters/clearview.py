"""Clearview Festival Productions street-fair schedule adapter."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from ..http_client import AtlasHttpClient
from ..normalize import clean_text
from ..review_ingest import ensure_source, queue_normalized_candidates, save_snapshot
from .common import base_record, guess_borough, parse_mdy

SOURCE_ID = "clearview"
URL = "https://vendors.clearviewfestival.com/StreetFairsSchedule.aspx"
ROOT = Path(__file__).resolve().parents[3]

ROW_DATE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4})\s+(.+)$")

# Jammed ASP.NET tables collapse many fairs into one cell.
JAMMED_CHUNK = re.compile(
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+(?P<body>.+?)\s+Download Event Application Form",
    re.IGNORECASE,
)



def _split_limits(limits: str) -> tuple[str, str]:
    if "-" not in limits:
        return "Unknown", "Unknown"
    left, right = [x.strip() for x in limits.split("-", 1)]
    return left or "Unknown", right or "Unknown"


def _split_jammed_body(body: str) -> tuple[str, str, str]:
    """Best-effort name / street / limits from a jammed schedule chunk."""
    body = re.sub(r"\b(ALMOST SOLD OUT|SOLD OUT)\b", "", body, flags=re.I)
    body = re.sub(r"\s+", " ", body).strip(" -")
    # Greedy name, then street phrase, then short from - to limits.
    m = re.match(
        r"^(?P<name>.+)\s+"
        r"(?P<street>\S+(?:\s+\S+){0,3}\s+(?:Street|Avenue|Ave\.?|Blvd|Boulevard|Road|Drive|Broadway|North|Place))\s+"
        r"(?P<frm>[^-]{1,40}?)\s-\s(?P<to>[^-]{1,40})$",
        body,
        re.IGNORECASE,
    )
    if m:
        name = clean_text(m.group("name"))
        street = clean_text(m.group("street"))
        limits = f"{m.group('frm').strip()} - {m.group('to').strip()}"
        if name and len(name) >= 4:
            return name, street, limits
    return clean_text(body), "Unknown", "Unknown"


def _row_from_parts(
    *,
    start: str,
    name: str,
    street: str,
    limits: str,
    verified_on: str,
) -> dict | None:
    name = re.sub(r"\b(ALMOST SOLD OUT|SOLD OUT)\b", "", name, flags=re.I).strip(" -")
    name = clean_text(name)
    if not name:
        return None
    street_from, street_to = _split_limits(limits)
    borough = guess_borough(name, street, limits)
    if borough == "Unknown":
        return None
    return base_record(
        name=name,
        start_date=start,
        end_date=start,
        borough=borough,
        venue=street if street != "Unknown" else name,
        street_from=street_from,
        street_to=street_to,
        organizer="Clearview Festival Productions",
        category="Street Fair",
        subcategory="Producer Schedule",
        status="Announced",
        confidence="High",
        primary_source=URL,
        website=URL,
        notes=f"Clearview schedule row; limits={limits}",
        verified_on=verified_on,
        permit_id=f"clearview:{start}:{name}",
    )


def parse_clearview_html(
    html: str,
    *,
    window_start: date,
    window_end: date,
    verified_on: str,
) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _maybe_add(start: str, name: str, street: str, limits: str) -> None:
        try:
            d = date.fromisoformat(start)
        except ValueError:
            return
        if d < window_start or d > window_end:
            return
        key = (start, name.lower())
        if key in seen:
            return
        mapped = _row_from_parts(
            start=start, name=name, street=street, limits=limits, verified_on=verified_on
        )
        if mapped:
            seen.add(key)
            records.append(mapped)

    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        # Skip mega-cells that contain many dated events (handled by jammed parser).
        dated = sum(1 for c in cells if re.search(r"\d{1,2}/\d{1,2}/\d{4}", c))
        if dated > 1 or any(len(c) > 200 for c in cells):
            continue
        date_name = ""
        street = "Unknown"
        limits = "Unknown"
        for cell in cells:
            if ROW_DATE.match(cell):
                date_name = cell
                continue
            if re.search(r"\b(Avenue|Street|Ave|St|Blvd|Road|Drive|Broadway)\b", cell, re.I):
                if "Download" in cell:
                    continue
                if street == "Unknown":
                    street = cell
                elif limits == "Unknown" and "-" in cell:
                    limits = cell
        m = ROW_DATE.match(date_name)
        if not m:
            continue
        start = parse_mdy(m.group(1))
        if not start:
            continue
        _maybe_add(start, m.group(2), street, limits)

    # Jammed single-cell / concatenated schedule text (only if tidy rows failed).
    if not records:
        page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        for m in JAMMED_CHUNK.finditer(page_text):
            start = parse_mdy(m.group("date"))
            if not start:
                continue
            name, street, limits = _split_jammed_body(m.group("body"))
            _maybe_add(start, name, street, limits)

    return records


def fetch_clearview(
    conn: sqlite3.Connection, *, window_start: date, window_end: date, **_kwargs
) -> dict:
    ensure_source(
        conn,
        source_id=SOURCE_ID,
        name="Clearview Festival Productions",
        base_url="https://vendors.clearviewfestival.com",
        authority="official_promoter",
        confidence="High",
        method="html_table",
    )
    client = AtlasHttpClient(cache_dir=str(ROOT / "data" / "raw"))
    response, meta = client.get(URL)
    verified_on = date.today().isoformat()
    records = parse_clearview_html(
        response.text,
        window_start=window_start,
        window_end=window_end,
        verified_on=verified_on,
    )
    snapshot_id = save_snapshot(
        conn,
        source_id=SOURCE_ID,
        meta=meta,
        params={"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        parser_version="clearview_html_v2",
    )
    report = queue_normalized_candidates(
        conn, source_id=SOURCE_ID, snapshot_id=snapshot_id, records=records
    )
    report["mapped_rows"] = len(records)
    return report
