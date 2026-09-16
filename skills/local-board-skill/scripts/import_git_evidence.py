#!/usr/bin/env python3
"""Import exact repository@commit references from board entity frontmatter into relations."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from board_config import load_board_config
from relations import load_document, save_document

REFERENCE = re.compile(r"(?P<repo>[A-Za-z0-9_./-]+)@(?P<hash>[0-9a-f]{7,64})\b")


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if line and line[0] not in " \t" and ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def frontmatter_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    return text[4:end] if end >= 0 else ""


def process_evidence_references(
    asset_id: str,
    frontmatter_text: str,
    commits: dict[tuple[str, str], dict[str, Any]],
    document: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    relations: set[tuple[str, str, str]],
) -> tuple[int, list[str]]:
    """Extract and link evidence references from frontmatter."""
    imported = 0
    unresolved: list[str] = []
    for match in REFERENCE.finditer(frontmatter_text):
        evidence = match.group(0)
        repo, short_hash = match.group("repo"), match.group("hash")
        matches = [(key, value) for key, value in commits.items() if key[0] == repo and key[1].startswith(short_hash)]
        if len(matches) != 1:
            unresolved.append(f"asset:{asset_id}:{evidence}")
            continue
        (repository, commit_hash), commit = matches[0]
        node_id = f"commit:{repository}:{commit_hash}"
        nodes[node_id] = {
            "id": node_id,
            "repository": repository,
            "hash": commit_hash,
            "committed_at": commit["committed_at"],
            "author": commit["author"],
            "subject": commit["subject"],
        }
        relation = (node_id, f"asset:{asset_id}", "evidence_for")
        if relation not in relations:
            document["relations"].append({
                "from": node_id,
                "to": f"asset:{asset_id}",
                "type": "evidence_for",
                "evidence": evidence,
                "confidence": "high",
                "decision": "exact repository and commit hash declared in asset frontmatter",
            })
            relations.add(relation)
            imported += 1
    return imported, unresolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Import exact Git evidence from board frontmatter")
    parser.add_argument("--board-dir", type=Path, default=Path.cwd() / "board")
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    config = load_board_config(args.board_dir)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    commits = {
        (repo["path"], commit["hash"]): commit
        for repo in inventory.get("repositories", [])
        for commit in repo.get("commits", [])
    }
    document = load_document(config.relations_file)
    nodes = {node["id"]: node for node in document["commits"]}
    relations = {(item["from"], item["to"], item["type"]) for item in document["relations"]}
    imported_total = 0
    all_unresolved: list[str] = []
    for path in config.board_dir.rglob(config.entity_glob):
        if config.sync_dir in path.parents or config.board_dir / "_meta" in path.parents:
            continue
        data = frontmatter(path)
        asset_id = data.get("id")
        if not asset_id:
            continue
        frontmatter_text = frontmatter_block(path)
        imported, unresolved = process_evidence_references(
            asset_id, frontmatter_text, commits, document, nodes, relations
        )
        imported_total += imported
        all_unresolved.extend(unresolved)
    if all_unresolved:
        raise RuntimeError("unresolved repository@commit references: " + ", ".join(sorted(all_unresolved)))
    document["commits"] = sorted(nodes.values(), key=lambda item: item["id"])
    save_document(config.relations_file, document)
    print(f"Imported relations={imported_total} unresolved_references=0 commits={len(document['commits'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
