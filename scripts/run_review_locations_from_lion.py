#!/usr/bin/env python3
"""Run the LION audit with transport and schema normalization.

ArcGIS query parameters are submitted through form POST to avoid URL-length
rejection. LION line-node IDs are normalized across zero-padded string and
integer representations. Official LION street aliases used by the current
release are also reduced to the same canonical keys as the event source text.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

try:
    from scripts import resolve_review_locations_from_lion as lion
except ModuleNotFoundError:  # pragma: no cover
    import resolve_review_locations_from_lion as lion


_original_street_key = lion.street_key
_original_street_variants = lion.street_variants


def canonical_node_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(text))
    except (TypeError, ValueError):
        return text


def canonical_street_key(value: Any) -> str:
    key = _original_street_key(value)
    aliases = {
        "AV OF THE AMERICAS": "6 AVE",
        "AVE OF THE AMERICAS": "6 AVE",
        "AVENUE OF THE AMERICAS": "6 AVE",
        "AV OF AMERICAS": "6 AVE",
        "AVE OF AMERICAS": "6 AVE",
        "AVENUE OF AMERICAS": "6 AVE",
        "AMERICAS AV": "6 AVE",
        "AMERICAS AVE": "6 AVE",
        "AMERICAS AVENUE": "6 AVE",
        "6TH AVE": "6 AVE",
        "6TH AVENUE": "6 AVE",
        "MAC DOUGAL ST": "MACDOUGAL ST",
        "MAC DOUGAL STREET": "MACDOUGAL ST",
    }
    return aliases.get(key, key)


def official_street_variants(value: Any) -> set[str]:
    variants = set(_original_street_variants(value))
    key = canonical_street_key(value)
    if key == "6 AVE":
        variants.update(
            {
                "6 AVE",
                "6 AVENUE",
                "6TH AVE",
                "6TH AVENUE",
                "SIXTH AVE",
                "SIXTH AVENUE",
                "AV OF THE AMERICAS",
                "AVE OF THE AMERICAS",
                "AVENUE OF THE AMERICAS",
                "AV OF AMERICAS",
                "AVE OF AMERICAS",
                "AVENUE OF AMERICAS",
                "AMERICAS AV",
                "AMERICAS AVE",
                "AMERICAS AVENUE",
            }
        )
    if key == "MACDOUGAL ST":
        variants.update(
            {
                "MACDOUGAL ST",
                "MACDOUGAL STREET",
                "MAC DOUGAL ST",
                "MAC DOUGAL STREET",
            }
        )
    return variants


def normalized_node_street_index(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        names = {
            canonical_street_key(row.get("Street")),
            canonical_street_key(row.get("SAFStreetName")),
        }
        names.discard("")
        for field in ("NodeIDFrom", "NodeIDTo"):
            node_id = canonical_node_id(row.get(field))
            if node_id:
                index[node_id].update(names)
    return index


def arcgis_post(url: str, params: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode(params).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "User-Agent": "nycif-review-location-lion-audit/1.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=lion.HTTP_TIMEOUT_SEC) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LION POST request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"LION response is not an object for {url}")
    if payload.get("error"):
        raise RuntimeError(f"LION service error for {url}: {payload['error']}")
    time.sleep(lion.REQUEST_DELAY_SEC)
    return payload


lion.arcgis_get = arcgis_post
lion.street_key = canonical_street_key
lion.street_variants = official_street_variants
lion.node_street_index = normalized_node_street_index


if __name__ == "__main__":
    raise SystemExit(lion.main())
