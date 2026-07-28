#!/usr/bin/env python3
"""Run the LION audit using ArcGIS form-POST queries.

ArcGIS supports query parameters through application/x-www-form-urlencoded
POST requests. This avoids intermediary URL-length rejection when the audit
submits multiple official street-name variants in one request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    from scripts import resolve_review_locations_from_lion as lion
except ModuleNotFoundError:  # pragma: no cover
    import resolve_review_locations_from_lion as lion


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


if __name__ == "__main__":
    raise SystemExit(lion.main())
