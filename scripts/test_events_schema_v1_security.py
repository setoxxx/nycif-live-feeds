#!/usr/bin/env python3
"""Security regression checks for schema-v1 Field Desk viewer source."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "docs" / "field-desk-map-deploy" / "schema-v1-major-all-v01"
APP = (VIEWER / "app-schema-v1-major-all-v01.js").read_text(encoding="utf-8")
SCHEMA = (VIEWER / "event-feed-schema-v1.js").read_text(encoding="utf-8")
INDEX = (VIEWER / "index.html").read_text(encoding="utf-8")

XSS_PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    "<script>alert(1)</script>",
    'javascript:alert(1)',
    '"><svg onload=alert(1)>',
]


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def check_dom_xss_guards() -> None:
    if re.search(r"innerHTML\s*=\s*[`'\"][^`'\"]*\$\{", APP):
        fail("template string assigned to innerHTML (possible XSS)")
    if "popup.setContent('<div" in APP or 'popup.setContent("<div' in APP:
        fail("hardcoded HTML string popup for dynamic content")
    if "textContent" not in APP:
        fail("expected textContent-based DOM rendering")


def check_url_guards() -> None:
    if "safeExternalUrl" not in SCHEMA and "safeExternalUrl" not in APP:
        fail("missing safeExternalUrl helper")
    if "javascript:" not in SCHEMA:
        fail("safeExternalUrl must document javascript: rejection")
    if "noopener noreferrer" not in APP:
        fail("external links must set rel=noopener noreferrer")


def check_eval_guards() -> None:
    if re.search(r"\beval\s*\(", APP + SCHEMA) or "new Function" in (APP + SCHEMA):
        fail("eval/new Function forbidden")
    if "setTimeout(String(" in APP or 'setTimeout("' in APP:
        fail("string-based timers forbidden")


def check_cdn_integrity() -> None:
    if "integrity=" not in INDEX or "crossorigin=" not in INDEX:
        fail("CDN scripts/styles must include integrity + crossorigin")


def check_page_shard_guards() -> None:
    if "manifest.json" not in APP or "/pages/" not in APP:
        fail("viewer must load page shards via manifest")
    if "events_schema_v1_all.json" in APP and "loadLayerPages" not in APP:
        fail("viewer still references full dump without page shards")


def check_obsolete_paths() -> None:
    if "schema-v1-explorer" in APP or "schema-v1-explorer" in INDEX:
        fail("obsolete explorer path referenced")


def source_guards() -> None:
    check_dom_xss_guards()
    check_url_guards()
    check_eval_guards()
    check_cdn_integrity()
    check_page_shard_guards()
    check_obsolete_paths()


def runtime_url_and_xss_checks() -> None:
    """Exercise safeExternalUrl + inferCategory in Node without a browser DOM for URLs."""
    harness = f"""
const {{ JSDOM }} = (() => {{ try {{ return require('jsdom'); }} catch {{ return {{ JSDOM: null }}; }} }})();
const fs = require('fs');
const schemaSrc = fs.readFileSync({json.dumps(str(VIEWER / 'event-feed-schema-v1.js'))}, 'utf8');
const fakeWindow = {{ location: {{ origin: 'https://example.test' }} }};
global.window = fakeWindow;
global.document = {{ }};
eval(schemaSrc);
const S = global.window.NYCIF_EVENT_FEED_SCHEMA_V1;
const bad = {json.dumps(XSS_PAYLOADS)};
const urls = bad.map(v => S.safeExternalUrl(v));
const titles = bad.map(v => S.projectEvent({{
  id: 'x', title: v, category: 'general', location: v,
  source: {{ dataset: 't', source_event_id: '1' }},
  latitude: 40.7, longitude: -74.0, timezone: 'America/New_York',
  start_date_time: '2026-07-14T12:00:00-04:00'
}}, 0, 'approved_staged'));
const civic = S.inferCategory({{ title: "Brownsville Old Timer's Parade", category: 'general', event_type: 'Parade' }}, true);
const sports = S.inferCategory({{ title: 'Bayside 5K', category: 'general', event_type: 'Athletic Race / Tour' }}, true);
const fitness = S.inferCategory({{ title: 'Yoga in the Park', category: 'general' }}, true);
console.log(JSON.stringify({{
  urls,
  titles: titles.map(e => e.title),
  categories: titles.map(e => e.category),
  civic, sports, fitness,
  hasDom: !!JSDOM
}}));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(harness)
        path = fh.name
    try:
        proc = subprocess.run(["node", path], capture_output=True, text=True, check=False)
    finally:
        Path(path).unlink(missing_ok=True)
    if proc.returncode != 0:
        fail(f"node harness failed: {proc.stderr or proc.stdout}")
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    if any(u is not None for u in payload["urls"]):
        fail(f"malicious/js URLs must be rejected, got {payload['urls']}")
    for original, rendered in zip(XSS_PAYLOADS, payload["titles"]):
        if rendered != original:
            fail("XSS title must be preserved as plain text string, not stripped silently wrong")
        if "<script>" in rendered.lower() and rendered != original:
            fail("unexpected title mutation")
    if payload["civic"] != "civic":
        fail(f"parade sample expected civic, got {payload['civic']}")
    if payload["sports"] != "sports":
        fail(f"5K sample expected sports, got {payload['sports']}")
    if payload["fitness"] != "fitness":
        fail(f"yoga sample expected fitness, got {payload['fitness']}")


def main() -> int:
    source_guards()
    runtime_url_and_xss_checks()
    print("PASS: schema-v1 security source + runtime checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
