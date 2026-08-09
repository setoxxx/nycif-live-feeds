#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

TOPOLOGY_CONTRACT = "nycif.borg-topology-projection.v1"
LEARNING_CONTRACT = "nycif.borg-learning-observation.v1"


def fingerprint_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records") or []
    fields = sorted({key for row in records if isinstance(row, dict) for key in row.keys()})
    material = json.dumps({"contract": payload.get("contract"), "fields": fields}, sort_keys=True).encode()
    return {
        "contract_hint": payload.get("contract"),
        "field_signature": fields,
        "schema_fingerprint": hashlib.sha256(material).hexdigest(),
        "row_count": len(records),
    }


def select_recipe(payload: dict[str, Any], registry: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    contract = payload.get("contract")
    exact = [r for r in registry.get("recipes", []) if r.get("source_contract") == contract]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, ["AMBIGUOUS_EXACT_RECIPE_MATCH"]
    return None, ["UNKNOWN_SCHEMA"]


def _node_id(node_type: str, identity: str) -> str:
    return f"{node_type}:{identity}"


def _edge_id(edge_type: str, source_id: str, target_id: str) -> str:
    return hashlib.sha256(f"{edge_type}|{source_id}|{target_id}".encode()).hexdigest()


def interpret_dataset(*, payload: dict[str, Any], registry: dict[str, Any], source_id: str, snapshot_id: str,
                      authority_class: str, sensitivity_class: str, provenance: dict[str, Any]) -> dict[str, Any]:
    fp = fingerprint_dataset(payload)
    recipe, warnings = select_recipe(payload, registry)
    envelope = {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        **fp,
        "authority_class": authority_class,
        "sensitivity_class": sensitivity_class,
        "provenance": provenance,
    }

    if recipe is None:
        return {
            "dataset": envelope,
            "interpretation_state": "REVIEW_REQUIRED",
            "recipe_id": None,
            "topology": {"contract": TOPOLOGY_CONTRACT, "nodes": [], "edges": []},
            "learning_observation": {
                "contract": LEARNING_CONTRACT,
                "schema_fingerprint": fp["schema_fingerprint"],
                "recipe_id": None,
                "interpretation_state": "REVIEW_REQUIRED",
                "row_count": fp["row_count"],
                "warnings": warnings,
                "unknown_fields": fp["field_signature"],
                "candidate_recipe_action": "REVIEW_NEW_SCHEMA",
            },
        }

    if recipe.get("authority_class") != authority_class:
        warnings.append("AUTHORITY_CLASS_MISMATCH")
    if recipe.get("culture_claim_power") != "NONE" and authority_class == "AUTHORITATIVE_AGGREGATE_STATISTICS":
        raise ValueError("Aggregate-statistics recipe cannot have Culture claim power")

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    identity_field = recipe["identity_field"]
    for row in payload.get("records") or []:
        if identity_field not in row:
            warnings.append(f"ROW_MISSING_IDENTITY:{identity_field}")
            continue
        identity = str(row[identity_field])
        node_id = _node_id(recipe["node_type"], identity)
        node = {
            "node_id": node_id,
            "node_type": recipe["node_type"],
            "identity": identity,
            "attributes": {k: v for k, v in row.items() if k != recipe.get("geometry_field")},
            "provenance": provenance,
        }
        geometry_field = recipe.get("geometry_field")
        if geometry_field:
            node["geometry"] = row.get(geometry_field)
        nodes.append(node)

        relationship = recipe.get("relationship")
        if relationship:
            target_identity = str(row.get(relationship["target_field"], identity))
            target_id = _node_id(relationship["target_node_type"], target_identity)
            edge_type = relationship["edge_type"]
            edges.append({
                "edge_id": _edge_id(edge_type, node_id, target_id),
                "edge_type": edge_type,
                "source_node_id": node_id,
                "target_node_id": target_id,
                "confidence": "EXACT",
                "provenance": provenance,
            })

    state = "RECOGNIZED_WITH_WARNINGS" if warnings else "RECOGNIZED"
    return {
        "dataset": envelope,
        "interpretation_state": state,
        "recipe_id": recipe["recipe_id"],
        "topology": {"contract": TOPOLOGY_CONTRACT, "nodes": nodes, "edges": edges},
        "learning_observation": {
            "contract": LEARNING_CONTRACT,
            "schema_fingerprint": fp["schema_fingerprint"],
            "recipe_id": recipe["recipe_id"],
            "interpretation_state": state,
            "row_count": fp["row_count"],
            "warnings": sorted(set(warnings)),
            "unknown_fields": [],
            "candidate_recipe_action": "REUSE_EXISTING" if not warnings else "REVIEW_RECIPE_UPDATE",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--authority-class", required=True)
    parser.add_argument("--sensitivity-class", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.dataset).read_text())
    registry = json.loads(Path(args.registry).read_text())
    result = interpret_dataset(
        payload=payload,
        registry=registry,
        source_id=args.source_id,
        snapshot_id=args.snapshot_id,
        authority_class=args.authority_class,
        sensitivity_class=args.sensitivity_class,
        provenance={"dataset_path": args.dataset},
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
