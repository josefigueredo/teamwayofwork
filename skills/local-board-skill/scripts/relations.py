#!/usr/bin/env python3
"""Shared contract and validation for a configured board relationship graph."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
NODE_COLLECTIONS = (
    "repositories",
    "assets",
    "specs",
    "commits",
    "pull_requests",
    "tags",
)
RELATION_TYPES = {
    "implements",
    "evidence_for",
    "part_of",
    "relates_to",
    "blocks",
    "released_by",
    "excluded_with_reason",
}


class RelationValidationError(ValueError):
    """Raised when the relationship graph cannot be safely synchronized."""


@dataclass(frozen=True)
class RelationNode:
    id: str
    data: dict[str, Any]


def empty_document() -> dict[str, Any]:
    """Return a valid, empty relationship document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {},
        "repositories": [],
        "assets": [],
        "specs": [],
        "commits": [],
        "pull_requests": [],
        "tags": [],
        "relations": [],
        "exceptions": [],
    }


def load_document(path: Path) -> dict[str, Any]:
    """Load and validate a relationship document."""
    if not path.exists():
        raise RelationValidationError(f"no existe el grafo configurado: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RelationValidationError(f"JSON inválido en {path}: {exc}") from exc
    validate_document(document)
    return document


def save_document(path: Path, document: dict[str, Any]) -> None:
    """Validate then atomically persist the relationship document."""
    validate_document(document)
    document["generated_at"] = datetime.now(timezone.utc).isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary_path.replace(path)


def index_nodes(document: dict[str, Any]) -> dict[str, RelationNode]:
    """Index every graph node by its globally unique identifier."""
    nodes: dict[str, RelationNode] = {}
    for collection in NODE_COLLECTIONS:
        values = document.get(collection, [])
        if not isinstance(values, list):
            raise RelationValidationError(f"{collection} debe ser una lista")
        for value in values:
            if not isinstance(value, dict):
                raise RelationValidationError(f"{collection} contiene un nodo no objeto")
            node_id = value.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                raise RelationValidationError(f"{collection} contiene un nodo sin id")
            if node_id in nodes:
                raise RelationValidationError(f"id duplicado: {node_id}")
            nodes[node_id] = RelationNode(node_id, value)
    return nodes


def validate_header(document: dict[str, Any]) -> None:
    if not isinstance(document, dict):
        raise RelationValidationError("el documento debe ser un objeto JSON")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise RelationValidationError(
            f"schema_version debe ser {SCHEMA_VERSION}, recibido {document.get('schema_version')!r}"
        )
    if not isinstance(document.get("baseline"), dict):
        raise RelationValidationError("baseline debe ser un objeto")
    missing = [collection for collection in (*NODE_COLLECTIONS, "relations", "exceptions") if collection not in document]
    if missing:
        raise RelationValidationError(f"faltan colecciones requeridas: {', '.join(missing)}")


def validate_relation(relation: Any, nodes: dict[str, RelationNode]) -> str | None:
    if not isinstance(relation, dict):
        raise RelationValidationError("relations contiene una relación no objeto")
    source, target, relation_type = relation.get("from"), relation.get("to"), relation.get("type")
    if not all(isinstance(value, str) for value in (source, target, relation_type)):
        raise RelationValidationError("from, to y type deben ser texto")
    if source not in nodes or target not in nodes:
        raise RelationValidationError(f"relación huérfana: {source!r} -> {target!r}")
    if relation_type not in RELATION_TYPES:
        raise RelationValidationError(f"tipo de relación no permitido: {relation_type!r}")
    if not isinstance(relation.get("evidence", ""), str) or not isinstance(relation.get("decision", ""), str):
        raise RelationValidationError("evidence y decision deben ser texto")
    if relation_type == "evidence_for" and source.startswith("commit:") and target.startswith("asset:"):
        return source
    return None


def validate_relations(document: dict[str, Any], nodes: dict[str, RelationNode]) -> set[str]:
    relations = document.get("relations")
    if not isinstance(relations, list):
        raise RelationValidationError("relations debe ser una lista")
    return {source for relation in relations if (source := validate_relation(relation, nodes))}


def validate_commit_coverage(document: dict[str, Any], nodes: dict[str, RelationNode], evidence_by_commit: set[str]) -> None:
    exceptions = document.get("exceptions")
    if not isinstance(exceptions, list):
        raise RelationValidationError("exceptions debe ser una lista")
    excluded_commits = {exception.get("commit") for exception in exceptions if isinstance(exception, dict) and exception.get("type") == "excluded_with_reason"}
    for node_id in nodes:
        if node_id.startswith("commit:") and node_id not in evidence_by_commit and node_id not in excluded_commits:
            raise RelationValidationError(f"commit sin evidencia ni exclusión: {node_id}")


def validate_document(document: dict[str, Any]) -> None:
    """Validate graph shape and synchronization invariants without network access."""
    validate_header(document)
    nodes = index_nodes(document)
    validate_commit_coverage(document, nodes, validate_relations(document, nodes))


def relations_for_asset(document: dict[str, Any], asset_id: str) -> list[dict[str, Any]]:
    """Return all graph relations that reference an asset node."""
    node_id = f"asset:{asset_id}"
    return [
        relation
        for relation in document.get("relations", [])
        if relation.get("from") == node_id or relation.get("to") == node_id
    ]
