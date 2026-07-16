"""NYC Street Fairs / Mardi Gras producer schedule (PDF) adapter."""

from __future__ import annotations

import io
import re
import sqlite3
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pypdf import PdfReader

from ..http_client import AtlasHttpClient
from ..normalize import clean_text
from ..review_ingest import ensure_source, queue_normalized_candidates, save_snapshot
from .common import base_record, guess_borough, parse_mdy

SOURCE_ID = "nyc_street_fairs"
PAGE_URL = "https://nycstreetfairs.com/event-schedule/"
ROOT = Path(__file__).resolve().parents[3]

DATE_LINE = re.compile(
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})\s+(?P<name>.+?)"
    r"(?:\s{2,}|\t| - | – | — )(?P<loc>.+)$"
)
SIMPLE = re.compile(r"(?P<date>\d{1,2}/\d{1,2}/\d{4})\s+(?P<rest>.+)$")

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# "JULY 15ᵗʰ" / "AUG. 1st" / "SEPTEMBER 7"
_ORDINAL_DATE = re.compile(
    r"\b(?P<month>"
    r"JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|JUN(?:E)?|"
    r"JUL(?:Y)?|AUG(?:UST)?|SEP(?:T(?:EMBER)?)?|OCT(?:OBER)?|"
    r"NOV(?:EMBER)?|DEC(?:EMBER)?"
    r")\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th|ᵗʰ|ˢᵗ|ⁿᵈ|ʳᵈ)?\b",
    re.IGNORECASE,
)


