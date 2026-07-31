"""Config-driven community adapters: BIDs, Community Boards, libraries, museums, parishes."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup

from ..http_client import AtlasHttpClient
from ..normalize import clean_text
from ..review_ingest import ensure_source, queue_normalized_candidates, save_snapshot
from ..sources.ical import extract_ical_events
from ..sources.jsonld import extract_jsonld_events
from .common import base_record, guess_borough, parse_iso_date

ROOT = Path(__file__).resolve().parents[3]
SEEDS = ROOT / "config" / "seeds" / "community_sources.yaml"

_KEEP = re.compile(
    r"festival|fair|parade|feast|concert|market|celebration|holiday|lighting|procession",
    re.I,
)


def _location_name(loc) -> str:
    if isinstance(loc, dict):
        if isinstance(loc.get("name"), str):
            return loc["name"]
        address = loc.get("address")
        if isinstance(address, dict):
            return clean_text(
                address.get("streetAddress")
                or address.get("name")
                or address.get("addressLocality")
            )
        if isinstance(address, str):
            return clean_text(address)
    if isinstance(loc, str):
        return clean_text(loc)
    return "Unknown"


def _organizer_name(org) -> str:
    if isinstance(org, dict):
        return clean_text(org.get("name") or "Unknown")
    if isinstance(org, str):
        return clean_text(org)
    return "Unknown"


def map_jsonld(
    item: dict,
    *,
    seed: dict,
    window_start: date,
    window_end: date,
    verified_on: str,
) -> dict | None:
    start = parse_iso_date(item.get("start"))
    if start == "Unknown":
        return None
    try:
        d = date.fromisoformat(start)
    except ValueError:
        return None
    if d < window_start or d > window_end:
        return None
    name = clean_text(item.get("name"))
    if name == "Unknown":
        return None
    venue = _location_name(item.get("location"))
    borough = seed.get("borough") or guess_borough(name, venue, seed.get("name", ""))
    if borough == "Unknown":
        return None
    return base_record(
        name=name,
        start_date=start,
        end_date=parse_iso_date(item.get("end")) if item.get("end") else start,
        borough=borough,
        venue=venue,
        organizer=_organizer_name(item.get("organizer")) or seed.get("name") or "Unknown",
        category=seed.get("category") or "Community Program",
        subcategory=seed.get("subcategory") or seed.get("kind") or "Community Source",
        status="Confirmed",
        confidence=seed.get("confidence") or "High",
        primary_source=item.get("source_url") or seed["url"],
        website=seed.get("url") or item.get("source_url") or "Unknown",
        notes=f"JSON-LD from {seed.get('id')}; kind={seed.get('kind')}",
        verified_on=verified_on,
        permit_id=f"{seed.get('id')}:{item.get('source_record_id') or name}:{start}",
    )


def extract_time_datetime_events(html: str, page_url: str) -> list[dict]:
    """Weak HTML fallback: <time datetime> near a short heading/link title."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for t in soup.find_all("time"):
        dt = t.get("datetime") or t.get_text(" ", strip=True)
        start = parse_iso_date(dt)
        if start == "Unknown":
            continue
        parent = t.find_parent(["article", "li", "div", "section", "tr"])
        name = ""
        if parent is not None:
            for tag in parent.find_all(["h1", "h2", "h3", "h4", "a", "strong"]):
                text = tag.get_text(" ", strip=True)
                if 8 <= len(text) <= 160 and not re.fullmatch(r"[\d\W]+", text):
                    name = text
                    break
        if not name or not _KEEP.search(name):
            continue
        out.append(
            {
                "source_url": page_url,
                "source_record_id": f"time:{start}:{name[:60]}",
                "name": name,
                "start": start,
                "end": start,
                "location": "Unknown",
                "organizer": None,
            }
        )
    return out


