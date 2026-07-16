"""Santa Rosalia / 18th Avenue Feast direct-source monitor."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from ..http_client import AtlasHttpClient
from ..normalize import clean_text
from ..review_ingest import ensure_source, queue_normalized_candidates, save_snapshot
from .common import base_record, parse_iso_date, parse_mdy
from ..sources.jsonld import extract_jsonld_events

SOURCE_ID = "santa_rosalia_18th_ave"
ROOT = Path(__file__).resolve().parents[3]

SEED_URLS = [
    "https://www.facebook.com/18thavenuefeast/",  # may fail robots/login — still attempt
    "https://www.nycgovparks.org/events",  # blocked; kept as documented target
]

# Prefer durable pages / known official mentions when available.
LOCAL_HINTS = ROOT / "config" / "seeds" / "santa_rosalia_sources.yaml"


def _dates_in_text(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text):
        iso = parse_mdy(m.group(1))
        if iso:
            out.append(iso)
    for m in re.finditer(r"\b(20\d{2}-\d{2}-\d{2})\b", text):
        out.append(m.group(1))
    return out


def fetch_santa_rosalia(
    conn: sqlite3.Connection, *, window_start: date, window_end: date, **_kwargs
) -> dict:
    ensure_source(
        conn,
        source_id=SOURCE_ID,
        name="Santa Rosalia / 18th Avenue Feast",
        base_url="https://www.18thavenuefeast.com",
        authority="official_local",
        confidence="High",
        method="direct_monitor",
    )
    import hashlib
    import yaml

    urls = []
    offline_paths = []
    if LOCAL_HINTS.exists():
        cfg = yaml.safe_load(LOCAL_HINTS.read_text(encoding="utf-8")) or []
        for x in cfg:
            if x.get("offline_html"):
                offline_paths.append(x["offline_html"])
            if x.get("url"):
                urls.append(x["url"])
    if not urls:
        urls = ["https://www.18thavenuefeast.com/"]

    client = AtlasHttpClient(cache_dir=str(ROOT / "data" / "raw"))
    verified_on = date.today().isoformat()
    records: list[dict] = []
    last_meta = None
    errors = []

    def _ingest_html(html: str, url: str, meta: dict) -> None:
        nonlocal last_meta, records
        last_meta = meta
        for item in extract_jsonld_events(html, url):
            name = clean_text(item.get("name"))
            if not re.search(r"rosalia|18th avenue|18th ave", name, re.I):
                continue
            start = parse_iso_date(item.get("start"))
            if start == "Unknown":
                continue
            d = date.fromisoformat(start)
            if d < window_start or d > window_end:
                continue
            records.append(
                base_record(
                    name=name,
                    start_date=start,
                    borough="Brooklyn",
                    venue="18th Avenue, Brooklyn",
                    organizer="Santa Rosalia Society / 18th Avenue Feast",
                    category="Religious Event",
                    subcategory="Feast",
                    status="Confirmed",
                    confidence="High",
                    primary_source=item.get("source_url") or url,
                    website=url,
                    notes="Direct Santa Rosalia / 18th Avenue monitor via JSON-LD",
                    verified_on=verified_on,
                )
            )

        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)
        if re.search(r"santa\s+rosalia|18th\s+avenue\s+feast", text, re.I):
            for iso in _dates_in_text(text):
                d = date.fromisoformat(iso)
                if d < window_start or d > window_end:
                    continue
                records.append(
                    base_record(
                        name="Santa Rosalia / 18th Avenue Feast",
                        start_date=iso,
                        borough="Brooklyn",
                        venue="18th Avenue, Bensonhurst, Brooklyn",
                        organizer="Santa Rosalia Society / 18th Avenue Feast",
                        category="Religious Event",
                        subcategory="Feast",
                        status="Announced",
                        confidence="Medium",
                        primary_source=url,
                        website=url,
                        notes=(
                            "Date found on page mentioning Santa Rosalia / 18th Avenue Feast. "
                            "Needs human verify of public hours/route."
                        ),
                        verified_on=verified_on,
                    )
                )

    for offline in offline_paths:
        op = Path(offline)
        if not op.is_absolute():
            op = ROOT / op
        if not op.exists() or not op.is_file() or op.stat().st_size == 0:
            continue
        html = op.read_text(encoding="utf-8", errors="ignore")
        body = html.encode("utf-8", errors="ignore")
        meta = {
            "url": str(op),
            "status": 200,
            "content_type": "text/html",
            "etag": None,
            "last_modified": None,
            "sha256": hashlib.sha256(body).hexdigest(),
            "local_path": str(op),
            "robots_policy": "offline_snapshot",
        }
        _ingest_html(html, str(op), meta)

    for url in urls:
        try:
            response, meta = client.get(url)
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})
            continue
        _ingest_html(response.text, url, meta)

    if last_meta is None:
        last_meta = {
            "url": urls[0] if urls else "about:blank",
            "status": 0,
            "content_type": "text/plain",
            "etag": None,
            "last_modified": None,
            "sha256": "0" * 64,
            "local_path": "",
            "robots_policy": "obey",
        }

    snapshot_id = save_snapshot(
        conn,
        source_id=SOURCE_ID,
        meta=last_meta,
        params={"urls": urls, "offline_paths": offline_paths, "errors": errors},
        parser_version="santa_rosalia_monitor_v2",
    )
    uniq = {}
    for r in records:
        uniq[(r["EVENT_NAME"], r["START_DATE"], r["VENUE"])] = r
    records = list(uniq.values())
    report = queue_normalized_candidates(
        conn, source_id=SOURCE_ID, snapshot_id=snapshot_id, records=records
    )
    report["mapped_rows"] = len(records)
    report["errors"] = errors
    report["monitored_urls"] = urls
    return report