def _extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_pdf_bytes(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _normalize_text(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\xa0", " ")
    text = re.sub(r"(\d{1,2})(?:st|nd|rd|th|ᵗʰ|ˢᵗ|ⁿᵈ|ʳᵈ)", r"\1", text, flags=re.I)
    return text


def _parse_month_day(month: str, day: str, year: int) -> str | None:
    m = _MONTHS.get(month.lower().rstrip("."))
    if not m:
        return None
    try:
        return date(year, m, int(day)).isoformat()
    except ValueError:
        return None


def parse_schedule_text(
    text: str,
    *,
    window_start: date,
    window_end: date,
    source_url: str,
    verified_on: str,
    default_year: int | None = None,
) -> list[dict]:
    text = _normalize_text(text)
    year = default_year or window_start.year
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    current_date: str | None = None

    def _add(start: str, name: str, loc: str) -> None:
        name = clean_text(name)
        loc = clean_text(loc) if loc else "Unknown"
        if not name or name.lower() in {"annual schedule", "nyc street fairs", "schedule", "price"}:
            return
        try:
            d = date.fromisoformat(start)
        except ValueError:
            return
        if d < window_start or d > window_end:
            return
        borough = guess_borough(name, loc)
        if borough == "Unknown":
            return
        key = (start, name.lower())
        if key in seen:
            return
        seen.add(key)
        records.append(
            base_record(
                name=name,
                start_date=start,
                end_date=start,
                borough=borough,
                venue=loc,
                organizer="NYC Street Fairs",
                category="Street Fair",
                subcategory="Producer Schedule",
                status="Announced",
                confidence="High",
                primary_source=source_url,
                website=source_url,
                notes="Parsed from NYC Street Fairs schedule PDF/HTML text. Street limits Unknown unless present.",
                verified_on=verified_on,
                permit_id=f"nycstreetfairs:{start}:{name}",
            )
        )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "price" in line.lower():
            continue

        # Numeric date formats
        m = DATE_LINE.search(line)
        if m:
            raw_date = m.group("date")
            start = raw_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) else parse_mdy(raw_date)
            if start:
                current_date = start
                _add(start, m.group("name"), m.group("loc"))
            continue

        m2 = SIMPLE.search(line)
        if m2:
            start = parse_mdy(m2.group("date"))
            if start:
                current_date = start
                rest = m2.group("rest").strip()
                parts = re.split(r"\s{2,}|\t", rest, maxsplit=1)
                if len(parts) == 2:
                    _add(start, parts[0], parts[1])
                else:
                    _add(start, rest, "Unknown")
            continue

        # Ordinal month dates: JULY 15 / AUG. 1
        om = _ORDINAL_DATE.search(line)
        if om:
            start = _parse_month_day(om.group("month"), om.group("day"), year)
            if start:
                current_date = start
                rest = line[om.end() :].strip(" –—-\t")
                if rest:
                    parts = re.split(r"\s{2,}|\t| – | — | - ", rest, maxsplit=1)
                    if len(parts) == 2:
                        _add(start, parts[0], parts[1])
                    else:
                        _add(start, rest, "Unknown")
            continue

        if current_date and len(line) >= 4 and not re.fullmatch(r"\d+", line):
            if re.search(r"page\s+\d+", line, re.I):
                continue
            parts = re.split(r"\s{2,}|\t| – | — | - ", line, maxsplit=1)
            if len(parts) == 2:
                _add(current_date, parts[0], parts[1])
            else:
                _add(current_date, line, "Unknown")

    return records


def fetch_nyc_street_fairs(
    conn: sqlite3.Connection, *, window_start: date, window_end: date, **_kwargs
) -> dict:
    ensure_source(
        conn,
        source_id=SOURCE_ID,
        name="NYC Street Fairs / Mardi Gras",
        base_url="https://nycstreetfairs.com",
        authority="official_promoter",
        confidence="High",
        method="pdf_or_html",
    )
    client = AtlasHttpClient(
        cache_dir=str(ROOT / "data" / "raw"),
        # Producer publishes this machine-readable annual PDF; HTML schedule page is
        # often robots-blocked / 403. Treat the known PDF as an official feed.
        robots_policy="official_feed",
    )
    verified_on = date.today().isoformat()
    records: list[dict] = []
    pdf_href = (
        "https://nycstreetfairs.com/wp-content/uploads/2026/07/2026-Vendor-Schedule-4TH-EDITION.pdf"
    )
    page_meta = {
        "url": PAGE_URL,
        "status": 0,
        "content_type": "text/html",
        "etag": None,
        "last_modified": None,
        "sha256": "0" * 64,
        "local_path": "",
        "robots_policy": "obey",
    }
    errors: list[dict] = []

    try:
        page, page_meta = client.get(PAGE_URL)
        soup = BeautifulSoup(page.text, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            label = a.get_text(" ", strip=True).lower()
            if ".pdf" in href.lower() and (
                "2026" in href
                or "2026" in label
                or "schedule" in label
                or "schedule" in href.lower()
            ):
                pdf_href = urljoin(PAGE_URL, href)
                break
    except Exception as exc:  # noqa: BLE001
        errors.append({"url": PAGE_URL, "error": str(exc)})
        soup = None

    meta = page_meta
    source_url = pdf_href
    try:
        pdf_resp, meta = client.get(pdf_href, ext_hint=".pdf")
        local = Path(meta.get("local_path") or "")
        if local.exists() and local.suffix.lower() == ".pdf":
            text = _extract_pdf_text(local)
        else:
            text = _extract_pdf_bytes(pdf_resp.content)
        records = parse_schedule_text(
            text,
            window_start=window_start,
            window_end=window_end,
            source_url=pdf_href,
            verified_on=verified_on,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append({"url": pdf_href, "error": str(exc)})
        if soup is not None:
            text = soup.get_text("\n", strip=True)
            records = parse_schedule_text(
                text,
                window_start=window_start,
                window_end=window_end,
                source_url=PAGE_URL,
                verified_on=verified_on,
            )
            meta = page_meta
            source_url = PAGE_URL
        meta = dict(meta)
        meta["pdf_error"] = str(exc)

    snapshot_id = save_snapshot(
        conn,
        source_id=SOURCE_ID,
        meta=meta,
        params={"pdf_url": pdf_href, "source_url": source_url, "errors": errors},
        parser_version="nyc_street_fairs_pdf_v2",
    )
    report = queue_normalized_candidates(
        conn, source_id=SOURCE_ID, snapshot_id=snapshot_id, records=records
    )
    report["mapped_rows"] = len(records)
    report["pdf_url"] = pdf_href
    report["errors"] = errors
    return report
