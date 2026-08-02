#!/usr/bin/env python3
"""Discover and inspect official NYC facility datasets used by SHADOW-2.

This probe is read-only. It records Socrata metadata, API field names, source
view relationships, and a small sample for each explicitly approved dataset.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CATALOG = "https://api.us.socrata.com/api/catalog/v1"
DOMAIN = "data.cityofnewyork.us"
OUTPUT = Path("data/authoritative_facility_source_contracts.json")

QUERIES = (
    "NYC library branches locations",
    "New York Public Library locations",
    "Brooklyn Public Library locations",
    "Queens Public Library locations",
    "NYC DOE school locations",
    "NYC Parks recreation centers",
)

SELECTED_DATASETS = {
    "dpr_parks_structures": "n8q6-i44s",
    "citywide_libraries": "feuq-due4",
    "queens_libraries": "kh3d-xhq7",
    "brooklyn_libraries": "xmzf-uf2w",
    "doe_school_points": "jfju-ynrr",
    "dpr_pools": "y5rm-wagw",
    "dcp_facilities_map": "2fpa-bnsx",
}


def fetch_json(url: str, *, timeout: int = 60) -> Any:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "nycif-authoritative-facility-discovery/2.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def query_catalog(text: str) -> list[dict[str, Any]]:
    url = CATALOG + "?" + urllib.parse.urlencode(
        {"q": text, "search_context": DOMAIN, "limit": 20}
    )
    payload = fetch_json(url)
    output: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        resource = item.get("resource") or {}
        metadata = item.get("metadata") or {}
        output.append(
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "description": resource.get("description"),
                "type": resource.get("type"),
                "updatedAt": resource.get("updatedAt"),
                "domain": metadata.get("domain"),
                "permalink": item.get("permalink"),
            }
        )
    return output


def inspect_dataset(label: str, dataset_id: str) -> dict[str, Any]:
    metadata_url = f"https://{DOMAIN}/api/views/{dataset_id}"
    try:
        metadata = fetch_json(metadata_url)
    except Exception as exc:
        return {
            "label": label,
            "requested_id": dataset_id,
            "metadata_error": f"{type(exc).__name__}: {exc}",
        }

    data_id = str(metadata.get("modifyingViewUid") or dataset_id)
    columns = metadata.get("columns") or []
    contract = {
        "label": label,
        "requested_id": dataset_id,
        "data_id": data_id,
        "name": metadata.get("name"),
        "asset_type": metadata.get("assetType"),
        "view_type": metadata.get("viewType"),
        "attribution": metadata.get("attribution"),
        "rows_updated_at": metadata.get("rowsUpdatedAt"),
        "metadata_updated_at": metadata.get("viewLastModified"),
        "columns": [
            {
                "name": column.get("name"),
                "field": column.get("fieldName"),
                "datatype": column.get("dataTypeName"),
            }
            for column in columns
        ],
    }

    sample_url = (
        f"https://{DOMAIN}/resource/{data_id}.json?"
        + urllib.parse.urlencode({"$limit": 3})
    )
    try:
        sample = fetch_json(sample_url)
        contract["sample_rows"] = sample if isinstance(sample, list) else []
        contract["sample_error"] = None
    except Exception as exc:
        contract["sample_rows"] = []
        contract["sample_error"] = f"{type(exc).__name__}: {exc}"
    return contract


def main() -> int:
    report = {
        "catalog_queries": {query: query_catalog(query) for query in QUERIES},
        "selected_dataset_contracts": {
            label: inspect_dataset(label, dataset_id)
            for label, dataset_id in SELECTED_DATASETS.items()
        },
        "safety": {
            "read_only": True,
            "coordinates_modified": False,
            "feeds_modified": False,
            "promotion_allowed": False,
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