def fetch_community_sources(
    conn: sqlite3.Connection,
    *,
    window_start: date,
    window_end: date,
    seeds_path: Path | None = None,
    kinds: set[str] | None = None,
) -> dict:
    path = seeds_path or SEEDS
    if not path.exists():
        return {"skipped": True, "reason": f"missing seeds file {path}"}
    seeds = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    client = AtlasHttpClient(cache_dir=str(ROOT / "data" / "raw"))
    verified_on = date.today().isoformat()
    summary = {"sources_attempted": 0, "sources_ok": 0, "mapped_rows": 0, "by_source": {}}

    window_start_dt = datetime.combine(window_start, datetime.min.time())
    window_end_dt = datetime.combine(window_end, datetime.max.time())

    for seed in seeds:
        kind = seed.get("kind") or "community"
        if kinds and kind not in kinds:
            continue
        source_id = seed["id"]
        summary["sources_attempted"] += 1
        ensure_source(
            conn,
            source_id=source_id,
            name=seed.get("name") or source_id,
            base_url=seed.get("url") or "",
            authority=seed.get("authority") or "official_local",
            confidence=seed.get("confidence") or "High",
            method=seed.get("method") or "html_jsonld_ical",
        )

        html = ""
        meta = None
        offline = seed.get("offline_html") or seed.get("offline_snapshot")
        if offline:
            op = Path(offline)
            if not op.is_absolute():
                op = ROOT / op
            if op.exists() and op.is_file() and op.stat().st_size > 0:
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

        if meta is None:
            try:
                response, meta = client.get(seed["url"])
                html = response.text
            except Exception as exc:  # robots / HTTP / timeout
                summary["by_source"][source_id] = {"error": str(exc)}
                continue

        records: list[dict] = []
        for item in extract_jsonld_events(html, seed["url"]):
            mapped = map_jsonld(
                item,
                seed=seed,
                window_start=window_start,
                window_end=window_end,
                verified_on=verified_on,
            )
            if mapped:
                records.append(mapped)

        if not records:
            for item in extract_time_datetime_events(html, seed["url"]):
                mapped = map_jsonld(
                    item,
                    seed=seed,
                    window_start=window_start,
                    window_end=window_end,
                    verified_on=verified_on,
                )
                if mapped:
                    mapped["SOURCE_CONFIDENCE"] = "Medium"
                    mapped["RESEARCH_NOTES"] = (
                        f"HTML <time> fallback from {seed.get('id')}; needs human verify"
                    )
                    records.append(mapped)

        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".ics" not in href.lower() and "text/calendar" not in (a.get("type") or ""):
                continue
            ics_url = urljoin(seed["url"], href)
            try:
                ics_resp, _ics_meta = client.get(ics_url, ext_hint=".ics")
                for item in extract_ical_events(
                    ics_resp.content, window_start_dt, window_end_dt, ics_url
                ):
                    start = item.get("start")
                    if hasattr(start, "date"):
                        start_s = start.date().isoformat()
                    else:
                        start_s = parse_iso_date(start)
                    if start_s == "Unknown":
                        continue
                    borough = seed.get("borough") or guess_borough(
                        item.get("name"), item.get("location"), seed.get("name", "")
                    )
                    if borough == "Unknown":
                        continue
                    records.append(
                        base_record(
                            name=clean_text(item.get("name")),
                            start_date=start_s,
                            borough=borough,
                            venue=clean_text(item.get("location") or "Unknown"),
                            organizer=seed.get("name") or "Unknown",
                            category=seed.get("category") or "Community Program",
                            subcategory=seed.get("subcategory") or kind,
                            status="Confirmed",
                            confidence=seed.get("confidence") or "High",
                            primary_source=ics_url,
                            website=seed.get("url") or ics_url,
                            notes=f"ICS from {source_id}",
                            verified_on=verified_on,
                            permit_id=(
                                f"{source_id}:{item.get('source_record_id') or item.get('name')}:{start_s}"
                            ),
                        )
                    )
            except Exception:
                continue

        snapshot_id = save_snapshot(
            conn,
            source_id=source_id,
            meta=meta,
            params={"seed": seed.get("id")},
            parser_version="community_jsonld_ical_v2",
        )
        report = queue_normalized_candidates(
            conn, source_id=source_id, snapshot_id=snapshot_id, records=records
        )
        summary["sources_ok"] += 1
        summary["mapped_rows"] += len(records)
        summary["by_source"][source_id] = report

    return summary
